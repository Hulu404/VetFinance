/* ВетФинанс — общий скрипт всех страниц сайта.
   Подключается на index.html, privacy.html, consent.html, offer.html.
   Отвечает за: cookie-согласие, Яндекс Метрику, возврат с юридических страниц,
   адрес обработчика заявки. */
(function (w, d) {
  'use strict';

  /* Номер счётчика Яндекс Метрики. Пока пусто — Метрика не загружается вовсе.
     Впишите номер (только цифры), и счётчик включится после согласия посетителя. */
  var METRIKA_ID = '';

  /* Куда форма на главной отправляет заявку. Обрабатывается в server.js. */
  var LEAD_ENDPOINT = '/api/lead';

  var CK_KEY = 'vf-ck';

  w.VF = {
    leadEndpoint: LEAD_ENDPOINT,
    /* Цель Метрики. Безопасно вызывать, даже если счётчик не подключён. */
    goal: function (name) {
      if (METRIKA_ID && typeof w.ym === 'function') w.ym(METRIKA_ID, 'reachGoal', name);
    }
  };

  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); }
    catch (e) { return null; }
  }

  /* ---------- Яндекс Метрика ---------- */
  function loadMetrika() {
    if (!METRIKA_ID || w.ym) return;
    (function (m, e, t, r, i, k, a) {
      m[i] = m[i] || function () { (m[i].a = m[i].a || []).push(arguments); }; m[i].l = 1 * new Date();
      k = e.createElement(t); a = e.getElementsByTagName(t)[0]; k.async = 1; k.src = r;
      a.parentNode.insertBefore(k, a);
    })(w, d, 'script', 'https://mc.yandex.ru/metrika/tag.js', 'ym');
    w.ym(METRIKA_ID, 'init', { clickmap: true, trackLinks: true, accurateTrackBounce: true });
  }

  /* ---------- Cookie-уведомление ---------- */
  var CK_CSS =
    '.vf-ck{position:fixed;left:16px;right:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:60;' +
    'max-width:620px;margin:0 auto;background:#141013;color:#E9E2E6;border-radius:18px;padding:16px 18px;' +
    'border:1px solid #3A3036;display:flex;gap:16px;align-items:center;box-shadow:0 12px 40px rgba(0,0,0,.25);' +
    "font-family:'Onest',-apple-system,system-ui,sans-serif;font-size:14.5px;line-height:1.45}" +
    '.vf-ck[hidden]{display:none}.vf-ck p{margin:0}.vf-ck a{color:#FF8AAC}' +
    '.vf-ck-b{display:flex;gap:8px;flex:none}' +
    '.vf-ck button{font-family:inherit;font-size:14px;font-weight:600;border:0;border-radius:11px;padding:10px 14px;cursor:pointer}' +
    '.vf-ck-no{background:#2E262B;color:#E9E2E6}.vf-ck-yes{background:#fff;color:#C22B55}' +
    '@media (max-width:600px){.vf-ck{flex-direction:column;align-items:stretch}.vf-ck-b button{flex:1}}';

  /* Ссылка «Подробнее» ведёт в раздел про cookie в политике: со страницы политики — якорем. */
  function privacyHref() {
    var onPrivacy = /privacy\.html$/.test(location.pathname) || /\/privacy$/.test(location.pathname);
    return (onPrivacy ? '' : 'privacy.html') + '#s10';
  }

  function cookieBanner() {
    var decided = store(CK_KEY);
    if (decided === 'yes') loadMetrika();
    if (decided) return;

    var css = d.createElement('style');
    css.textContent = CK_CSS;
    d.head.appendChild(css);

    var box = d.createElement('div');
    box.className = 'vf-ck';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-live', 'polite');
    box.setAttribute('aria-label', 'Файлы cookie');
    box.innerHTML =
      '<p>Мы используем технические cookie. С вашего разрешения также включим Яндекс Метрику ' +
      'для обезличенной статистики. <a href="' + privacyHref() + '">Подробнее</a></p>' +
      '<div class="vf-ck-b"><button type="button" class="vf-ck-no">Только необходимые</button>' +
      '<button type="button" class="vf-ck-yes">Разрешить</button></div>';
    d.body.appendChild(box);

    function decide(val) {
      store(CK_KEY, val);
      box.hidden = true;
      if (val === 'yes') loadMetrika();
    }
    box.querySelector('.vf-ck-yes').addEventListener('click', function () { decide('yes'); });
    box.querySelector('.vf-ck-no').addEventListener('click', function () { decide('no'); });
  }

  /* ---------- Возврат на главную ----------
     С формы на юридические страницы уходят ссылки вида consent.html?r=form.
     Тогда «На главную» возвращает прямо к форме, а не в начало страницы. */
  function returnLinks() {
    if (location.search.indexOf('r=form') === -1) return;
    d.querySelectorAll('a[href="index.html"]').forEach(function (a) { a.href = 'index.html#form'; });
  }

  function init() { cookieBanner(); returnLinks(); }

  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', init);
  else init();
})(window, document);
