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
              Deep Voting
            </p>

            {/* Headline */}
            <h1
              className="text-4xl md:text-5xl font-semibold tracking-tight leading-[1.1] mb-12 max-w-3xl"
              style={{ fontFamily: "var(--font-rubik)" }}
            >
              Trust makes AI{" "}
              <span className="text-gradient-gold">more accurate.</span>
            </h1>

            {/* Body */}
            <div className="max-w-2xl space-y-5 text-muted-foreground leading-relaxed">
              <p className="text-foreground/80">
                Today&apos;s AI mashes all training data together, destroying the link between sources and predictions. Data providers lose control the moment they share. Users can&apos;t verify where answers come from. A new architecture called <em>Deep Voting</em> solves both problems at once, and the result is AI that&apos;s more accurate because it&apos;s more&nbsp;trustworthy.
              </p>
            </div>

          </div>
        </section>

        {/* ── How AI loses trust ──────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                How AI loses trust
              </h2>
              <p>
                When a neural network trains, it combines millions of data points through addition. The result is a model that works, but the connection between any specific source and any specific prediction is gone. Permanently.
              </p>
              <p>
                This is the root of every major AI debate right now. Copyright holders can&apos;t prove their work was used. Patients can&apos;t control how their medical data shapes predictions. Auditors can&apos;t trace a biased output back to biased training data. The EU AI Act, GDPR, and similar frameworks are all trying to solve problems that stem from this one architectural choice.
              </p>
              <p>
                Both sides of the open-vs-closed AI debate are reacting to the same broken link. Companies centralize because they can&apos;t offer accountability otherwise. Critics demand openness because they can&apos;t verify anything otherwise. The architecture forces the&nbsp;conflict.
              </p>
            </div>
          </div>
        </section>

        {/* ── Deep Voting ────────────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                Choose who you trust
              </h2>
              <p>
                Deep Voting is a different approach to how AI learns. Instead of pooling all data into a single set of weights, it trains source-specific parameters that stay separate. They only combine at the moment of&nbsp;prediction.
              </p>
              <p>
                This changes the relationship between AI and the people who feed it. Data providers can withdraw their contributions from specific predictions. Users can weight the sources they trust and filter out the ones they don&apos;t. Researchers can trace exactly which training data influenced a given&nbsp;output.
              </p>
              <p className="text-foreground/80">
                Here is what makes it powerful: when you choose which sources to trust, accuracy improves. The system gets better <em>for you</em> because it reflects your judgment about what&apos;s reliable. Trust and accuracy reinforce each other. This is true for individual users choosing their sources, and for data providers choosing who gets to use their&nbsp;work.
              </p>
            </div>
          </div>
        </section>

        {/* ── What trust-based AI makes possible ─────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto mb-10">
              <h2
                className="text-2xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                What trust-based AI makes possible
              </h2>
            </div>
            <div className="grid grid-cols-1 gap-y-8 max-w-2xl mx-auto">

              {/* Privacy & Sovereignty */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Privacy &amp; Sovereignty
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Data stays with its owner. Insights flow. Institutions and communities contribute to AI training while retaining full control over what is shared, with whom, and under what terms. When models are codeveloped using community resources, ownership is built into the&nbsp;protocol.
                  </p>
                </div>
              </div>

              {/* Copyright & Compensation */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Copyright &amp; Compensation
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    When contributions are traceable, creators can be compensated and their rights can be enforced. Attribution survives model training because the architecture is designed to&nbsp;preserve&nbsp;it.
                  </p>
                </div>
              </div>

              {/* Traceability */}
              <div className="flex gap-3">
                <ChevronRight className="w-4 h-4 text-primary mt-1 shrink-0" />
                <div>
                  <h3
                    className="text-base font-medium text-foreground mb-2"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    Traceability
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Every prediction maps back to its sources. Hallucinations and bias become auditable, not just detectable. When something goes wrong, you can find out why and hold the right system&nbsp;accountable.
                  </p>
                </div>
              </div>

              {/* Democratic Governance */}
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
                    AI infrastructure is becoming as foundational as electricity grids and public roads. Open, federated systems built as public goods and governed collectively give civic institutions the ability to serve their communities on their own terms. Human agency over how knowledge is used is preserved at every&nbsp;level.
                  </p>
                </div>
              </div>

            </div>
          </div>
        </section>

        {/* ── Built on open infrastructure ────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                Built on open infrastructure
              </h2>
              <p>
                screamingface is the first working implementation of these ideas. It combines multiple AI models into an ensemble that outperforms any single model, with an attribution layer (built on the open{" "}
                <a
                  href="https://url4.ai"
                  className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  url4
                </a>{" "}
                protocol) that tracks every contribution. The evaluation code is open source and the results are&nbsp;reproducible.
              </p>
              <p>
                We&apos;ve been here before. When governments digitized public records in the 1990s, the organizations that moved early built lasting infrastructure. The ones that waited bought vendor lock-in. The same pattern is unfolding now with AI. Hospitals, research labs, agricultural cooperatives, cultural archives. The opportunity to build open, trust-based AI infrastructure exists now, and the tools to build it already&nbsp;exist.
              </p>
              <p>
                <a
                  href="https://openmined.org"
                  className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  OpenMined
                </a>{" "}
                is the nonprofit behind this work. Founded in 2017, the organization built PySyft (a framework for secure, privacy-preserving machine learning) and assembled one of the largest open-source AI communities in the&nbsp;world.
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
                Andrew Trask&apos;s thesis on Attribution-Based Control lays out the technical and societal argument in full. Deep Voting is Chapter 2. The thesis covers how traceable AI addresses copyright, privacy, bias, and democratic governance.
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
              We&apos;re building a coalition around open, trust-based AI infrastructure. If you want to help make the case while the window is open, here&apos;s how.
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
