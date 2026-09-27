(() => {
  const canvas = document.querySelector('.grain');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w = 0, h = 0, frame = 0, timer = 0;

  function size() {
    // Half resolution: the grain is soft anyway, and it keeps the phone cool.
    w = canvas.width = Math.ceil(innerWidth / 2);
    h = canvas.height = Math.ceil(innerHeight / 2);
  }

  function draw() {
    const img = ctx.createImageData(w, h);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) {
      const v = (Math.random() * 255) | 0;
      d[i] = d[i + 1] = d[i + 2] = v;
      d[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }

  function loop() {
    // About 12 fps: film grain flickers, it doesn't shimmer.
    if (!document.hidden && frame++ % 5 === 0) draw();
    timer = requestAnimationFrame(loop);
  }

  size();
  draw();
  addEventListener('resize', () => { size(); draw(); });
  if (!still) timer = requestAnimationFrame(loop);
})();
