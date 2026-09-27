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

  document.addEventListener('DOMContentLoaded', start);

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
