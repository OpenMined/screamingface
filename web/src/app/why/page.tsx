export default function WhyPage() {
  return (
    <>
      {/* Header */}
      <header style={{ borderBottom: "1px solid #ccc", paddingBottom: 8, marginBottom: 16, paddingTop: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
          <div>
            <a href="/" style={{ textDecoration: "none", color: "inherit" }}>
              <span style={{ fontSize: 22 }}>😱</span>{" "}
              <strong style={{ fontSize: 16 }}>screamingface</strong>
            </a>{" "}
            <span style={{ color: "#666", fontSize: 12 }}>/ why this matters</span>
          </div>
          <nav style={{ fontSize: 12, display: "flex", gap: 16 }}>
            <a href="/">cost dashboard</a>
            <a href="#window">the window</a>
            <a href="#involved">get involved</a>
            <a href="https://github.com/OpenMined/screamingface">github</a>
          </nav>
        </div>
      </header>

      {/* Lede */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 20, borderBottom: "none", marginBottom: 8 }}>
          Who controls the price of intelligence?
        </h1>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          Right now, 3–4 companies set the price of AI and nobody is watching.
          There is no public index. No ticker. No transparency.
          Benchmarks measure accuracy in isolation. Pricing pages show cost per token in isolation.
          The number that actually matters — <strong>what does it cost to get a correct answer?</strong> — isn&apos;t tracked by anyone.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7 }}>
          <a href="/">We started tracking it.</a> And the data tells a story that should concern anyone thinking about the future of AI.
        </p>
      </div>

      <hr />

      {/* The concentration problem */}
      <section style={{ marginBottom: 24 }}>
        <h2>The concentration problem</h2>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          Look at the <a href="/">cost dashboard</a>. Every category shows the same pattern: a handful of companies control the frontier models, and they set prices with no public accountability. When Anthropic raises prices on coding tasks, or OpenAI adjusts their reasoning model rates, the cost of intelligence moves — and nobody tracks it.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          This is not a normal market. When fuel prices spike, there are indices, regulators, and public debate. When the cost of AI intelligence moves, there&apos;s a blog post from a company and a thread on Twitter.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7 }}>
          The cost dashboard is a small step toward fixing that. But the deeper problem requires a different kind of solution.
        </p>
      </section>

      <hr />

      {/* The 2-year window */}
      <section id="window" style={{ marginBottom: 24 }}>
        <h2>The 2-year window</h2>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          Right now, open ensemble systems like screamingface can route around any single company&apos;s model. If Claude is too expensive for a task, route to Gemini. If Gemini is weak at coding, route to Claude. Competition works because the models are accessible via APIs.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          That access window is closing. Within roughly two years, large AI companies will respond — by restricting API access, by bundling models into walled ecosystems, or by competing directly in ways that make ensemble routing impractical.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          Before that window closes, the public sector needs to begin funding federated, decentralized AI infrastructure. This is not speculation. It&apos;s the same pattern as the previous wave of government digitization — the conversion of public records, libraries, health data, and civic systems into digital form. The organizations that moved early built lasting infrastructure. The ones that waited bought vendor lock-in.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7 }}>
          The same pattern is unfolding now with AI. Hospitals, research labs, agricultural cooperatives, cultural archives. The window to build open infrastructure is now.
        </p>
      </section>

      <hr />

      {/* What open infrastructure looks like */}
      <section style={{ marginBottom: 24 }}>
        <h2>What open infrastructure looks like</h2>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          <strong>Transparent pricing.</strong> The cost of intelligence should be tracked publicly, like commodity prices. That&apos;s what the <a href="/">dashboard</a> does.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          <strong>Ensemble routing.</strong> No single model should be a dependency. screamingface routes your queries to whichever model is cheapest for the task at hand. The tool is <a href="https://github.com/OpenMined/screamingface">open source</a>.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          <strong>Attribution and traceability.</strong> When AI uses your data, you should know. When AI gives you an answer, you should be able to trace where it came from. Andrew Trask&apos;s work on <a href="https://attribution-based-control.ai">Attribution-Based Control</a> lays the technical foundation for this — source-specific parameters that never merge, predictions you can audit, contributions you can withdraw.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7 }}>
          <strong>Shared resources.</strong> Credit-sharing across teams and institutions, so the cost of intelligence is distributed, not concentrated. Public infrastructure, not private tollbooths.
        </p>
      </section>

      <hr />

      {/* Who we are */}
      <section style={{ marginBottom: 24 }}>
        <h2>Who we are</h2>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 12 }}>
          <a href="https://openmined.org">OpenMined</a> is a nonprofit focused on privacy-preserving AI, founded in 2017. We built <a href="https://github.com/OpenMined/PySyft">PySyft</a> (a framework for secure, privacy-preserving machine learning) and assembled one of the largest open-source AI communities in the world.
        </p>
        <p style={{ maxWidth: 640, lineHeight: 1.7 }}>
          screamingface is the next step: making AI cost-efficient, transparent, and open. The cost dashboard is phase one. The ensemble tool is phase two. The long-term vision is AI infrastructure that works like public utilities — open, accountable, and governed collectively.
        </p>
      </section>

      <hr />

      {/* Get involved */}
      <section id="involved" style={{ marginBottom: 24 }}>
        <h2>Get involved</h2>
        <p style={{ maxWidth: 640, lineHeight: 1.7, marginBottom: 16 }}>
          We&apos;re building a coalition around open, transparent AI infrastructure. Here&apos;s how to help:
        </p>

        <dl style={{ fontSize: 12, lineHeight: 1.7, maxWidth: 640 }}>
          <dt><strong>Co-author</strong></dt>
          <dd style={{ marginLeft: 16, marginBottom: 12 }}>
            Write with us. Policy briefs, research papers, public statements. We&apos;re building a body of work that makes the case for open AI as public infrastructure.
          </dd>

          <dt><strong>Share expertise</strong></dt>
          <dd style={{ marginLeft: 16, marginBottom: 12 }}>
            Privacy law, AI safety, copyright, democratic governance. Join a roundtable, speak at a convening, or advise on a workshop.
          </dd>

          <dt><strong>Contribute data</strong></dt>
          <dd style={{ marginLeft: 16, marginBottom: 12 }}>
            Run our <a href="/#contribute">open-source script</a> to anonymously contribute your real-world AI costs. The more data, the more useful the dashboard.
          </dd>

          <dt><strong>Lend your name</strong></dt>
          <dd style={{ marginLeft: 16, marginBottom: 12 }}>
            Institutional affiliations and organizational endorsements signal to policymakers that this work has broad support.
          </dd>

          <dt><strong>Cover the story</strong></dt>
          <dd style={{ marginLeft: 16, marginBottom: 12 }}>
            If you&apos;re a journalist or researcher, we&apos;ll share data, methodology, and access. Everything is open and reproducible.
          </dd>
        </dl>

        <p style={{ fontSize: 12, lineHeight: 1.7, maxWidth: 640, marginTop: 8 }}>
          Reach us: <a href="https://github.com/OpenMined/screamingface">GitHub</a> · <a href="https://openmined.org">openmined.org</a>
        </p>
      </section>

      <hr />

      {/* Further reading */}
      <section style={{ marginBottom: 24 }}>
        <h2>Further reading</h2>
        <ul style={{ fontSize: 12, lineHeight: 1.8, paddingLeft: 20 }}>
          <li><a href="https://attribution-based-control.ai">Attribution-Based Control</a> — Andrew Trask&apos;s thesis on traceable, trust-based AI. The technical and societal case in full.</li>
          <li><a href="https://attribution-based-control.ai/#societal-consequences">Societal Consequences of AI</a> — Chapter on why this matters beyond the technical.</li>
          <li><a href="/">The Cost Dashboard</a> — Live cost-per-accuracy data across AI models and tasks.</li>
          <li><a href="https://github.com/OpenMined/screamingface">screamingface on GitHub</a> — All code, methodology, and data. Open source.</li>
        </ul>
      </section>

      <hr />

      {/* Footer */}
      <footer style={{ fontSize: 11, color: "#666", paddingBottom: 24, lineHeight: 1.8 }}>
        <p>
          😱 <strong>screamingface</strong> — the real cost of intelligence.
          Built by <a href="https://openmined.org">OpenMined</a> (nonprofit, est. 2017).
        </p>
        <p>
          <a href="/">cost dashboard</a> ·{" "}
          <a href="https://github.com/OpenMined/screamingface">github</a> ·{" "}
          <a href="https://attribution-based-control.ai">attribution-based-control.ai</a>
        </p>
      </footer>
    </>
  );
}
