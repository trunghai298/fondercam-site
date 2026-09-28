(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const Home = { motion: false, chapters: {} };
  window.FonderHome = Home;

  const noop = () => {};
  Home.chapters = { load: noop, shoot: noop, develop: noop, prints: noop, ticket: noop };
  // Replaced with real players once the sound toggle wires up (only when motion is on); until
  // then, and always when sound is off, these are safe no-ops.
  Home.playAdvance = noop;
  Home.playShutter = noop;

  function start() {
    const { gsap, ScrollTrigger } = window;
    if (reduce || !gsap || !ScrollTrigger) return;   // End states stay; the page reads as a static page.
    gsap.registerPlugin(ScrollTrigger);
    // The `motion` class goes on *before* the builders run, not after: several chapters use
    // gsap.to()/gsap.from() tweens whose start or end value is the element's live CSS at
    // ScrollTrigger-creation time (e.g. the #ch2 phone's frame and state-layer opacities, which
    // only differ between the motion and no-motion CSS). Adding the class after building would make
    // those tweens capture the no-motion values and animate nowhere. Each builder still runs in
    // its own try/catch, and if any of them throws, everything is rolled back — the class comes
    // off and every ScrollTrigger already created is killed — so a broken chapter never leaves
    // the page half-wired; it falls back to its plain no-motion end state instead.
    document.documentElement.classList.add('motion');
    let ok = true;
    for (const build of Object.values(Home.chapters)) {
      try {
        build(gsap);
      } catch (e) {
        ok = false;
      }
    }
    if (!ok) {
      document.documentElement.classList.remove('motion');
      ScrollTrigger.getAll().forEach((st) => st.kill());
      return;
    }
    Home.motion = true;
    let t = 0;
    addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => ScrollTrigger.refresh(), 200); });
  }

  // Chapter builders are assigned below this line by later tasks, before start() runs.
  // (Tasks 6–8 replace the no-ops.)

  Home.langBar = ({ path, navigatorLanguages, storage }) => {
    if (path.startsWith('/vi')) return 'hide';
    if (!(navigatorLanguages || []).some((l) => l.toLowerCase().startsWith('vi'))) return 'hide';
    let dismissed = null;
    try { dismissed = storage.getItem('fonder-lang-bar'); } catch (e) { /* storage blocked: still offer, never break */ }
    return dismissed ? 'hide' : 'show';
  };

  document.addEventListener('DOMContentLoaded', () => {
    const bar = document.querySelector('.lang-bar');
    if (!bar) return;
    let storage = null;
    try { storage = window.localStorage; } catch (e) { storage = { getItem: () => null, setItem() {} }; }
    if (Home.langBar({ path: location.pathname, navigatorLanguages: navigator.languages, storage }) !== 'show') return;
    bar.hidden = false;
    const remember = () => { try { storage.setItem('fonder-lang-bar', 'dismissed'); } catch (e) {} };
    bar.querySelector('.lang-bar-no').addEventListener('click', () => { remember(); bar.hidden = true; });
    bar.querySelector('.lang-bar-yes').addEventListener('click', remember);
  });

  Home.chapters.load = (gsap) => {
    const tl = gsap.timeline({ scrollTrigger: { trigger: '#ch0', start: 'top top', end: '+=70%', scrub: 0.6, pin: '#ch0 .pin' } });
    // The canister rolls in on load (a short intro, not scroll-bound), then the scroll pulls the leader.
    gsap.to('#ch0 .canister', { x: 0, rotation: 0, duration: 1.4, ease: 'power3.out', delay: 0.2 });
    tl.to('#ch0 .leader', { scaleX: 1, ease: 'none', duration: 1 })
      .to('#ch0 .hint', { opacity: 0, duration: 0.3 }, 0)
      .to('#ch0 h1, #ch0 .lead', { y: -40, opacity: 0.2, duration: 0.6 }, 0.5);
  };

  Home.chapters.shoot = (gsap) => {
    // Fonder's camera in Still mode. Timeline units: the recipe strip comes up (1) and steps
    // through three recipes (2, 3, 4) to Still Air 100; the controls panel opens (5.3) on White
    // balance, which goes from the recipe's Daylight to 3200K (7) and 7000K (8); the Grain page
    // takes grain from 30 to 75 (9.2); the panel closes and the shutter fires (11), the frame
    // dropping into the recents tile. Only opacity and transforms are tweened; the readouts are
    // text, written from onUpdate. The recipes and their white balance are the app's catalogue.
    const q = (sel) => document.querySelector(`#ch1 ${sel}`);
    const all = (sel) => gsap.utils.toArray(`#ch1 ${sel}`);
    const cam = q('.cam');
    const L = { daylight: cam.dataset.daylight, preset: cam.dataset.preset, fixed: cam.dataset.fixed };
    const RECIPES = [
      { name: 'Summer Chrome', film: 'Daylight Cine', wb: 'AWB −200K', at: 0 },
      { name: 'Ha Noi Chrome', film: 'Harbour Cool', wb: 'AWB −100K', at: 2 },
      { name: 'Amber 400', film: 'Amber Neg', wb: 'AWB −300K', at: 3 },
      { name: 'Still Air 100', film: 'Memoir Chrome', wb: L.daylight, at: 4 },
    ];
    const WB = [   // Still Air's own Daylight preset, then the K choice at two kelvins
      { at: 0, hud: null, big: L.daylight, cap: L.preset, kel: '' },
      { at: 7, hud: '3200K', big: '3200K', cap: L.fixed, kel: '3200K' },
      { at: 8, hud: '7000K', big: '7000K', cap: L.fixed, kel: '7000K' },
    ];
    const GRAIN_AT = 9.2, GRAIN_LEN = 0.6;
    const TRACK_STEP = 100 / 6;                 // the strip is six 82-pt columns
    const trackX = (i) => 32.52 - i * TRACK_STEP;   // tile i centred in the sheet
    const STRIP_INDEX = [0, 1, 2, 4];           // where each recipe sits on the strip
    const els = {
      name: q('.cam-name'), film: q('.cam-film'), wb: q('.cam-wb'), sheetName: q('.sheet-name'),
      big: q('.wb-big'), cap: q('.wb-cap'), kel: q('.kel-v'), grain: q('.gr-v'),
    };
    const setText = (el, s) => { if (el.textContent !== s) el.textContent = s; };
    const last = (list, t) => list.reduce((cur, s) => (t >= s.at ? s : cur), list[0]);
    let tl = null;
    const update = () => {
      if (!tl) return;
      const t = tl.time();
      const r = last(RECIPES, t), w = last(WB, t);
      setText(els.name, r.name); setText(els.sheetName, r.name); setText(els.film, r.film);
      setText(els.wb, w.hud || r.wb);
      setText(els.big, w.big); setText(els.cap, w.cap); setText(els.kel, w.kel);
      const g = Math.min(Math.max((t - GRAIN_AT) / GRAIN_LEN, 0), 1);
      setText(els.grain, String(Math.round(30 + 45 * g)));
    };
    // Where the scrub crosses a step, the tick of a control changing (and the shutter at 11).
    const ticks = [2, 3, 4, 7, 8];
    let lastTime = 0;
    const sounds = () => {
      const now = tl.time();
      const crossed = (at) => (lastTime < at && now >= at) || (lastTime > at && now <= at);
      ticks.forEach((at) => { if (crossed(at)) Home.playAdvance(); });
      if (crossed(11)) Home.playShutter();
      lastTime = now;
    };
    gsap.set(q('.cam-sheet'), { yPercent: 105 });
    gsap.set(q('.cam-panel'), { yPercent: 110 });
    gsap.set(q('.sheet-track'), { xPercent: trackX(0) });
    gsap.set(q('.kel-pos'), { xPercent: 40 });   // Daylight's 5500 K on the 2500–10000 K bar
    gsap.set(q('.gr-pos'), { xPercent: 30 });
    tl = gsap.timeline({
      scrollTrigger: { trigger: '#ch1 .phone', start: 'center center', end: '+=160%', scrub: 0.6, pin: '#ch1 .pin' },
      onUpdate: () => { update(); sounds(); },
    });
    const vf = all('.cam-vf img.vf');
    const vfIn = (n, at, d = 0.35) => tl.to(vf.filter((img) => img.classList.contains(`vf-${n}`)), { opacity: 1, duration: d }, at);
    // The recipe strip.
    tl.to(q('.cam-controls'), { opacity: 0, duration: 0.3 }, 1)
      .to(q('.cam-sheet'), { yPercent: 0, duration: 0.4, ease: 'power2.out' }, 1);
    const tiles = all('.sw');
    RECIPES.slice(1).forEach((r, k) => {
      const i = k + 1, at = r.at;
      const from = tiles[STRIP_INDEX[i - 1]], to = tiles[STRIP_INDEX[i]];
      vfIn(i + 1, at);
      tl.to(q('.sheet-track'), { xPercent: trackX(STRIP_INDEX[i]), duration: 0.35, ease: 'power2.inOut' }, at)
        .to(from.querySelectorAll('.sw-ring, .sw-on'), { opacity: 0, duration: 0.2 }, at)
        .to(from.querySelector('.sw-dim'), { opacity: 1, duration: 0.2 }, at)
        .to(to.querySelectorAll('.sw-ring, .sw-on'), { opacity: 1, duration: 0.2 }, at + 0.15)
        .to(to.querySelector('.sw-dim'), { opacity: 0, duration: 0.2 }, at + 0.15)
        .to(q(`.can-${i}`), { opacity: 0, duration: 0.3 }, at)
        .to(q(`.can-${i + 1}`), { opacity: 1, duration: 0.3 }, at);
    });
    tl.to(q('.cam-sheet'), { yPercent: 105, duration: 0.4, ease: 'power2.in' }, 4.8);
    // The controls panel: the grid, then White balance.
    // The panel is sized for White balance; the shorter pages sit lower, their empty foot off
    // the bottom of the screen (the app's panel is sized to its page).
    tl.to(q('.cam-panel'), { yPercent: 24.7, duration: 0.4, ease: 'power2.out' }, 5.3)
      .to(q('.cam-panel'), { yPercent: 0, duration: 0.3, ease: 'power2.inOut' }, 6)
      .to(q('.pg-grid'), { opacity: 0, duration: 0.25 }, 6)
      .to(q('.pg-wb'), { opacity: 1, duration: 0.25 }, 6.1);
    vfIn(5, 7);
    tl.to(q('.wb-sun').querySelectorAll('.on, .dot-on'), { opacity: 0, duration: 0.2 }, 7)
      .to(q('.wb-k').querySelectorAll('.on, .dot-on'), { opacity: 1, duration: 0.2 }, 7)
      .to(q('.kel-pos'), { xPercent: (3200 - 2500) / 75, duration: 0.35, ease: 'power2.inOut' }, 7)
      .to(q('.kel-pos'), { xPercent: (7000 - 2500) / 75, duration: 0.45, ease: 'power2.inOut' }, 8);
    vfIn(6, 8, 0.45);
    // Grain.
    tl.to(q('.pg-wb'), { opacity: 0, duration: 0.25 }, 8.8)
      .to(q('.pg-grain'), { opacity: 1, duration: 0.25 }, 8.9)
      .to(q('.cam-panel'), { yPercent: 46, duration: 0.3, ease: 'power2.inOut' }, 8.8)
      .to(q('.gr-fill'), { scaleX: 0.75, duration: GRAIN_LEN, ease: 'none' }, GRAIN_AT)
      .to(q('.gr-pos'), { xPercent: 75, duration: GRAIN_LEN, ease: 'none' }, GRAIN_AT);
    vfIn(7, GRAIN_AT, GRAIN_LEN);
    // Close, and take the picture.
    tl.to(q('.cam-panel'), { yPercent: 110, duration: 0.4, ease: 'power2.in' }, 10.2)
      .to(q('.cam-controls'), { opacity: 1, duration: 0.3 }, 10.45)
      .to(q('.vf-flash'), { opacity: 0.85, duration: 0.05 }, 11)
      .to(q('.vf-flash'), { opacity: 0, duration: 0.3 }, 11.05)
      .to(q('.vf-snap'), { opacity: 1, duration: 0.05 }, 11)
      .to(q('.vf-snap'), { opacity: 0, duration: 0.4 }, 11.4)
      .to(q('.cam-shutter'), { scale: 0.92, duration: 0.08 }, 11)
      .to(q('.cam-shutter'), { scale: 1, duration: 0.15 }, 11.1)
      .to(q('.cam-shot'), { opacity: 1, duration: 0.02 }, 11.1)
      .to(q('.cam-shot'), { xPercent: -38.9, yPercent: 73, scale: 0.127, duration: 0.6, ease: 'power2.in' }, 11.15)
      .to(q('.cam-recent .rc-new'), { opacity: 1, duration: 0.15 }, 11.7)
      .to(q('.cam-shot'), { opacity: 0, duration: 0.15 }, 11.75)
      .to({}, { duration: 1.2 }, 11.9);
    update();
  };

  Home.chapters.develop = (gsap) => {
    // Fonder's Developing screen on the phone. Timeline units: 0–10 develops the roll (the
    // percentage, the stage bar and the frames, one by one), 10–10.6 swaps to the Developed
    // screen, and the rest holds it. Only opacity and transforms are tweened; the counters are
    // text, written from onUpdate.
    const q = (sel) => document.querySelector(`#ch2 ${sel}`);
    const app = q('.app');
    const total = Number(app.dataset.total);
    const pct = q('.app-pct');
    const frameLine = q('.app-frameline');
    const footLine = q('.f-dev');
    const pad = (n) => String(n).padStart(2, '0');
    const fillTpl = (el, n) => { el.textContent = el.dataset.tpl.replace('{n}', pad(n)).replace('{total}', total); };
    const DEV = 10;
    let shown = -1;
    let tl = null;
    const update = () => {
      if (!tl) return;   // ScrollTrigger can render the timeline while it is still being created.
      const p = Math.min(Math.max(tl.time() / DEV, 0), 1);
      const pc = Math.round(p * 100);
      if (pc === shown) return;
      shown = pc;
      pct.textContent = pc;
      const n = Math.min(total, Math.floor(p * total) + 1);
      fillTpl(frameLine, n);
      fillTpl(footLine, n);
    };
    tl = gsap.timeline({
      scrollTrigger: { trigger: '#ch2 .phone', start: 'center center', end: '+=120%', scrub: 0.6, pin: '#ch2 .pin' },
      onUpdate: update,
    });
    tl.to('#ch2 .app-bar-fill', { scaleX: 1, duration: DEV, ease: 'none' }, 0);
    // Stage tabs: the amber layer crossfades from DEVELOP to FIX to SCAN.
    tl.to('#ch2 .t-develop', { opacity: 0, duration: 0.2 }, DEV * 0.5)
      .to('#ch2 .t-fix', { opacity: 1, duration: 0.2 }, DEV * 0.5)
      .to('#ch2 .t-fix', { opacity: 0, duration: 0.2 }, DEV * 0.8)
      .to('#ch2 .t-scan', { opacity: 1, duration: 0.2 }, DEV * 0.8);
    // Each frame: dark numbered slot -> faint latent image -> full, then its number turns amber.
    const step = DEV / total;
    gsap.utils.toArray('#ch2 .app-frame').forEach((frame, i) => {
      const at = i * step;
      const img = frame.querySelector('img');
      tl.to(img, { opacity: 0.3, duration: step * 0.3, ease: 'none' }, at)
        .to(img, { opacity: 1, duration: step * 0.55, ease: 'power1.in' }, at + step * 0.35)
        .to(frame.querySelector('.fn-on'), { opacity: 1, duration: step * 0.1 }, at + step * 0.9)
        .to(frame.querySelector('.fn-dim'), { opacity: 0, duration: step * 0.1 }, at + step * 0.9);
    });
    // Developed: status, count, meta, note and footer swap; the stage tabs go.
    tl.to('#ch2 :is(.st-dev,.c-dev,.m-dev,.n-dev,.f-dev,.app-tabs)', { opacity: 0, duration: 0.3 }, DEV + 0.1)
      .to('#ch2 :is(.st-done,.c-done,.m-done,.n-done,.f-done)', { opacity: 1, duration: 0.3 }, DEV + 0.3)
      .to({}, { duration: 1.4 }, DEV + 0.6);
    update();
  };

  Home.chapters.prints = (gsap) => {
    const cards = gsap.utils.toArray('#ch3 .print-card');
    const tl = gsap.timeline({ scrollTrigger: { trigger: '#ch3', start: 'top top', end: '+=100%', scrub: 0.6, pin: '#ch3 .pin' } });
    // The envelope slides away and the prints fan out from a stack.
    tl.from(cards, { y: 160, rotation: 0, opacity: 0, stagger: 0.12, duration: 0.5, ease: 'power2.out' })
      .to('#ch3 .envelope', { yPercent: 100, duration: 0.4 }, 0)
      .from('#ch3 .contact', { y: 60, opacity: 0, duration: 0.4 }, '>-0.1');
  };

  Home.chapters.ticket = (gsap) => {
    // The ticket feeds out from under the printer, gliding with the scroll.
    gsap.timeline({ scrollTrigger: { trigger: '#ch4', start: 'top 85%', end: 'bottom bottom', scrub: 1 } })
      .to('#ch4 .ticket', { yPercent: 0, y: 0, duration: 1, ease: 'power1.out' });
  };

  // Chapter images load as their chapter approaches — independent of motion/Reduce Motion,
  // since it's about network weight, not animation. Each image starts `hidden` (with a
  // placeholder src) so no-JS visitors only ever see the <noscript> twin's real image.
  // Once this script runs, though, it un-hides them straight away — a `hidden` (display:none)
  // element has no geometry, so IntersectionObserver could never detect it coming into view.
  // What stays deferred until the swap is the real network fetch (the data-src -> src swap).
  // Registered *before* `start()` below: start() builds the ScrollTriggers that pin each
  // chapter, and those measure real layout — if the lazy images were still `hidden` (zero box)
  // at that point, the pins would measure the wrong heights.
  document.addEventListener('DOMContentLoaded', () => {
    const lazyImages = [...document.querySelectorAll('img[data-src]')];
    if (!lazyImages.length) return;
    lazyImages.forEach((img) => { img.hidden = false; });
    let refreshTimer = null;
    const requestRefresh = () => {
      if (!Home.motion || !window.ScrollTrigger) return;
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => window.ScrollTrigger.refresh(), 150);
    };
    const swap = (img) => {
      img.addEventListener('load', requestRefresh, { once: true });
      img.src = img.dataset.src;
      img.removeAttribute('data-src');
    };
    if (!('IntersectionObserver' in window)) {
      lazyImages.forEach(swap);
      return;
    }
    const io = new IntersectionObserver((entries, obs) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        swap(entry.target);
        obs.unobserve(entry.target);
      });
    }, { rootMargin: '100% 0px' });
    lazyImages.forEach((img) => io.observe(img));
  });

  document.addEventListener('DOMContentLoaded', start);

  // Sound toggle: only offered once motion (and start()) has run, so it must be registered after start().
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.querySelector('.sound-toggle');
    if (!btn || !Home.motion) return;              // No motion, no sound cues.
    btn.hidden = false;
    const shutter = new Audio('/img/home/sfx/shutter.mp3');
    const advance = new Audio('/img/home/sfx/advance.mp3');
    let on = false;
    btn.addEventListener('click', () => {
      on = !on;
      btn.setAttribute('aria-pressed', String(on));
      btn.textContent = on ? btn.dataset.on : btn.dataset.off;
      if (on) shutter.play().catch(() => {});      // The click itself unlocks audio.
    });
    // The ch1 timeline calls these as the scrub crosses a control change and the shutter (see Home.chapters.shoot)
    // instead of restarting the clip on every scroll tick, which used to make it stutter.
    Home.playAdvance = () => { if (on) { advance.currentTime = 0; advance.play().catch(() => {}); } };
    Home.playShutter = () => { if (on) { shutter.currentTime = 0; shutter.play().catch(() => {}); } };
  });

  // The slider works with or without motion: it only sets a CSS variable.
  document.addEventListener('DOMContentLoaded', () => {
    const box = document.querySelector('.compare');
    const input = box && box.querySelector('input');
    if (!input) return;
    const set = () => box.style.setProperty('--split', `${input.value}%`);
    input.addEventListener('input', set);
    set();
  });

  if (location.search.includes('probe=overflow')) {
    addEventListener('load', () => setTimeout(() => {
      const bad = [...document.querySelectorAll('body *')].filter((e) => e.scrollWidth > e.clientWidth + 1
        && getComputedStyle(e).overflowX === 'visible' && e.clientWidth > 0).map((e) => `${e.tagName}.${e.className}`);
      document.body.setAttribute('data-overflow', bad.length ? bad.join(',') : 'none');
    }, 500));
  }
})();
