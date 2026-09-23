/* ВетФинанс — сервер сайта.
   Раздаёт статику из public/ и принимает заявки на POST /api/lead,
   пересылая их в Telegram. Никаких зависимостей: только Node 18+. */

'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const crypto = require('node:crypto');

const PORT = process.env.PORT || 3000;
const ROOT = path.join(__dirname, 'public');
const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || '';
const CHAT_ID = process.env.TELEGRAM_CHAT_ID || '';

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.xml': 'application/xml; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.mp4': 'video/mp4',
  '.woff2': 'font/woff2'
};
const COMPRESSIBLE = /^(text\/|application\/(xml|json)|image\/svg)/;

/* ---------- статика: читаем и сжимаем один раз при старте ---------- */

const files = new Map();

function loadDir(dir, prefix) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    const url = prefix + '/' + entry.name;
    if (entry.isDirectory()) { loadDir(full, url); continue; }

    const body = fs.readFileSync(full);
    const type = TYPES[path.extname(entry.name).toLowerCase()] || 'application/octet-stream';
    const asset = {
      body: body,
      type: type,
      etag: '"' + crypto.createHash('sha1').update(body).digest('hex').slice(0, 16) + '"',
      gzip: null,
      br: null
    };
    if (COMPRESSIBLE.test(type) && body.length > 1024) {
      asset.gzip = zlib.gzipSync(body, { level: 8 });
      asset.br = zlib.brotliCompressSync(body, {
        params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 5 }
      });
    }
    files.set(url, asset);
  }
}
loadDir(ROOT, '');

/* /privacy и /privacy.html — одна и та же страница */
function lookup(pathname) {
  if (pathname === '/') return files.get('/index.html');
  if (files.has(pathname)) return files.get(pathname);
  if (files.has(pathname + '.html')) return files.get(pathname + '.html');
  if (pathname.endsWith('/') && files.has(pathname.slice(0, -1) + '.html')) {
    return files.get(pathname.slice(0, -1) + '.html');
  }
  return null;
}

function securityHeaders(res) {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'SAMEORIGIN');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
}

function sendAsset(req, res, asset, status) {
  securityHeaders(res);
  res.setHeader('Content-Type', asset.type);
  res.setHeader('ETag', asset.etag);
  res.setHeader('Vary', 'Accept-Encoding');
  res.setHeader('Cache-Control',
    asset.type.indexOf('text/html') === 0 ? 'public, max-age=0, must-revalidate' : 'public, max-age=3600');

  if (req.headers['if-none-match'] === asset.etag) { res.writeHead(304); return res.end(); }

  const accept = req.headers['accept-encoding'] || '';
  let body = asset.body;
  if (asset.br && /\bbr\b/.test(accept)) { body = asset.br; res.setHeader('Content-Encoding', 'br'); }
  else if (asset.gzip && /\bgzip\b/.test(accept)) { body = asset.gzip; res.setHeader('Content-Encoding', 'gzip'); }

  res.setHeader('Content-Length', body.length);
  res.writeHead(status || 200);
  res.end(req.method === 'HEAD' ? undefined : body);
}

function sendJson(res, status, obj) {
  const body = Buffer.from(JSON.stringify(obj));
  securityHeaders(res);
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Content-Length', body.length);
  res.writeHead(status);
  res.end(body);
}

/* ---------- заявки ---------- */

/* Не больше 5 заявок с одного адреса за 10 минут — от случайного спама. */
const RATE_WINDOW = 10 * 60 * 1000;
const RATE_MAX = 5;
const hits = new Map();

function rateLimited(ip) {
  const now = Date.now();
  const list = (hits.get(ip) || []).filter(function (t) { return now - t < RATE_WINDOW; });
  list.push(now);
  hits.set(ip, list);
  if (hits.size > 5000) hits.clear();
  return list.length > RATE_MAX;
}

function readBody(req, limit) {
  return new Promise(function (resolve, reject) {
    let size = 0;
    const chunks = [];
    req.on('data', function (c) {
      size += c.length;
      if (size > limit) { reject(new Error('too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', function () { resolve(Buffer.concat(chunks).toString('utf8')); });
    req.on('error', reject);
  });
}

function clean(v, max) {
  return String(v == null ? '' : v).replace(/\s+/g, ' ').trim().slice(0, max);
}

function escapeHtml(v) {
  return v.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function validate(data) {
  const lead = {
    name: clean(data.name, 120),
    phone: clean(data.phone, 40),
    clinic: clean(data.clinic, 160),
    mis: clean(data.mis, 80),
    banks: Array.isArray(data.banks)
      ? data.banks.slice(0, 12).map(function (b) { return clean(b, 40); }).filter(Boolean)
      : [],
    page: clean(data.page, 300),
    ref: clean(data.ref, 300)
  };
  if (!lead.name || !lead.clinic || !lead.mis) return { error: 'Заполните все поля.' };
  if (lead.phone.replace(/\D/g, '').length < 10) return { error: 'Проверьте номер телефона.' };
  if (!lead.banks.length) return { error: 'Отметьте банк.' };
  return { lead: lead };
}

async function toTelegram(lead) {
  const text =
    '<b>Заявка с сайта ВетФинанс</b>\n\n' +
    '<b>Имя:</b> ' + escapeHtml(lead.name) + '\n' +
    '<b>Телефон:</b> ' + escapeHtml(lead.phone) + '\n' +
    '<b>Клиника:</b> ' + escapeHtml(lead.clinic) + '\n' +
    '<b>Программа учёта:</b> ' + escapeHtml(lead.mis) + '\n' +
    '<b>Банки:</b> ' + escapeHtml(lead.banks.join(', ')) + '\n' +
    (lead.ref ? '<b>Пришёл с:</b> ' + escapeHtml(lead.ref) + '\n' : '') +
    '\n' + new Date().toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }) + ' МСК';

  const r = await fetch('https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: CHAT_ID,
      text: text,
      parse_mode: 'HTML',
      disable_web_page_preview: true
    })
  });
  if (!r.ok) {
    const detail = await r.text();
    throw new Error('Telegram ответил ' + r.status + ': ' + detail.slice(0, 300));
  }
}

async function handleLead(req, res) {
  const forwarded = req.headers['x-forwarded-for'] || '';
  const ip = forwarded.split(',')[0].trim() || req.socket.remoteAddress || '?';
  if (rateLimited(ip)) return sendJson(res, 429, { error: 'Слишком много заявок. Попробуйте позже.' });

  let data;
  try {
    data = JSON.parse(await readBody(req, 16 * 1024));
  } catch (e) {
    return sendJson(res, 400, { error: 'Не удалось прочитать заявку.' });
  }

  const checked = validate(data);
  if (checked.error) return sendJson(res, 400, { error: checked.error });

  /* Заявка всегда попадает в лог — даже если Telegram недоступен, её видно в Railway. */
  console.log('ЗАЯВКА', JSON.stringify(checked.lead));

  if (!BOT_TOKEN || !CHAT_ID) {
    console.error('TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы — заявка не отправлена в Telegram');
    return sendJson(res, 503, { error: 'Приём заявок временно недоступен.' });
  }

  try {
    await toTelegram(checked.lead);
    sendJson(res, 200, { ok: true });
  } catch (e) {
    console.error('Не удалось отправить заявку в Telegram:', e.message);
    sendJson(res, 502, { error: 'Не удалось отправить заявку.' });
  }
}

/* ---------- маршруты ---------- */

const server = http.createServer(async function (req, res) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  } catch (e) {
    return sendJson(res, 400, { error: 'Некорректный адрес.' });
  }

  if (pathname === '/api/lead') {
    if (req.method !== 'POST') { res.writeHead(405, { Allow: 'POST' }); return res.end(); }
    return handleLead(req, res);
  }

  if (pathname === '/healthz') return sendJson(res, 200, { ok: true });

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' });
    return res.end();
  }

  const asset = lookup(pathname);
  if (asset) return sendAsset(req, res, asset, 200);

  const notFound = files.get('/404.html');
  if (notFound) return sendAsset(req, res, notFound, 404);
  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Страница не найдена');
});

server.on('error', function (e) {
  if (e.code === 'EADDRINUSE') {
    console.error('Порт ' + PORT + ' уже занят. Закройте другой запуск сайта или укажите свободный порт:');
    console.error('  PORT=3100 npm run dev            (bash)');
    console.error('  $env:PORT="3100"; npm run dev    (PowerShell)');
    process.exit(1);
  }
  throw e;
});

server.listen(PORT, function () {
  console.log('');
  console.log('  ВетФинанс — сайт запущен');
  console.log('');
  console.log('  Откройте:  http://localhost:' + PORT + '/');
  console.log('  Документы: http://localhost:' + PORT + '/privacy  /offer  /consent');
  console.log('');
  if (BOT_TOKEN && CHAT_ID) {
    console.log('  Заявки с формы уходят в Telegram.');
  } else {
    console.log('  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы:');
    console.log('  форма ответит «Приём заявок временно недоступен», но саму заявку');
    console.log('  будет видно здесь строкой «ЗАЯВКА {...}».');
  }
  console.log('  Остановить: Ctrl+C');
  console.log('');
});
