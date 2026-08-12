/* wavy mark — "The Scream" ripple, canvas remake of the old 64-band CSS slicer.
   Each device-pixel row of the hi-res mark is drawn with a horizontal offset
   amp·sin(2π·y/λ − φ(t)); φ advances with time so the wave travels down the
   glyph. Row granularity kills the band seams, continuous phase kills the
   keyframe stepping, and the texture is our own mark (24 KB WebP) instead of
   whatever emoji font the OS ships.
   Contracts: prefers-reduced-motion → one static frame, no loop; offscreen or
   hidden tab → loop pauses; DPR capped at 2. */
(function () {
  'use strict';
  var PERIOD = 0.5;        // s per cycle — matches the old wave-x timing
  var AMP = 0.025;         // horizontal amplitude, fraction of mark height
  var WAVELENGTH = 1.0;    // one full wave per mark height
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

  function initCanvas(cv) {
    var ctx = cv.getContext('2d');
    var img = new Image();
    var raf = 0, onscreen = true;

    function layout() {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      var w = Math.round(cv.clientWidth * dpr), h = Math.round(cv.clientHeight * dpr);
      if (w && h && (cv.width !== w || cv.height !== h)) { cv.width = w; cv.height = h; }
    }

    function draw(now) {
      var W = cv.width, H = cv.height, iw = img.naturalWidth, ih = img.naturalHeight;
      if (!W || !H || !iw) return;
      var amp = AMP * H;
      var dw = iw * (H / ih);              // mark drawn full-height…
      var x0 = (W - dw) / 2;               // …centered, with the amplitude as side room
      var phase = (now / 1000 / PERIOD) * 2 * Math.PI;
      var sy = ih / H;
      ctx.clearRect(0, 0, W, H);
      for (var y = 0; y < H; y++) {
        var dx = amp * Math.sin(2 * Math.PI * y / (WAVELENGTH * H) - phase);
        ctx.drawImage(img, 0, y * sy, iw, sy, x0 + dx, y, dw, 1);
      }
    }

    function still() { layout(); draw(0); }

    function tick(now) {
      draw(now);
      raf = requestAnimationFrame(tick);
    }
    function run() {
      cancelAnimationFrame(raf); raf = 0;
      if (reduced.matches) { still(); return; }
      if (onscreen && !document.hidden) { layout(); raf = requestAnimationFrame(tick); }
      else still();
    }

    img.decode ? img.decode().then(run).catch(function () {}) : (img.onload = run);
    img.src = cv.getAttribute('data-src');

    new IntersectionObserver(function (entries) {
      onscreen = entries[0].isIntersecting; run();
    }).observe(cv);
    document.addEventListener('visibilitychange', run);
    reduced.addEventListener ? reduced.addEventListener('change', run) : reduced.addListener(run);
    if (window.ResizeObserver) new ResizeObserver(run).observe(cv);
  }

  // Idempotent scan — inits any not-yet-initialised wave-mark canvas. Exposed so scripts that
  // render canvases dynamically (guide.js panels) can init them after they hit the DOM.
  function init(root) {
    (root || document).querySelectorAll('canvas.wave-mark:not([data-wave-init])').forEach(function (cv) {
      cv.setAttribute('data-wave-init', '1');
      initCanvas(cv);
    });
  }
  window.SFWave = { init: init };
  init();
})();
