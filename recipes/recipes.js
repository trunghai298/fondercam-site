// The recipes page's own behaviour: every before/after slider (the homepage's component,
// but many of them), and the one-scene viewer. Analytics stays in /home/consent.js, which
// already watches `.compare input` and every `section.chapter[data-chapter]` on this page.
(() => {
  const ready = (fn) => (document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', fn) : fn());

  // Each slider only sets its own --split, exactly as the homepage's single one does.
  ready(() => {
    document.querySelectorAll('.compare').forEach((box) => {
      const input = box.querySelector('input');
      if (!input) return;
      const set = () => box.style.setProperty('--split', `${input.value}%`);
      input.addEventListener('input', set);
      set();
    });
  });

  // The scene viewer: the frame stays put, the chip swaps which develop is on it.
  ready(() => {
    const img = document.getElementById('scene-img');
    const caption = document.getElementById('scene-caption');
    const chips = [...document.querySelectorAll('.scene-chip')];
    if (!img || !chips.length) return;
    const select = (chip) => {
      chips.forEach((c) => { c.classList.toggle('is-on', c === chip); c.setAttribute('aria-pressed', String(c === chip)); });
      img.srcset = chip.dataset.srcset;
      img.src = chip.dataset.img;
      caption.textContent = chip.dataset.caption || chip.dataset.label;
      if (window.FonderConsent) window.FonderConsent.track('scene_pick', { look: chip.dataset.label });
    };
    chips.forEach((chip) => chip.addEventListener('click', () => select(chip)));

    // A catalogue card's "see it on the shared scene" link selects its recipe up here.
    document.querySelectorAll('.card-scene[data-scene]').forEach((a) => {
      a.addEventListener('click', () => {
        const chip = chips.find((c) => c.dataset.slug === a.dataset.scene);
        if (chip) select(chip);
      });
    });
  });
  // The same probe home.js carries, so tools/shots.py --overflow works on this page too.
  if (location.search.includes('probe=overflow')) {
    addEventListener('load', () => setTimeout(() => {
      const bad = [...document.querySelectorAll('body *')].filter((e) => e.scrollWidth > e.clientWidth + 1
        && getComputedStyle(e).overflowX === 'visible' && e.clientWidth > 0).map((e) => `${e.tagName}.${e.className}`);
      document.body.setAttribute('data-overflow', bad.length ? bad.join(',') : 'none');
    }, 500));
  }
})();
