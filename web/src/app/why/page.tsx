import EmailCapture from "@/components/EmailCapture";
import CollaboratorsGrid from "@/components/CollaboratorsGrid";
import { ChevronRight } from "lucide-react";

// All sections use max-w-4xl as the outer container for consistent left-edge alignment.
// Body text is constrained to max-w-2xl mx-auto within the outer max-w-4xl container.
// The hero uses the full 4xl width for its two-column layout.

export default function WhyPage() {
  return (
    <div className="min-h-screen flex flex-col">

      {/* Nav */}
      <header className="border-b border-border px-6 py-4 flex items-center justify-between">
        <a
          href="/"
          className="text-lg font-medium tracking-tight hover:opacity-80 transition-opacity"
          style={{ fontFamily: "var(--font-rubik)" }}
        >
          😱 screamingface
        </a>
        <nav className="flex items-center gap-6 text-sm text-muted-foreground">
          <a href="#argument" className="hover:text-foreground transition-colors">The argument</a>
          <a href="#get-involved" className="hover:text-foreground transition-colors">Get involved</a>
          <a href="/" className="hover:text-foreground transition-colors">The tool →</a>
        </nav>
      </header>

      <main className="flex-1">

        {/* ── Hero ─────────────────────────────────────────────────────────── */}
        <section id="argument" className="px-6 pt-24 pb-20">
          <div className="max-w-4xl mx-auto">

            {/* Kicker */}
            <p
              className="text-xs text-muted-foreground uppercase tracking-widest mb-8 border-l-2 border-primary pl-3"
              style={{ fontFamily: "var(--font-sometype-mono)" }}
            >
              The window is open
            </p>

            {/* Headline */}
            <h1
              className="text-4xl md:text-5xl font-semibold tracking-tight leading-[1.1] mb-12 max-w-3xl"
              style={{ fontFamily: "var(--font-rubik)" }}
            >
              The best AI is{" "}
              <span className="text-gradient-gold">already working together.</span>
            </h1>

            {/* Two-column body: narrative left, stat callout right */}
            <div className="grid grid-cols-1 md:grid-cols-[1fr_200px] gap-10 items-start">
              <div className="space-y-5 text-muted-foreground leading-relaxed">
                <p className="text-foreground/80">
                  The opportunity is here. Open ensembles (systems that combine the outputs of many AI models) consistently outperform any single model on every benchmark we&apos;ve tested. This is a structural advantage, and it belongs to no one company. The time to establish open AI infrastructure is now, and the people and tools to build it already exist.
                </p>
              </div>

              {/* Stat callout */}
              <div className="md:border-l md:border-border md:pl-8 pt-1 flex flex-col gap-3">
                <div
                  className="text-3xl font-semibold leading-none text-gradient-gold"
                  style={{ fontFamily: "var(--font-rubik)" }}
                >
                  It&apos;s time
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  The chance to build open AI infrastructure exists now, before the commercial response closes it.
                </p>
              </div>
            </div>

          </div>
        </section>

        {/* ── Common Ground ────────────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                Open and accountable are not opposites
              </h2>
              <p>
                The AI world has been stuck on a question: do you centralize for safety, or distribute for transparency? Both concerns are legitimate. Governments everywhere are trying to balance them. The EU AI Act, GDPR, and US executive orders all reflect the same tension.
              </p>
              <p>
                But new research in attribution-based control and ensemble architectures suggests the question itself is outdated. You can have open, distributed AI <em>and</em> maintain accountability. The choice between openness and safety was a limitation of single-model systems. It doesn&apos;t have to apply anymore.
              </p>
            </div>
          </div>
        </section>

        {/* ── The Problem ──────────────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                The ensemble gets both
              </h2>
              <p>
                We&apos;ve been here before. When governments began digitizing public records, libraries, and civic data in the 1990s and 2000s, the organizations that acted early built lasting infrastructure. The ones that waited bought vendor lock-in. The same pattern is unfolding now with AI. Hospitals, research labs, agricultural cooperatives, cultural archives. Every discipline is generating data that could power better AI. The question is whether that data builds infrastructure everyone benefits from, or becomes assets controlled by&nbsp;a&nbsp;few.
              </p>
              <p>
                The ensemble changes the equation. When open and proprietary models work together through an attribution layer that tracks every contribution, you get the performance benefits of the best commercial systems <em>and</em> the transparency that open systems provide. What remains is a chance to build shared infrastructure while the window is&nbsp;open.
              </p>
            </div>
          </div>
        </section>

        {/* ── What's at stake ─────────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto mb-10">
              <h2
                className="text-2xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                What centralized AI puts at risk
              </h2>
              <p className="text-muted-foreground">
                Centralized AI creates specific, solvable problems. Open, federated systems address each of them. But only if we build the infrastructure while the window is open.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-y-8 max-w-2xl mx-auto">

              {/* Privacy */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Privacy &amp; Data Sovereignty
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    When every query flows through a single provider, that provider builds a complete picture of your work, your thinking, and your organization&apos;s priorities. Distributing queries across multiple models and providers is structural privacy. Not a setting you toggle, but an architectural property of the system. Institutions and communities can contribute data to AI training while retaining full control over what is shared, with whom, and under what terms. And when models are codeveloped using community resources, the question of who owns the result needs an answer built into the infrastructure.
                  </p>
                </div>
              </div>

              {/* Safety */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Safety &amp; Control
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    No single entity should be the sole gatekeeper of the most powerful AI systems. When inference is concentrated in one provider, a single point of failure (technical, ethical, or commercial) affects everyone. An open ensemble distributes that risk. Multiple models with independent training, independent safety evaluations, and independent governance create resilience that no single provider can match.
                  </p>
                </div>
              </div>

              {/* Copyright */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Copyright &amp; Attribution
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Courts around the world are actively litigating how copyright applies to AI-generated content and model training data. An ensemble that tracks which model produced which output, and maintains a chain of attribution, provides exactly the kind of provenance record that legal and ethical frameworks are calling for. Creator attribution rights can survive model training, but only if the infrastructure is designed to preserve them.
                  </p>
                </div>
              </div>

              {/* Hallucination */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Hallucination &amp; Traceability
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    When a model fabricates a source, cites a nonexistent paper, or generates a confident falsehood, the damage compounds if there&apos;s no way to trace the claim back to its origin. An ensemble with attribution makes predictions traceable. You can identify which model generated which claim, evaluate its reliability, and hold the right system accountable.
                  </p>
                </div>
              </div>

              {/* Bias */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Bias &amp; Representation
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Every model carries the biases of its training data and the priorities of its creators. A single-provider system embeds one company&apos;s choices about what to include, what to weight, and what to filter. An ensemble draws from models built by different teams, trained on different data, with different design philosophies. Communities can govern their own contributions to the system, preserving human agency over how their knowledge is used.
                  </p>
                </div>
              </div>

              {/* Democracy */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Democratic Governance
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    AI infrastructure is becoming as foundational as electricity grids and public roads. When that infrastructure is controlled by a handful of private entities, public oversight becomes structurally difficult, and civic institutions lose the ability to serve their communities independently. Open, federated AI systems, built as public goods, governed collectively, and auditable by the institutions that depend on them, are the democratic alternative. The question is whether we build them while the window is open.
                  </p>
                </div>
              </div>

            </div>
            <p className="text-xs text-muted-foreground mt-10 max-w-2xl mx-auto">
              For a deeper treatment of these consequences, see{" "}
              <a
                href="https://attribution-based-control.ai/#societal-consequences"
                className="underline underline-offset-2 hover:text-foreground transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                attribution-based-control.ai
              </a>.
            </p>
          </div>
        </section>

        {/* ── How the ensemble works ───────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                Why many models beat one
              </h2>
              <p>
                Different AI models make different kinds of mistakes. Claude might excel at complex reasoning but stumble on a math problem that Gemini handles easily. GPT might nail a coding task that trips up both of them. These errors are <em>anti-correlated</em>. When one model is wrong, another is often right. An ensemble that combines their outputs catches mistakes that any individual model would miss.
              </p>
              <p>
                Ensemble methods have outperformed single models in machine learning for decades. Random forests, boosting, mixture-of-experts. What&apos;s new is applying the principle to frontier AI models at inference time, routing each prompt to the model most likely to get it right, or combining multiple answers into one that&apos;s better than any single response.
              </p>
              <p>
                Intelligent routing picks the lightest model for simple tasks and the strongest for hard ones. And because the system works with the models you already have access to, it doesn&apos;t require a new subscription. It makes your existing tools work better together.
              </p>
            </div>
          </div>
        </section>

        {/* ── Attribution-Based Control ────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                Every AI output should be traceable
              </h2>
              <p>
                screamingface is a tool you can use today. But it&apos;s built on top of something larger. An open protocol called{" "}
                <a
                  href="https://url4.ai"
                  className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  url4
                </a>{" "}
                that encodes AI task chains as human-readable URLs. Every step in a computation becomes transparent and auditable. The protocol is designed to support <em>attribution-based control</em>, the idea that when AI systems produce outputs, the contributions of every data source, model, and human decision should be traceable.
              </p>
              <p>
                The implications go beyond debugging. Tracing which model produced which output means copyright becomes enforceable. Tracing which data trained which model means creators can be compensated. Tracing routing decisions means auditing for bias and accountability becomes possible. Attribution is the foundation for fair, governable AI.
              </p>
              <p>
                Credit sharing is an early example. When someone in your network has unused tokens on a provider you need, screamingface can route through their allocation. The attribution layer tracks exactly who contributed what. Resource-sharing with accountability built in.
              </p>
            </div>

            {/* ABC callout */}
            <div className="max-w-2xl mx-auto mt-8 border border-primary/30 rounded-lg p-6 bg-primary/[0.04]">
              <h3
                className="text-sm font-medium text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                The full case
              </h3>
              <p className="text-sm text-muted-foreground leading-relaxed mb-3">
                Andrew Trask&apos;s thesis lays out the full case for attribution-based control, including how it addresses copyright, privacy, bias, and democratic governance. It&apos;s the intellectual foundation this project is built on.
              </p>
              <a
                href="https://attribution-based-control.ai"
                className="inline-flex items-center gap-1.5 text-sm text-primary hover:opacity-80 transition-opacity"
                target="_blank"
                rel="noopener noreferrer"
              >
                Read the Attribution-Based Control thesis
                <ChevronRight className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </section>

        {/* ── Built by OpenMined ──────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                Built by OpenMined
              </h2>
              <p>
                <a
                  href="https://openmined.org"
                  className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  OpenMined
                </a>{" "}
                is a nonprofit building open-source tools for privacy-preserving AI. Founded in 2017, the organization built PySyft (a framework for secure, privacy-preserving machine learning) and assembled one of the largest open-source AI communities in the world. screamingface is the next step. Proving that open, distributed AI infrastructure can outperform the proprietary alternative, and building the attribution layer that makes it governable.
              </p>
            </div>
          </div>
        </section>

        {/* ── Collaborators ───────────────────────────────────────────────── */}
        <CollaboratorsGrid />

        {/* ── Get involved (wraps EmailCapture) ─────────────────────────── */}
        <div id="get-involved">
          <EmailCapture>
            <div className="text-4xl mb-4 select-none">😱</div>
            <h2
              className="text-2xl font-semibold mb-3"
              style={{ fontFamily: "var(--font-rubik)" }}
            >
              Get involved
            </h2>
            <p className="text-muted-foreground text-sm mb-8 leading-relaxed">
              We&apos;re building a coalition around open, federated AI infrastructure. If you want to help make the case while the window is open, here&apos;s how.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-left mb-10">
              <div className="border border-border rounded-lg p-4">
                <h3
                  className="text-sm font-medium text-foreground mb-1"
                  style={{ fontFamily: "var(--font-rubik)" }}
                >
                  Co-author
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Write with us. Policy briefs, research papers, public statements. We&apos;re building a body of work that makes the case for open AI as public infrastructure. Co-author opportunities are open.
                </p>
              </div>
              <div className="border border-border rounded-lg p-4">
                <h3
                  className="text-sm font-medium text-foreground mb-1"
                  style={{ fontFamily: "var(--font-rubik)" }}
                >
                  Share expertise
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Privacy law, AI safety, copyright, democratic governance. If you work in these areas, join a roundtable, speak at a convening, or advise on a workshop. Your perspective shapes what we build.
                </p>
              </div>
              <div className="border border-border rounded-lg p-4">
                <h3
                  className="text-sm font-medium text-foreground mb-1"
                  style={{ fontFamily: "var(--font-rubik)" }}
                >
                  Lend your name
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Institutional affiliations and organizational endorsements signal to policymakers that this work has broad support. Add your voice.
                </p>
              </div>
              <div className="border border-border rounded-lg p-4">
                <h3
                  className="text-sm font-medium text-foreground mb-1"
                  style={{ fontFamily: "var(--font-rubik)" }}
                >
                  Cover the story
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  If you&apos;re a journalist or researcher, we&apos;ll share data, methodology, and access. The benchmarks are open and reproducible.
                </p>
              </div>
            </div>
          </EmailCapture>
        </div>

      </main>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
        <span>
          😱 screamingface, built by{" "}
          <a
            href="https://openmined.org"
            className="hover:text-foreground transition-colors underline underline-offset-2"
            target="_blank"
            rel="noopener noreferrer"
          >
            OpenMined
          </a>
        </span>
        <nav className="flex items-center gap-5">
          <a href="/" className="hover:text-foreground transition-colors">The tool</a>
          <a
            href="https://github.com/OpenMined/screamingface"
            className="hover:text-foreground transition-colors"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          <a
            href="https://attribution-based-control.ai"
            className="hover:text-foreground transition-colors"
            target="_blank"
            rel="noopener noreferrer"
          >
            attribution-based-control.ai
          </a>
        </nav>
      </footer>
    </div>
  );
}
