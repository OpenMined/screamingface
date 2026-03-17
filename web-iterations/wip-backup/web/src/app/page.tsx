import LeaderboardChart from "@/components/LeaderboardChart";
import EmailCapture from "@/components/EmailCapture";
import CollaboratorsGrid from "@/components/CollaboratorsGrid";

const installCommand = `curl -fsSL https://screamingface.ai/install | sh`;

const steps = [
  {
    number: "01",
    title: "Install",
    description:
      "One command. Downloads and configures screamingface on your machine. Nothing is uploaded during setup.",
  },
  {
    number: "02",
    title: "Auto-detected",
    description:
      "screamingface reads your PATH and existing configs. Claude Code, Gemini CLI, Codex, and Ollama are found and wired up automatically.",
  },
  {
    number: "03",
    title: "Just code",
    description:
      "Use your normal CLI workflow. We don't change your setup. We route every prompt to whichever model scores best on the task.",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <header className="border-b border-border px-6 py-4 flex items-center justify-between">
        <span className="text-lg font-medium tracking-tight" style={{ fontFamily: "var(--font-rubik)" }}>
          😱 screamingface
        </span>
        <nav className="flex items-center gap-6 text-sm text-muted-foreground">
          <a href="#leaderboard" className="hover:text-foreground transition-colors">
            Leaderboard
          </a>
          <a href="#install" className="hover:text-foreground transition-colors">
            Install
          </a>
          <a
            href="https://github.com/OpenMined/screamingface"
            className="hover:text-foreground transition-colors"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
        </nav>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="px-6 pt-24 pb-20 max-w-4xl mx-auto text-center">
          <div className="text-7xl mb-8 select-none">😱</div>
          <h1
            className="text-5xl font-semibold tracking-tight leading-tight mb-6"
            style={{ fontFamily: "var(--font-rubik)" }}
          >
            <span className="text-gradient-gold">SOTA</span> on your laptop.
          </h1>
          <p className="text-lg text-muted-foreground max-w-xl mx-auto leading-relaxed mb-4">
            The models you already use (Claude Code, Gemini CLI, Codex, Ollama) combined into an ensemble that consistently outscores any one of them. No new workflow. No new subscription.
          </p>
          <p className="text-sm text-muted-foreground max-w-md mx-auto">
            Skeptical?{" "}
            <a href="#leaderboard" className="text-primary hover:opacity-80 transition-opacity">
              See the benchmark scores
            </a>
            , then run the evals yourself.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <a
              href="#install"
              className="gradient-gold text-[#1a1720] px-6 py-3 rounded-lg font-medium text-sm hover:opacity-90 transition-opacity"
            >
              Get started
            </a>
            <a
              href="https://github.com/OpenMined/screamingface"
              className="border border-border px-6 py-3 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
              target="_blank"
              rel="noopener noreferrer"
            >
              View on GitHub
            </a>
          </div>
        </section>

        {/* ── Internal team callout (REMOVE BEFORE PUBLIC LAUNCH) ──── */}
        <section className="px-6 py-10 border-t border-primary/30 bg-primary/[0.04]">
          <div className="max-w-3xl mx-auto">
            <div>
              <div className="flex items-center gap-3 mb-5">
                <span className="text-2xl select-none">👋</span>
                <h2
                  className="text-lg font-semibold text-foreground"
                  style={{ fontFamily: "var(--font-rubik)" }}
                >
                  OpenMined team: how screamingface 😱 fits in
                </h2>
              </div>
              <div className="space-y-4 text-sm text-muted-foreground leading-relaxed">
                <div className="flex items-start gap-3">
                  <span className="text-base select-none shrink-0 mt-0.5">▸</span>
                  <p>
                    The market adopts what performs best. screamingface gives us a public stage to prove that, and a place where every bet at OpenMined can show its value through shared leaderboards the market already understands.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-base select-none shrink-0 mt-0.5">▸</span>
                  <p>
                    Right now, screamingface achieves SOTA performance through open model ensembling, using only public data and public APIs. That&apos;s the baseline. It proves the concept and builds an audience. As your bets mature, they plug into this ecosystem through{" "}
                    <a
                      href="https://url4.ai"
                      className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      url4
                    </a>
                    , the open protocol underneath screamingface that&apos;s designed as the grammar layer for Attribution-Based Control.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-base select-none shrink-0 mt-0.5">▸</span>
                  <p>
                    The leaderboards are where this comes together. Imagine the current benchmark results, then a new leaderboard where private news media data from Network Source AI gets added and the scores jump in that domain. Or where remote data science capabilities improve performance on a different benchmark. Each bet can demonstrate its value through a shared set of leaderboards that the market already understands.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <span className="text-base select-none shrink-0 mt-0.5">▸</span>
                  <p>
                    The public-facing site (what you see below) focuses on the ensemble performance story. The connection to your work will grow as the leaderboards expand and the bets integrate. The deeper vision lives in url4 and the{" "}
                    <a
                      href="https://attribution-based-control.ai"
                      className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      ABC thesis
                    </a>
                    , and will surface publicly as the work progresses.
                  </p>
                </div>
                <p className="text-xs text-muted-foreground/60 mt-4">
                  This section is for internal review only and will be removed before public launch.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Leaderboard */}
        <section
          id="leaderboard"
          className="px-6 py-20 border-t border-border bg-card/40"
        >
          <div className="max-w-3xl mx-auto">
            <div className="text-center mb-12">
              <h2
                className="text-3xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                The ensemble wins
              </h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                HLE (Humanity&apos;s Last Exam) multiple-choice accuracy. The ensemble combines the models you already have. It doesn&apos;t require anything new.
              </p>
            </div>
            <div className="bg-card border border-border rounded-lg p-8">
              <LeaderboardChart />
            </div>
            <p className="text-xs text-muted-foreground text-center mt-5">
              These scores are reproducible. Evaluation code is open source.{" "}
              <a
                href="https://github.com/OpenMined/screamingface"
                className="underline underline-offset-2 hover:text-foreground transition-colors"
                target="_blank"
                rel="noopener noreferrer"
              >
                run it yourself
              </a>
              .
            </p>
          </div>
        </section>

        {/* Install */}
        <section id="install" className="px-6 py-24 border-t border-border relative overflow-hidden">
          {/* Subtle radial glow behind command block */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none" aria-hidden>
            <div className="w-[700px] h-[320px] rounded-full bg-primary/[0.06] blur-[90px]" />
          </div>

          <div className="max-w-3xl mx-auto relative">
            <div className="text-center mb-12">
              <h2
                className="text-3xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                One command to install
              </h2>
              <p className="text-muted-foreground">
                screamingface detects every model on your machine and configures itself automatically. Nothing is sent to a server during setup.
              </p>
            </div>

            {/* Command block — terminal style */}
            <div className="bg-card border border-border rounded-xl overflow-hidden mb-12 shadow-xl shadow-black/30">
              {/* Terminal chrome */}
              <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-secondary/60">
                <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
                <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
                <span className="w-3 h-3 rounded-full bg-[#28c840]" />
                <span
                  className="ml-auto text-xs text-muted-foreground"
                  style={{ fontFamily: "var(--font-sometype-mono)" }}
                >
                  bash
                </span>
              </div>
              {/* Command */}
              <div className="px-6 py-5 flex items-center gap-3 text-sm">
                <span
                  className="text-primary select-none shrink-0"
                  style={{ fontFamily: "var(--font-sometype-mono)" }}
                >
                  $
                </span>
                <span
                  className="min-w-0 block text-foreground overflow-x-auto whitespace-nowrap"
                  style={{ fontFamily: "var(--font-sometype-mono)" }}
                >
                  {installCommand}
                </span>
              </div>
            </div>

            {/* Steps */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {steps.map((step) => (
                <div key={step.number} className="flex flex-col gap-3">
                  <span
                    className="text-xs text-primary"
                    style={{ fontFamily: "var(--font-sometype-mono)" }}
                  >
                    {step.number}
                  </span>
                  <h3
                    className="font-medium text-foreground"
                    style={{ fontFamily: "var(--font-rubik)" }}
                  >
                    {step.title}
                  </h3>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {step.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Collaborators */}
        <CollaboratorsGrid />

        {/* Email capture */}
        <EmailCapture />
      </main>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
        <span>😱 screamingface, built by{" "}
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
          <a
            href="https://github.com/OpenMined/screamingface"
            className="hover:text-foreground transition-colors"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          <a
            href="/why"
            className="hover:text-foreground transition-colors"
          >
            Why it matters
          </a>
        </nav>
      </footer>
    </div>
  );
}
