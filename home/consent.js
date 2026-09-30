// Google Analytics, only after the visitor says OK. Until then — and always after "No thanks" —
// the page makes no request to Google at all. The choice lives in this browser's localStorage
// under one key for the whole site; if storage is blocked the banner simply asks again next time,
// and nothing is counted until OK.
//
// The measurement id is also in config.json (`ga4`); tools/build_home.py --check keeps them equal.
(() => {
  const ID = 'G-XY9H5LMRP0';
  const KEY = 'fonder-analytics';

  // What to do on this visit: 'load' (agreed), 'none' (declined), or 'ask' (no answer yet).
  const decide = (storage) => {
    let v = null;
    try { v = storage ? storage.getItem(KEY) : null; } catch (e) { /* blocked: no answer */ }
    return v === 'yes' ? 'load' : v === 'no' ? 'none' : 'ask';
  };
  // An event, only when analytics is running (after OK). Otherwise nothing — no queue is kept.
  const track = (name, params) => { if (typeof window.gtag === 'function') window.gtag('event', name, params || {}); };
  window.FonderConsent = { id: ID, key: KEY, decide, track };

  function load() {
    if (window.gtag) return;
    const s = document.createElement('script');
    s.async = true;
    s.src = `https://www.googletagmanager.com/gtag/js?id=${ID}`;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', ID, { anonymize_ip: true, page_lang: document.documentElement.lang === 'vi' ? 'vi' : 'en' });
  }

  function remember(v) {
    try { window.localStorage.setItem(KEY, v); } catch (e) { /* blocked: ask again next visit */ }
  }

  // The banner's look, added only when it is shown, so no page pays for it otherwise. Inside the
  // homepage's `.bars` stack it sits with the language bar; elsewhere it is fixed on its own.
  const CSS = `.consent-bar:not([hidden]){position:fixed;left:16px;right:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:60;
display:flex;gap:10px 14px;align-items:center;flex-wrap:wrap;background:#efe6d6;color:#1f1a14;padding:12px 14px;border-radius:12px;
box-shadow:0 10px 30px rgba(0,0,0,.35);font:400 15px/1.4 "Be Vietnam Pro",ui-sans-serif,system-ui,-apple-system,sans-serif}
.bars .consent-bar:not([hidden]){position:static}
.consent-bar p{margin:0;flex:1 1 200px}
.consent-bar button{min-height:40px;font:inherit;border-radius:99px;cursor:pointer}
.consent-yes{padding:0 18px;background:#1f1a14;color:#fffdf7;border:0}
.consent-no{padding:0 6px;background:none;border:0;color:#1f1a14;text-decoration:underline}
.consent-bar button:focus-visible{outline:2px solid #9a6a2c;outline-offset:3px}`;

  function ask() {
    const bar = document.querySelector('.consent-bar');
    if (!bar) return;
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);
    bar.hidden = false;
    bar.querySelector('.consent-yes').addEventListener('click', () => { remember('yes'); bar.hidden = true; load(); rewatch(); });
    bar.querySelector('.consent-no').addEventListener('click', () => { remember('no'); bar.hidden = true; });
  }

  // The homepage's events. Listeners attach on every visit and call `track`, which is a no-op
  // until the visitor has said OK. An event on a link that leaves the page goes out with gtag's own
  // flush as the page is hidden (a beacon), as GA4's outbound-link tracking does.
  const HOSTS = { 'instagram.com': 'instagram', 'threads.com': 'threads', 'testflight.apple.com': 'testflight', 'apps.apple.com': 'appstore' };
  let rewatch = () => {};
  function wireEvents() {
    const on = (sel, type, fn, once) => document.querySelectorAll(sel).forEach((el) => el.addEventListener(type, fn, { once: !!once }));
    const action = document.querySelector('.action');
    on('.action a', 'click', (e) => {
      const host = new URL(e.currentTarget.href).hostname.replace(/^www\./, '');
      const target = HOSTS[host];
      if (target) track('action_click', { target, stage: action.dataset.stage });
    });
    on('.compare input', 'input', () => track('slider_touch'), true);
    on('.lang-bar-yes', 'click', () => track('lang_bar_accept'));
    if (document.querySelector('main .chapter')) {
      // $= matches both languages' pages: /diary/ and /vi/diary/, /recipes/ and /vi/recipes/.
      on('.site-nav a[href$="/diary/"]', 'click', () => track('diary_click', { from: 'header' }));
      on('.site-footer a[href$="/diary/"]', 'click', () => track('diary_click', { from: 'footer' }));
      on('main a[href*="/diary/"]', 'click', () => track('diary_click', { from: 'home_block' }));
      on('.site-nav a[href$="/recipes/"]', 'click', () => track('recipes_click', { from: 'header' }));
      on('.site-footer a[href$="/recipes/"]', 'click', () => track('recipes_click', { from: 'footer' }));
      on('main a[href$="/recipes/"]', 'click', () => track('recipes_click', { from: 'teaser' }));
    }
    // A chapter counts as seen when any of it crosses the middle of the screen — pinned chapters are
    // several screens tall, so a share of their area would never be reached. Only a sent view retires a
    // chapter; saying OK re-observes the rest, so the chapter on screen at that moment counts.
    const chapters = [...document.querySelectorAll('section.chapter[data-chapter]')];
    if (!chapters.length || !('IntersectionObserver' in window)) return;
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (!e.isIntersecting || typeof window.gtag !== 'function') return;
      io.unobserve(e.target);
      e.target.dataset.seen = '1';
      track('chapter_view', { chapter: e.target.dataset.chapter });
    }), { rootMargin: '-40% 0px -40% 0px' });
    chapters.forEach((c) => io.observe(c));
    rewatch = () => chapters.filter((c) => !c.dataset.seen).forEach((c) => { io.unobserve(c); io.observe(c); });
  }

  function run() {
    wireEvents();
    let storage = null;
    try { storage = window.localStorage; } catch (e) { /* blocked */ }
    const d = decide(storage);
    if (d === 'load') load();
    else if (d === 'ask') ask();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
