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
    // document.documentElement.classList.add('motion'); // enabled in Task 6
    for (const build of Object.values(Home.chapters)) build(gsap);
    let t = 0;
    addEventListener('resize', () => { clearTimeout(t); t = setTimeout(() => ScrollTrigger.refresh(), 200); });
  }

  // Chapter builders are assigned below this line by later tasks, before start() runs.
  // (Tasks 6–8 replace the no-ops.)

  document.addEventListener('DOMContentLoaded', start);
})();
