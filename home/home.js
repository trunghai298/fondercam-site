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
    const tl = gsap.timeline({ scrollTrigger: { trigger: '#ch0', start: 'top top', end: '+=120%', scrub: 0.6, pin: '#ch0 .pin' } });
    // The canister rolls in on load (a short intro, not scroll-bound), then the scroll pulls the leader.
    gsap.to('#ch0 .canister', { x: 0, rotation: 0, duration: 1.4, ease: 'power3.out', delay: 0.2 });
    tl.to('#ch0 .leader', { scaleX: 1, ease: 'none', duration: 1 })
      .to('#ch0 .hint', { opacity: 0, duration: 0.3 }, 0)
      .to('#ch0 h1, #ch0 .lead', { y: -40, opacity: 0.2, duration: 0.6 }, 0.5);
  };

  Home.chapters.shoot = (gsap) => {
    const frames = gsap.utils.toArray('#ch1 .frame');
    gsap.set(frames, { yPercent: (i) => i * 105 });
    gsap.set('#ch1 .strip', { display: 'block', position: 'relative', aspectRatio: '3 / 2' });
    gsap.set(frames, { position: 'absolute', inset: 0 });
    const tl = gsap.timeline({ scrollTrigger: { trigger: '#ch1', start: 'top top', end: '+=160%', scrub: 0.5, pin: '#ch1 .pin', snap: { snapTo: 'labels', duration: 0.25 } } });
    tl.addLabel('f1');
    frames.forEach((f, i) => {
      if (i === 0) return;
      if (i === frames.length - 1) {
        tl.to('#ch1 .flash', { opacity: 0.9, duration: 0.05 }).call(() => Home.playShutter());
        tl.to('#ch1 .flash', { opacity: 0, duration: 0.25 });
      }
      tl.to(frames, { yPercent: `-=105`, duration: 0.5, ease: 'steps(6)' });
      tl.addLabel(`f${i + 1}`);
    });
    // Play the advance click once each time the scrub crosses a frame label (f2, f3, …), in
    // either direction. A tl.call() placed exactly at the last label — which sits at the
    // timeline's own total duration — turns out not to reliably fire in GSAP when the scrub
    // lands exactly on that boundary, so label crossings are detected on every render instead,
    // by comparing the previous and current time against each label's time. onComplete and
    // onReverseComplete are added as a guaranteed-fire backstop for that same boundary case (a
    // single large scroll jump can skip the one render that would otherwise catch it); both
    // reuse the same lastTime bookkeeping so a crossing is never counted twice.
    const frameLabelTimes = Object.entries(tl.labels).filter(([name]) => name !== 'f1').map(([, t]) => t);
    let lastTime = 0;
    const checkLabelCrossings = () => {
      const now = tl.time();
      frameLabelTimes.forEach((t) => {
        if ((lastTime < t && now >= t) || (lastTime > t && now <= t)) Home.playAdvance();
      });
      lastTime = now;
    };
    tl.eventCallback('onUpdate', checkLabelCrossings);
    tl.eventCallback('onComplete', checkLabelCrossings);
    tl.eventCallback('onReverseComplete', checkLabelCrossings);
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
      scrollTrigger: { trigger: '#ch2 .phone', start: 'center center', end: '+=220%', scrub: 0.6, pin: '#ch2 .pin' },
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
    const tl = gsap.timeline({ scrollTrigger: { trigger: '#ch3', start: 'top top', end: '+=160%', scrub: 0.6, pin: '#ch3 .pin' } });
    // The envelope slides away and the prints fan out from a stack.
    tl.from(cards, { y: 160, rotation: 0, opacity: 0, stagger: 0.12, duration: 0.5, ease: 'power2.out' })
      .to('#ch3 .envelope', { yPercent: 100, duration: 0.4 }, 0)
      .from('#ch3 .contact', { y: 60, opacity: 0, duration: 0.4 }, '>-0.1');
  };

  Home.chapters.ticket = (gsap) => {
    gsap.timeline({ scrollTrigger: { trigger: '#ch4', start: 'top 60%', end: 'top 10%', scrub: 0.5 } })
      .to('#ch4 .ticket', { yPercent: 0, y: 0, duration: 1, ease: 'steps(12)' });  // printed out line by line
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
    // The ch1 timeline calls these at each frame label and at the flash (see Home.chapters.shoot)
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
