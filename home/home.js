(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const Home = { motion: false, chapters: {} };
  window.FonderHome = Home;

  const noop = () => {};
  Home.chapters = { load: noop, shoot: noop, develop: noop, prints: noop, ticket: noop };

  function start() {
    const { gsap, ScrollTrigger } = window;
    if (reduce || !gsap || !ScrollTrigger) return;   // End states stay; the page reads as a static page.
    gsap.registerPlugin(ScrollTrigger);
    Home.motion = true;
    document.documentElement.classList.add('motion');
    for (const build of Object.values(Home.chapters)) build(gsap);
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
      if (i === frames.length - 1) tl.to('#ch1 .flash', { opacity: 0.9, duration: 0.05 }).to('#ch1 .flash', { opacity: 0, duration: 0.25 });
      tl.to(frames, { yPercent: `-=105`, duration: 0.5, ease: 'steps(6)' });
      tl.addLabel(`f${i + 1}`);
    });
  };

  Home.chapters.develop = (gsap) => {
    const tl = gsap.timeline({ scrollTrigger: { trigger: '#ch2', start: 'top top', end: '+=140%', scrub: 0.8, pin: '#ch2 .pin' } });
    // Blank paper → the image slowly comes up, the latent grey fading as the colour rises.
    tl.to('#ch2 .print-developed', { opacity: 1, duration: 0.6, ease: 'power2.inOut' }, 0.35)
      .to('#ch2 .print-latent', { opacity: 0, duration: 0.3 }, 0.7)
      .fromTo('#ch2 .tray', { rotation: -0.6 }, { rotation: 0.6, duration: 1, ease: 'sine.inOut', yoyo: true, repeat: 1 }, 0);
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
    window.ScrollTrigger.create({ trigger: '#ch1', start: 'top top', end: '+=160%',
      onUpdate: (self) => { if (on && Math.abs(self.getVelocity()) > 50) { advance.currentTime = 0; advance.play().catch(() => {}); } } });
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
})();
