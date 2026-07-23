<script setup lang="ts">
import { onMounted } from 'vue'

// Honor reduced-motion for the SVG's SMIL animations (CSS is handled by the
// scoped media query below).
onMounted(() => {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const svg = document.querySelector<SVGSVGElement>('svg.viz')
    // pauseAnimations exists on SVGSVGElement at runtime
    ;(svg as unknown as { pauseAnimations?: () => void })?.pauseAnimations?.()
  }
})
</script>

<template>
  <div class="sf">
    <!-- ============ HERO ============ -->
    <section class="hero" id="top">
      <div class="wrap hero__grid">
        <div class="hero__copy">
          <span class="eyebrow"><span class="dot"></span> Model ensembles, orchestrated</span>
          <h1>Turn your models<br />into <span class="fused">monsters</span>.</h1>
          <p class="lede">
            Screaming Face fuses model ensembles that run <b>faster</b>, cost <b>less</b>, and reason
            <b>harder</b> than any single model. Bring the subscriptions you already pay for — we make
            them work together.
          </p>
          <div class="hero__cta">
            <a class="btn btn--primary" href="#launch">Open Studio →</a>
            <a class="btn btn--ghost" href="#launch">Read the launch post</a>
            <span class="ph"><span class="up">▲</span> <strong>#1</strong> on Product&nbsp;Hunt today</span>
          </div>
        </div>

        <!-- SIGNATURE: ensemble → judge → fused output -->
        <div class="hero__viz">
          <svg class="viz" viewBox="0 0 560 480" role="img" aria-label="Three models feeding a judge that fuses one output">
            <defs>
              <radialGradient id="gCyan" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#8FF3F9"/><stop offset="55%" stop-color="#38D2DC"/><stop offset="100%" stop-color="#127a83"/></radialGradient>
              <radialGradient id="gIris" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#B7ADFF"/><stop offset="55%" stop-color="#7B6CF2"/><stop offset="100%" stop-color="#3d34a0"/></radialGradient>
              <radialGradient id="gRose" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#FF9EC1"/><stop offset="55%" stop-color="#FF5C93"/><stop offset="100%" stop-color="#a52a56"/></radialGradient>
              <radialGradient id="gScream" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#FFD79B"/><stop offset="45%" stop-color="#FF9A3D"/><stop offset="80%" stop-color="#FF6A2B"/><stop offset="100%" stop-color="#a53807"/></radialGradient>
              <linearGradient id="gEdge" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#38D2DC" stop-opacity=".1"/><stop offset="100%" stop-color="#FF6A2B" stop-opacity=".55"/></linearGradient>
              <filter id="blur" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="9"/></filter>
              <filter id="soft" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.2"/></filter>
            </defs>

            <!-- ambient swirl (Scream-sky nod) -->
            <g opacity=".5">
              <ellipse class="drift" cx="330" cy="150" rx="150" ry="90" fill="#FF6A2B" opacity=".12" filter="url(#blur)"/>
              <ellipse class="drift b" cx="180" cy="330" rx="140" ry="100" fill="#7B6CF2" opacity=".12" filter="url(#blur)"/>
            </g>

            <!-- connection paths -->
            <path id="p1" d="M108,120 C200,132 220,196 288,240" fill="none" stroke="#38D2DC" stroke-opacity=".26" stroke-width="1.6"/>
            <path id="p2" d="M92,240 C170,240 220,240 288,240" fill="none" stroke="#7B6CF2" stroke-opacity=".26" stroke-width="1.6"/>
            <path id="p3" d="M108,360 C200,348 220,284 288,240" fill="none" stroke="#FF5C93" stroke-opacity=".26" stroke-width="1.6"/>
            <path id="p4" d="M320,240 C380,240 420,240 470,240" fill="none" stroke="url(#gEdge)" stroke-width="2.4" class="flowline"/>

            <!-- MODEL NODES -->
            <g class="float f1">
              <circle cx="100" cy="120" r="30" fill="#38D2DC" opacity=".35" filter="url(#blur)"/>
              <circle cx="100" cy="120" r="19" fill="url(#gCyan)"/>
              <text x="100" y="163" text-anchor="middle" font-family="'JetBrains Mono',monospace" font-size="12" fill="#8B93A9">gpt-x</text>
            </g>
            <g class="float f2">
              <circle cx="82" cy="240" r="30" fill="#7B6CF2" opacity=".35" filter="url(#blur)"/>
              <circle cx="82" cy="240" r="19" fill="url(#gIris)"/>
              <text x="82" y="283" text-anchor="middle" font-family="'JetBrains Mono',monospace" font-size="12" fill="#8B93A9">claude</text>
            </g>
            <g class="float f3">
              <circle cx="100" cy="360" r="30" fill="#FF5C93" opacity=".35" filter="url(#blur)"/>
              <circle cx="100" cy="360" r="19" fill="url(#gRose)"/>
              <text x="100" y="403" text-anchor="middle" font-family="'JetBrains Mono',monospace" font-size="12" fill="#8B93A9">gemini</text>
            </g>

            <!-- flowing particles -->
            <circle r="3.4" fill="#38D2DC" filter="url(#soft)"><animateMotion dur="2.1s" repeatCount="indefinite"><mpath href="#p1"/></animateMotion></circle>
            <circle r="3.4" fill="#38D2DC" filter="url(#soft)"><animateMotion dur="2.1s" begin="1.05s" repeatCount="indefinite"><mpath href="#p1"/></animateMotion></circle>
            <circle r="3.4" fill="#7B6CF2" filter="url(#soft)"><animateMotion dur="1.9s" repeatCount="indefinite"><mpath href="#p2"/></animateMotion></circle>
            <circle r="3.4" fill="#7B6CF2" filter="url(#soft)"><animateMotion dur="1.9s" begin=".95s" repeatCount="indefinite"><mpath href="#p2"/></animateMotion></circle>
            <circle r="3.4" fill="#FF5C93" filter="url(#soft)"><animateMotion dur="2.3s" repeatCount="indefinite"><mpath href="#p3"/></animateMotion></circle>
            <circle r="3.4" fill="#FF5C93" filter="url(#soft)"><animateMotion dur="2.3s" begin="1.15s" repeatCount="indefinite"><mpath href="#p3"/></animateMotion></circle>
            <circle r="4" fill="#FF6A2B" filter="url(#soft)"><animateMotion dur="1.5s" repeatCount="indefinite"><mpath href="#p4"/></animateMotion></circle>

            <!-- JUDGE core -->
            <g>
              <circle cx="304" cy="240" r="46" fill="#7B6CF2" opacity=".25" filter="url(#blur)"/>
              <circle class="spin" cx="304" cy="240" r="40" fill="none" stroke="#7B6CF2" stroke-opacity=".5" stroke-width="1.4" stroke-dasharray="4 8"/>
              <circle class="spin-rev" cx="304" cy="240" r="31" fill="none" stroke="#38D2DC" stroke-opacity=".55" stroke-width="1.4" stroke-dasharray="2 10"/>
              <g class="corepulse">
                <circle cx="304" cy="240" r="22" fill="#1B2333" stroke="#7B6CF2" stroke-width="1.5"/>
                <text x="304" y="236" text-anchor="middle" font-family="'JetBrains Mono',monospace" font-size="10.5" letter-spacing="1" fill="#ECEEF5">JUDGE</text>
                <text x="304" y="250" text-anchor="middle" font-family="'JetBrains Mono',monospace" font-size="8" fill="#8B93A9">scoring</text>
              </g>
            </g>

            <!-- FUSED OUTPUT (scream) -->
            <g>
              <circle class="ring" cx="486" cy="240" r="30" fill="none" stroke="#FF6A2B" stroke-width="2"/>
              <circle class="ring b" cx="486" cy="240" r="30" fill="none" stroke="#FFB63D" stroke-width="2"/>
              <circle cx="486" cy="240" r="40" fill="#FF6A2B" opacity=".35" filter="url(#blur)"/>
              <circle class="corepulse" cx="486" cy="240" r="28" fill="url(#gScream)"/>
              <text x="486" y="245" text-anchor="middle" font-size="24" aria-hidden="true">😱</text>
              <text x="486" y="300" text-anchor="middle" font-family="'JetBrains Mono',monospace" font-size="12" fill="#FFB63D">ensemble</text>
            </g>
          </svg>
        </div>
      </div>
    </section>

    <!-- ============ BENCH STRIP ============ -->
    <section class="bench" aria-label="Benchmarks">
      <div class="wrap bench__inner">
        <div class="bench__label">State of the art, out of the box</div>
        <!-- Replace placeholder figures with your verified benchmark numbers -->
        <div class="stat c1"><div class="n">2.4×</div><div class="k">faster time-to-answer</div></div>
        <div class="stat c2"><div class="n">−58%</div><div class="k">cost per task</div></div>
        <div class="stat c3"><div class="n">+11 pts</div><div class="k">on your eval suite</div></div>
        <div class="stat c4"><div class="n">1 line</div><div class="k">to reproduce it all</div></div>
      </div>
    </section>

    <!-- ============ STUDIO / STEPS ============ -->
    <section class="block" id="studio">
      <div class="wrap">
        <div class="sechead">
          <span class="tag">Screaming Face Studio</span>
          <h2>Build an ensemble in three moves.</h2>
          <p>
            Studio is where you compose, orchestrate, and ship model ensembles — no glue code, no
            re-plumbing your stack. Follow the order once and it sticks.
          </p>
        </div>
        <div class="steps">
          <article class="step s1">
            <div class="step__num">01 / connect</div>
            <h3>Connect what you already pay for</h3>
            <p>Plug in your existing model subscriptions. No new bills, no vendor lock-in — Studio talks to the accounts you have.</p>
          </article>
          <article class="step s2">
            <div class="step__num">02 / judge</div>
            <h3>Appoint the judges</h3>
            <p>Pick which models score, critique, and pick the winning answer. Debate, vote, or cascade — the orchestration is yours to shape.</p>
          </article>
          <article class="step s3">
            <div class="step__num">03 / ship</div>
            <h3>Ship a one-liner</h3>
            <p>Every ensemble compiles to one reproducible line. Copy it, version it, hand it to a teammate — same result, every time.</p>
          </article>
        </div>
      </div>
    </section>

    <!-- ============ ONE-LINER ============ -->
    <section class="block" id="oneliner" style="padding-top: 0">
      <div class="wrap">
        <div class="sechead">
          <span class="tag">Reproducible by design</span>
          <h2>The whole ensemble, in one line.</h2>
          <p>What the research team builds out-of-band, Studio captures verbatim — so the workflow that hit the benchmark is the workflow you run.</p>
        </div>
        <div class="oneliner">
          <div class="oneliner__bar"><i class="r"></i><i class="y"></i><i class="g"></i><span>ensemble.sh</span></div>
<pre><span class="cmd">screamingface</span> run <span class="flag">--models</span> <span class="val">"gpt-x, claude, gemini"</span> \
  <span class="flag">--judge</span> <span class="val">claude</span> <span class="flag">--strategy</span> <span class="val">debate</span> \
  <span class="flag">--budget</span> <span class="val">low</span> <span class="cm"># faster + cheaper, same answer</span></pre>
        </div>
      </div>
    </section>

    <!-- ============ LAUNCH CTA ============ -->
    <section class="block" id="launch" style="padding-top: 0">
      <div class="wrap">
        <div class="launch">
          <h2>We're live. Come make a monster.</h2>
          <p>Screaming Face — the project some of us still call Fusion Monsters — is out in the open. Read how the benchmarks were won, then build your own ensemble in Studio.</p>
          <div class="launch__cta">
            <a class="btn btn--primary" href="#top">Open Studio →</a>
            <a class="btn btn--ghost" href="#top">▲ Back us on Product Hunt</a>
            <a class="btn btn--ghost" href="#top">Read the blog</a>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ FOOTER ============ -->
    <footer>
      <div class="wrap foot">
        <span class="brand"><span class="face" aria-hidden="true">😱</span> Screaming Face</span>
        <span>Model ensembles, orchestrated. · aka Fusion Monsters</span>
        <span><a href="#studio">Studio</a> &nbsp;·&nbsp; <a href="#oneliner">Docs</a> &nbsp;·&nbsp; <a href="#launch">Launch</a></span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/* Brand accents (fixed identity); surfaces map to the app theme tokens so the
   landing follows light/dark. */
.sf {
  --cyan: #38d2dc;
  --iris: #7b6cf2;
  --rose: #ff5c93;
  --scream: #ff6a2b;
  --amber: #ffb63d;
  --maxw: 1180px;
  --display: 'Bricolage Grotesque', system-ui, sans-serif;
  --body: 'Hanken Grotesk', system-ui, sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, monospace;

  /* Surfaces from the app theme */
  --ink: var(--foreground);
  --mute: var(--muted-foreground);
  --line: var(--border);
  --panel: var(--card);
  --panel-2: var(--muted);

  font-family: var(--body);
  font-size: 17px;
  line-height: 1.55;
  color: var(--ink);
}
.sf * {
  font-family: inherit;
}

.sf .wrap {
  max-width: var(--maxw);
  margin: 0 auto;
  padding: 0 28px;
}
.sf a {
  color: inherit;
  text-decoration: none;
}

.sf .btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: var(--body);
  font-weight: 600;
  font-size: 15px;
  padding: 11px 20px;
  border-radius: 999px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: transform 0.18s, box-shadow 0.18s, background 0.18s;
}
.sf .btn--primary {
  background: linear-gradient(120deg, var(--scream), var(--amber));
  color: #160a02;
  box-shadow: 0 6px 22px -6px rgba(255, 106, 43, 0.6);
}
.sf .btn--primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 30px -6px rgba(255, 106, 43, 0.75);
}
.sf .btn--ghost {
  border-color: var(--line);
  color: var(--ink);
  background: color-mix(in oklab, var(--ink) 3%, transparent);
}
.sf .btn--ghost:hover {
  border-color: color-mix(in oklab, var(--ink) 28%, transparent);
  transform: translateY(-2px);
}

/* ---------- HERO ---------- */
.sf .hero {
  position: relative;
  padding: 72px 0 40px;
}
.sf .hero__grid {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 36px;
  align-items: center;
}
.sf .eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-family: var(--mono);
  font-size: 12.5px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--cyan);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 7px 15px;
  margin-bottom: 26px;
}
.sf .eyebrow .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cyan);
  box-shadow: 0 0 10px var(--cyan);
}
.sf h1 {
  font-family: var(--display);
  font-weight: 800;
  font-size: clamp(2.7rem, 6vw, 4.6rem);
  line-height: 0.98;
  letter-spacing: -0.03em;
  margin: 0 0 22px;
}
.sf h1 .fused {
  background: linear-gradient(115deg, var(--cyan), var(--iris) 42%, var(--rose) 68%, var(--scream));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.sf .lede {
  font-size: clamp(1.05rem, 1.6vw, 1.22rem);
  color: var(--mute);
  max-width: 33ch;
  margin: 0 0 32px;
}
.sf .lede b {
  color: var(--ink);
  font-weight: 600;
}
.sf .hero__cta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
}
.sf .ph {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-size: 13px;
  color: var(--mute);
  font-family: var(--mono);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 9px 13px;
}
.sf .ph strong {
  color: var(--ink);
  font-weight: 600;
}
.sf .ph .up {
  color: var(--scream);
}

/* ---------- HERO VIZ ---------- */
.sf .viz {
  width: 100%;
  height: auto;
  display: block;
  overflow: visible;
}
.sf .float {
  transform-box: fill-box;
  transform-origin: center;
}
.sf .f1 {
  animation: sf-floaty 6s ease-in-out infinite;
}
.sf .f2 {
  animation: sf-floaty 7.5s ease-in-out infinite 0.8s;
}
.sf .f3 {
  animation: sf-floaty 6.8s ease-in-out infinite 1.6s;
}
@keyframes sf-floaty {
  0%, 100% { transform: translateY(-6px); }
  50% { transform: translateY(6px); }
}
.sf .spin {
  transform-box: fill-box;
  transform-origin: center;
  animation: sf-spin 14s linear infinite;
}
@keyframes sf-spin {
  to { transform: rotate(360deg); }
}
.sf .spin-rev {
  transform-box: fill-box;
  transform-origin: center;
  animation: sf-spin 22s linear infinite reverse;
}
.sf .corepulse {
  transform-box: fill-box;
  transform-origin: center;
  animation: sf-corepulse 3.4s ease-in-out infinite;
}
@keyframes sf-corepulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.06); opacity: 0.86; }
}
.sf .ring {
  animation: sf-ring 3s ease-out infinite;
  transform-box: fill-box;
  transform-origin: center;
}
.sf .ring.b {
  animation-delay: 1.5s;
}
@keyframes sf-ring {
  0% { transform: scale(0.5); opacity: 0.7; }
  100% { transform: scale(1.9); opacity: 0; }
}
.sf .drift {
  transform-box: view-box;
  animation: sf-drift 30s ease-in-out infinite alternate;
}
.sf .drift.b {
  animation-duration: 38s;
  animation-direction: alternate-reverse;
}
@keyframes sf-drift {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(30px, -20px) scale(1.12); }
}
.sf .flowline {
  stroke-dasharray: 5 9;
  animation: sf-flow 1.4s linear infinite;
}
@keyframes sf-flow {
  to { stroke-dashoffset: -14; }
}

/* ---------- BENCH STRIP ---------- */
.sf .bench {
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  background: color-mix(in oklab, var(--ink) 1.5%, transparent);
}
.sf .bench__inner {
  display: grid;
  grid-template-columns: auto repeat(4, 1fr);
  gap: 0;
  align-items: stretch;
}
.sf .bench__label {
  display: flex;
  align-items: center;
  padding: 26px 28px 26px 0;
  font-family: var(--mono);
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--mute);
  max-width: 150px;
}
.sf .stat {
  padding: 26px 22px;
  border-left: 1px solid var(--line);
}
.sf .stat .n {
  font-family: var(--display);
  font-weight: 800;
  font-size: clamp(1.7rem, 3vw, 2.4rem);
  line-height: 1;
  letter-spacing: -0.02em;
}
.sf .stat.c1 .n { color: var(--cyan); }
.sf .stat.c2 .n { color: var(--rose); }
.sf .stat.c3 .n { color: var(--amber); }
.sf .stat.c4 .n { color: var(--scream); }
.sf .stat .k {
  font-size: 13.5px;
  color: var(--mute);
  margin-top: 8px;
}

/* ---------- STUDIO / STEPS ---------- */
.sf section.block {
  padding: 96px 0;
}
.sf .sechead {
  max-width: 620px;
  margin-bottom: 52px;
}
.sf .sechead .tag {
  font-family: var(--mono);
  font-size: 12.5px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--iris);
}
.sf .sechead h2 {
  font-family: var(--display);
  font-weight: 800;
  font-size: clamp(2rem, 4vw, 3rem);
  letter-spacing: -0.025em;
  line-height: 1.02;
  margin: 16px 0 14px;
}
.sf .sechead p {
  color: var(--mute);
  font-size: 1.08rem;
  margin: 0;
}
.sf .steps {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.sf .step {
  position: relative;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 30px 26px 32px;
  overflow: hidden;
  transition: transform 0.2s, border-color 0.2s;
}
.sf .step:hover {
  transform: translateY(-4px);
  border-color: color-mix(in oklab, var(--ink) 20%, transparent);
}
.sf .step::before {
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  opacity: 0.9;
}
.sf .step.s1::before { background: var(--cyan); }
.sf .step.s2::before { background: var(--iris); }
.sf .step.s3::before { background: var(--scream); }
.sf .step__num {
  font-family: var(--mono);
  font-size: 13px;
  color: var(--mute);
}
.sf .step h3 {
  font-family: var(--display);
  font-weight: 600;
  font-size: 1.35rem;
  letter-spacing: -0.01em;
  margin: 16px 0 10px;
}
.sf .step p {
  color: var(--mute);
  font-size: 0.98rem;
  margin: 0;
}

/* ---------- ONE-LINER ---------- */
.sf .oneliner {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 12px;
  overflow: hidden;
}
.sf .oneliner__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
}
.sf .oneliner__bar i {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  display: inline-block;
}
.sf .oneliner__bar .r { background: #ff5f56; }
.sf .oneliner__bar .y { background: #ffbd2e; }
.sf .oneliner__bar .g { background: #27c93f; }
.sf .oneliner__bar span {
  margin-left: 8px;
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--mute);
}
.sf .oneliner pre {
  margin: 0;
  padding: 22px 22px 26px;
  font-family: var(--mono);
  font-size: clamp(0.82rem, 1.35vw, 1rem);
  line-height: 1.85;
  overflow-x: auto;
  color: var(--ink);
}
.sf .oneliner pre .cmd { color: var(--amber); }
.sf .oneliner pre .flag { color: var(--cyan); }
.sf .oneliner pre .val { color: var(--rose); }
.sf .oneliner pre .cm { color: var(--mute); }

/* ---------- LAUNCH CTA ---------- */
.sf .launch {
  position: relative;
  text-align: center;
  border: 1px solid var(--line);
  border-radius: 26px;
  padding: 72px 32px;
  overflow: hidden;
  background: linear-gradient(160deg, var(--panel-2), var(--panel));
}
.sf .launch::after {
  content: '';
  position: absolute;
  width: 520px;
  height: 520px;
  left: 50%;
  top: -60%;
  transform: translateX(-50%);
  background: radial-gradient(circle, rgba(255, 106, 43, 0.22), transparent 62%);
  pointer-events: none;
}
.sf .launch h2 {
  position: relative;
  font-family: var(--display);
  font-weight: 800;
  font-size: clamp(2rem, 4.5vw, 3.2rem);
  letter-spacing: -0.03em;
  margin: 0 0 16px;
}
.sf .launch p {
  position: relative;
  color: var(--mute);
  max-width: 46ch;
  margin: 0 auto 32px;
  font-size: 1.08rem;
}
.sf .launch__cta {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  justify-content: center;
}

/* ---------- FOOTER ---------- */
.sf footer {
  border-top: 1px solid var(--line);
  padding: 40px 0;
  margin-top: 20px;
}
.sf .foot {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  color: var(--mute);
  font-size: 14px;
}
.sf .brand {
  display: flex;
  align-items: center;
  gap: 11px;
  font-family: var(--display);
  font-weight: 800;
  font-size: 16px;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.sf .brand .face {
  font-size: 20px;
  line-height: 1;
  filter: drop-shadow(0 0 12px rgba(56, 210, 220, 0.5));
}
.sf .foot a { color: var(--mute); }
.sf .foot a:hover { color: var(--ink); }

/* ---------- RESPONSIVE ---------- */
@media (max-width: 900px) {
  .sf .hero__grid {
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .sf .hero__viz {
    order: -1;
    max-width: 460px;
    margin: 0 auto;
  }
  .sf .lede { max-width: none; }
  .sf .steps { grid-template-columns: 1fr; }
  .sf .bench__inner { grid-template-columns: 1fr 1fr; }
  .sf .bench__label {
    grid-column: 1 / -1;
    max-width: none;
    padding: 22px 0 16px;
    border-bottom: 1px solid var(--line);
  }
  .sf .stat:nth-child(2), .sf .stat:nth-child(4) { border-left: 0; }
  .sf section.block { padding: 70px 0; }
}
@media (max-width: 440px) {
  .sf .bench__inner { grid-template-columns: 1fr; }
  .sf .stat {
    border-left: 0;
    border-top: 1px solid var(--line);
  }
}
@media (prefers-reduced-motion: reduce) {
  .sf * {
    animation: none !important;
    transition: none !important;
  }
}
</style>
