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
/* Сводка по сайту в боте: номер счётчика Метрики, OAuth-токен с правом чтения
   статистики, секрет вебхука и публичный адрес сайта для регистрации вебхука. */
const METRIKA_ID = /^\d+$/.test(process.env.METRIKA_COUNTER_ID || '') ? process.env.METRIKA_COUNTER_ID : '';
const METRIKA_TOKEN = process.env.METRIKA_TOKEN || '';
const WEBHOOK_SECRET = /^[A-Za-z0-9_-]{16,256}$/.test(process.env.TELEGRAM_WEBHOOK_SECRET || '')
  ? process.env.TELEGRAM_WEBHOOK_SECRET : '';
const PUBLIC_URL = (process.env.PUBLIC_URL || '').replace(/\/+$/, '');

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

    let body = fs.readFileSync(full);
    /* Номер счётчика Метрики берём из METRIKA_COUNTER_ID, чтобы не держать его в двух местах. */
    if (url === '/assets/site.js' && METRIKA_ID) {
      body = Buffer.from(body.toString('utf8').replace("var METRIKA_ID = '';", "var METRIKA_ID = '" + METRIKA_ID + "';"));
    }
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

/* Заявка на демо: только имя и контакт — телефон, ник в Telegram или почта. */
function validateDemo(data) {
  const lead = {
    type: 'demo',
    name: clean(data.name, 120),
    contact: clean(data.contact, 80),
    page: clean(data.page, 300),
    ref: clean(data.ref, 300)
  };
  if (!lead.name || !lead.contact) return { error: 'Заполните все поля.' };
  const isPhone = lead.contact.replace(/\D/g, '').length >= 10;
  const isTelegram = /^(@|https?:\/\/t\.me\/|t\.me\/)?[A-Za-z][A-Za-z0-9_]{4,31}$/.test(lead.contact);
  const isEmail = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(lead.contact);
  if (!isPhone && !isTelegram && !isEmail) return { error: 'Укажите телефон, ник в Telegram или почту.' };
  return { lead: lead };
}

function validate(data) {
  if (data && data.type === 'demo') return validateDemo(data);
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

function telegramLink(contact) {
  const nick = contact.replace(/^(@|https?:\/\/t\.me\/|t\.me\/)/, '');
  if (contact.replace(/\D/g, '').length >= 10 || !/^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(nick)) return escapeHtml(contact);
  return '<a href="https://t.me/' + nick + '">@' + nick + '</a>';
}

async function toTelegram(lead) {
  const when = '\n' + new Date().toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }) + ' МСК';
  if (lead.type === 'demo') {
    return tg('sendMessage', {
      chat_id: CHAT_ID,
      text: '<b>Заявка на демо</b>\n\n' +
        '<b>Имя:</b> ' + escapeHtml(lead.name) + '\n' +
        '<b>Контакт:</b> ' + telegramLink(lead.contact) + '\n' +
        (lead.ref ? '<b>Пришёл с:</b> ' + escapeHtml(lead.ref) + '\n' : '') + when,
      parse_mode: 'HTML',
      disable_web_page_preview: true
    });
  }
  const text =
    '<b>Заявка с сайта ВетФинанс</b>\n\n' +
    '<b>Имя:</b> ' + escapeHtml(lead.name) + '\n' +
    '<b>Телефон:</b> ' + escapeHtml(lead.phone) + '\n' +
    '<b>Клиника:</b> ' + escapeHtml(lead.clinic) + '\n' +
    '<b>Программа учёта:</b> ' + escapeHtml(lead.mis) + '\n' +
    '<b>Банки:</b> ' + escapeHtml(lead.banks.join(', ')) + '\n' +
    (lead.ref ? '<b>Пришёл с:</b> ' + escapeHtml(lead.ref) + '\n' : '') + when;

  await tg('sendMessage', {
    chat_id: CHAT_ID,
    text: text,
    parse_mode: 'HTML',
    disable_web_page_preview: true
  });
}

async function tg(method, payload) {
  const r = await fetch('https://api.telegram.org/bot' + BOT_TOKEN + '/' + method, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!r.ok) {
    const detail = await r.text();
    throw new Error('Telegram ответил ' + r.status + ': ' + detail.slice(0, 300));
  }
  return r.json();
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

/* ---------- сводка по сайту в боте ----------
   Бот отвечает на /stats только в чате заявок (TELEGRAM_CHAT_ID). Цифры берутся
   из API Яндекс Метрики, поэтому учитываются посетители, согласившиеся на cookie. */

const PERIODS = {
  today: { label: 'сегодня', date1: 'today', date2: 'today' },
  yesterday: { label: 'вчера', date1: 'yesterday', date2: 'yesterday' },
  week: { label: '7 дней', date1: '6daysAgo', date2: 'today' },
  month: { label: '30 дней', date1: '29daysAgo', date2: 'today' }
};

const PERIOD_BUTTONS = {
  inline_keyboard: [
    [
      { text: 'Сегодня', callback_data: 'stats:today' },
      { text: 'Вчера', callback_data: 'stats:yesterday' }
    ],
    [
      { text: '7 дней', callback_data: 'stats:week' },
      { text: '30 дней', callback_data: 'stats:month' }
    ]
  ]
};

const SOURCE_NAMES = {
  organic: 'Поиск',
  direct: 'Прямые заходы',
  referral: 'Ссылки на сайтах',
  social: 'Соцсети',
  ad: 'Реклама',
  messenger: 'Мессенджеры',
  internal: 'Внутренние переходы',
  email: 'Почта',
  recommend: 'Рекомендации',
  saved: 'Сохранённые страницы',
  undefined: 'Не определено'
};

const DEVICE_NAMES = { desktop: 'Компьютеры', mobile: 'Смартфоны', tablet: 'Планшеты', tv: 'ТВ' };

async function metrika(params) {
  const q = new URLSearchParams(Object.assign({ ids: METRIKA_ID, accuracy: 'full' }, params));
  const r = await fetch('https://api-metrika.yandex.net/stat/v1/data?' + q, {
    headers: { Authorization: 'OAuth ' + METRIKA_TOKEN }
  });
  if (!r.ok) {
    const detail = await r.text();
    throw new Error('Метрика ответила ' + r.status + ': ' + detail.slice(0, 300));
  }
  return r.json();
}

/* Номера целей «lead» и «demo». Считаем только их: автоматические цели Метрики
   (клики по телефону, почте и т. п.) заявками не являются. Список кешируем на час. */
let goalsCache = { at: 0, ids: null };

async function goalIds() {
  if (goalsCache.ids && Date.now() - goalsCache.at < 60 * 60 * 1000) return goalsCache.ids;
  const r = await fetch('https://api-metrika.yandex.net/management/v1/counter/' + METRIKA_ID + '/goals', {
    headers: { Authorization: 'OAuth ' + METRIKA_TOKEN }
  });
  if (!r.ok) throw new Error('Метрика (цели) ответила ' + r.status + ': ' + (await r.text()).slice(0, 300));
  const ids = {};
  for (const goal of (await r.json()).goals || []) {
    for (const c of goal.conditions || []) {
      if ((c.url === 'lead' || c.url === 'demo') && !ids[c.url]) ids[c.url] = goal.id;
    }
  }
  goalsCache = { at: Date.now(), ids: ids };
  return ids;
}

function num(v) {
  return Math.round(v).toLocaleString('ru-RU');
}

function pct(v) {
  return (Math.round(v * 10) / 10).toLocaleString('ru-RU') + '%';
}

function duration(sec) {
  const s = Math.round(sec);
  return Math.floor(s / 60) + ' мин ' + String(s % 60).padStart(2, '0') + ' с';
}

function shortDate(iso) {
  const p = iso.split('-');
  return p[2] + '.' + p[1];
}

/* Строки вида «Поиск — 12 (40%)» для топа по визитам. */
function breakdown(report, names, total) {
  return report.data.slice(0, 5).map(function (row) {
    const key = row.dimensions[0].id || row.dimensions[0].name || 'undefined';
    const name = names[key] || row.dimensions[0].name || 'Не определено';
    const visits = row.metrics[0];
    return '• ' + escapeHtml(String(name)) + ' — ' + num(visits) +
      (total ? ' (' + pct(visits / total * 100) + ')' : '');
  }).join('\n');
}

async function siteSummary(periodKey) {
  const p = PERIODS[periodKey] || PERIODS.today;
  const range = { date1: p.date1, date2: p.date2 };
  const goals = await goalIds();
  const goalMetrics = ['lead', 'demo'].filter(function (k) { return goals[k]; });

  const results = await Promise.all([
    metrika(Object.assign({
      metrics: 'ym:s:users,ym:s:visits,ym:s:pageviews,ym:s:percentNewVisitors,' +
        'ym:s:bounceRate,ym:s:avgVisitDurationSeconds' +
        goalMetrics.map(function (k) { return ',ym:s:goal' + goals[k] + 'reaches'; }).join('')
    }, range)),
    metrika(Object.assign({
      metrics: 'ym:s:visits', dimensions: 'ym:s:lastTrafficSource', sort: '-ym:s:visits', limit: '5'
    }, range)),
    metrika(Object.assign({
      metrics: 'ym:s:visits', dimensions: 'ym:s:deviceCategory', sort: '-ym:s:visits', limit: '5'
    }, range))
  ]);
  const totals = results[0].totals;
  const users = totals[0], visits = totals[1], pageviews = totals[2];
  const newShare = totals[3], bounce = totals[4], avgTime = totals[5];
  const reached = {};
  goalMetrics.forEach(function (k, i) { reached[k] = totals[6 + i]; });

  function goalLine(label, k) {
    if (!(k in reached)) return '<b>' + label + ':</b> цель «' + k + '» не создана в Метрике\n';
    return '<b>' + label + ':</b> ' + num(reached[k]) + ' (' + pct(reached[k] / visits * 100) + ' визитов)\n';
  }

  const q = results[0].query;
  const dates = q.date1 === q.date2 ? shortDate(q.date1) : shortDate(q.date1) + '–' + shortDate(q.date2);

  let text = '<b>Сайт за ' + p.label + '</b> (' + dates + ')\n\n';
  if (!visits) {
    return text + 'Заходов пока нет. Метрика обновляет данные с задержкой в несколько минут.';
  }
  text +=
    '<b>Посетители:</b> ' + num(users) + ' (новых ' + pct(newShare) + ')\n' +
    '<b>Визиты:</b> ' + num(visits) + '\n' +
    '<b>Просмотры страниц:</b> ' + num(pageviews) + '\n' +
    '<b>Отказы:</b> ' + pct(bounce) + '\n' +
    '<b>Время на сайте:</b> ' + duration(avgTime) + '\n' +
    goalLine('Заявки на подключение', 'lead') +
    goalLine('Заявки на демо', 'demo') + '\n' +
    '<b>Откуда пришли</b>\n' + breakdown(results[1], SOURCE_NAMES, visits) + '\n\n' +
    '<b>Устройства</b>\n' + breakdown(results[2], DEVICE_NAMES, visits) + '\n\n' +
    '<i>Только посетители, принявшие cookie.</i>';
  return text;
}

async function statsText(periodKey) {
  if (!METRIKA_ID || !METRIKA_TOKEN) {
    return 'Сводка по сайту не настроена: на сервере не заданы METRIKA_COUNTER_ID и METRIKA_TOKEN.';
  }
  try {
    return await siteSummary(periodKey);
  } catch (e) {
    console.error('Не удалось получить сводку из Метрики:', e.message);
    return 'Не получилось забрать данные из Метрики. Подробности в логах сервера.';
  }
}

async function handleUpdate(update) {
  if (update.message && update.message.text) {
    const msg = update.message;
    if (String(msg.chat.id) !== CHAT_ID) return;
    const cmd = msg.text.trim().split(/[\s@]/)[0].toLowerCase();
    if (cmd !== '/stats' && cmd !== '/start') return;
    await tg('sendMessage', {
      chat_id: msg.chat.id,
      text: await statsText('today'),
      parse_mode: 'HTML',
      reply_markup: PERIOD_BUTTONS
    });
    return;
  }

  const cb = update.callback_query;
  if (cb && cb.message && /^stats:/.test(cb.data || '')) {
    if (String(cb.message.chat.id) !== CHAT_ID) return;
    const text = await statsText(cb.data.slice(6));
    await tg('answerCallbackQuery', { callback_query_id: cb.id });
    try {
      await tg('editMessageText', {
        chat_id: cb.message.chat.id,
        message_id: cb.message.message_id,
        text: text,
        parse_mode: 'HTML',
        reply_markup: PERIOD_BUTTONS
      });
    } catch (e) {
      /* Та же сводка повторно: Telegram отвечает «message is not modified», это не ошибка. */
      if (!/not modified/.test(e.message)) throw e;
    }
  }
}

async function handleWebhook(req, res) {
  if (req.headers['x-telegram-bot-api-secret-token'] !== WEBHOOK_SECRET) {
    res.writeHead(403);
    return res.end();
  }
  let update;
  try {
    update = JSON.parse(await readBody(req, 256 * 1024));
  } catch (e) {
    res.writeHead(400);
    return res.end();
  }
  /* Отвечаем Telegram сразу, иначе он повторит запрос, пока мы ждём Метрику. */
  res.writeHead(200);
  res.end();
  handleUpdate(update).catch(function (e) {
    console.error('Не удалось ответить в боте:', e.message);
  });
}

async function setupBot() {
  if (!BOT_TOKEN || !CHAT_ID || !WEBHOOK_SECRET || !PUBLIC_URL) return false;
  await tg('setWebhook', {
    url: PUBLIC_URL + '/api/telegram/' + WEBHOOK_SECRET,
    secret_token: WEBHOOK_SECRET,
    allowed_updates: ['message', 'callback_query']
  });
  await tg('setMyCommands', {
    commands: [{ command: 'stats', description: 'Сводка по сайту' }]
  });
  return true;
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

  if (WEBHOOK_SECRET && pathname === '/api/telegram/' + WEBHOOK_SECRET) {
    if (req.method !== 'POST') { res.writeHead(405, { Allow: 'POST' }); return res.end(); }
    return handleWebhook(req, res);
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

  setupBot().then(function (ok) {
    if (ok) console.log('  Бот: вебхук ' + PUBLIC_URL + '/api/telegram/…, команда /stats.' +
      (METRIKA_ID && METRIKA_TOKEN ? '' : ' Метрика не настроена.'));
  }).catch(function (e) {
    console.error('Не удалось подключить вебхук бота:', e.message);
  });
});
