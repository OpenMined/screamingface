import EmailCapture from "@/components/EmailCapture";
import CollaboratorsGrid from "@/components/CollaboratorsGrid";
import { ChevronRight } from "lucide-react";

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
              An open protocol
            </p>

            {/* Headline */}
            <h1
              className="text-4xl md:text-5xl font-semibold tracking-tight leading-[1.1] mb-12 max-w-3xl"
              style={{ fontFamily: "var(--font-rubik)" }}
            >
              Many models are{" "}
              <span className="text-gradient-gold">better than one.</span>
            </h1>

            {/* Body */}
            <div className="max-w-2xl space-y-5 text-muted-foreground leading-relaxed">
              <p className="text-foreground/80">
                screamingface combines multiple AI models into an ensemble that consistently outperforms any single model on published benchmarks. The results are open source and reproducible. Different models make different mistakes, and when their errors don&apos;t overlap, the combination is structurally stronger than any individual&nbsp;model.
              </p>
            </div>

          </div>
        </section>

        {/* ── Why this matters ────────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                The ensemble advantage
              </h2>
              <p>
                An ensemble draws from models built by different labs, trained on different data, with different approaches to cleaning, tuning, and architecture. Because each lab builds differently, their models tend to make different kinds of mistakes, and the ensemble catches what any single model misses. Instead of betting on one provider, it routes each prompt to the model most likely to get it&nbsp;right.
              </p>
              <p>
                This also means no single entity controls the system. If one provider changes terms, raises prices, or restricts access, the ensemble routes around it. You keep working. Right now, while multiple competitive AI models exist and their APIs remain open, there is a window to build open infrastructure on top of&nbsp;them.
              </p>
              <p>
                The EU AI Act, GDPR, US executive orders on AI, and frameworks from dozens of other governments all reflect a shared set of concerns about AI: transparency, accountability, and who controls the infrastructure. Open ensembles are a practical step toward addressing these concerns. They make AI usage auditable, distributed, and independent of any single&nbsp;vendor.
              </p>
            </div>
          </div>
        </section>

        {/* ── The protocol ────────────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                url4: the protocol behind screamingface
              </h2>
              <p>
                screamingface runs on{" "}
                <a
                  href="https://url4.ai"
                  className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  url4
                </a>
                , an open protocol that encodes AI task chains as human-readable URLs. Every computation step is transparent and auditable. url4 is what makes the ensemble work, and it&apos;s designed to be the foundation for open, federated&nbsp;AI.
              </p>
              <p>
                The protocol is bigger than screamingface. Any application can build on url4. As the protocol matures, it will support new capabilities, from traceable AI workflows to the kind of accountability that single-provider systems can&apos;t offer. screamingface is the first application, and it proves the protocol&nbsp;works.
              </p>
              <a
                href="https://url4.ai"
                className="inline-flex items-center gap-1.5 text-sm text-primary hover:opacity-80 transition-opacity mt-2"
                target="_blank"
                rel="noopener noreferrer"
              >
                Learn more about url4
                <ChevronRight className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </section>

        {/* ── Why open AI infrastructure matters ──────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto mb-10">
              <h2
                className="text-2xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                Why open AI infrastructure matters
              </h2>
              <p className="text-muted-foreground">
                When AI runs on an open protocol, the benefits compound. The system is auditable by default. Institutions can participate without giving up control. And the infrastructure belongs to everyone who builds on it, not to a single company. We&apos;ve seen this pattern before. When governments digitized public records in the 1990s, the organizations that moved early built lasting infrastructure. The ones that waited bought vendor&nbsp;lock-in.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-y-8 max-w-2xl mx-auto">

              {/* Independence */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Independence from any single provider
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Hospitals, research labs, agricultural cooperatives, cultural archives. Every sector is now dependent on AI. When that AI is controlled by one company, a pricing change or a policy shift affects everyone. Open ensembles give institutions the ability to serve their communities on their own&nbsp;terms.
                  </p>
                </div>
              </div>

              {/* Transparency */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Transparency by design
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    An open protocol means the system is auditable. How models are routed, what outputs are produced, and how the ensemble makes decisions can all be examined. This is a starting point for the kind of accountability that regulators and civic institutions are asking&nbsp;for.
                  </p>
                </div>
              </div>

              {/* Democratic governance */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    AI as public infrastructure
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    AI infrastructure is becoming as foundational as electricity grids and public roads. Open, federated systems built as public goods and governed collectively are the alternative to a future where a handful of private entities control the most powerful technology of this generation. The question is whether we build them while the window is&nbsp;open.
                  </p>
                </div>
              </div>

            </div>
          </div>
        </section>

        {/* ── Built by OpenMined ──────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border">
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
                is a nonprofit that has been building open-source tools for privacy-preserving AI since 2017. PySyft, the Syft Network, federated learning research. screamingface and url4 are the latest work from an organization with a track record of building infrastructure that keeps data where it lives while letting insights&nbsp;flow.
              </p>
            </div>

            {/* ABC callout */}
            <div className="max-w-2xl mx-auto mt-8 border border-primary/30 rounded-lg p-6 bg-primary/[0.04]">
              <h3
                className="text-sm font-medium text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                The long plan
              </h3>
              <p className="text-sm text-muted-foreground leading-relaxed mb-3">
                screamingface and url4 are early steps. The full vision for where this leads, including how open protocols can support attribution, creator compensation, and democratic AI governance, is laid out in Andrew Trask&apos;s thesis on Attribution-Based Control.
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
              We&apos;re building a coalition around open AI infrastructure. If you want to help make the case while the window is open, here&apos;s how.
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
                  Write with us. Policy briefs, research papers, public statements. We&apos;re building a body of work that makes the case for open AI as public infrastructure.
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
