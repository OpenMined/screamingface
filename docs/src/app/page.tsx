import LeaderboardChart from "@/components/LeaderboardChart";

const installCommand = `curl -fsSL https://screamingface.ai/install | sh`;

const steps = [
  {
    number: "01",
    title: "Install",
    description:
      "One command downloads and configures screamingface on your machine.",
  },
  {
    number: "02",
    title: "Auto-detected",
    description:
      "Claude Code, Gemini CLI, Codex, and Ollama are detected and configured automatically.",
  },
  {
    number: "03",
    title: "Just code",
    description:
      "Use your normal coding CLI. The ensemble routes every prompt to the best available model.",
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
          <p className="text-lg text-muted-foreground max-w-xl mx-auto leading-relaxed">
            Combine Claude Code, Gemini CLI, Codex, and Ollama into an ensemble that beats any single model on state-of-the-art benchmarks — without changing how you code.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <a
              href="#install"
              className="gradient-gold text-[#1a1720] px-6 py-3 rounded-lg font-medium text-sm hover:opacity-90 transition-opacity"
            >
              Get started
            </a>
            <a
              href="#leaderboard"
              className="border border-border px-6 py-3 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
            >
              See the benchmarks
            </a>
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
                Beat SOTA. Every prompt.
              </h2>
              <p className="text-muted-foreground max-w-md mx-auto">
                By ensembling the models you already have, screamingface consistently outperforms any individual frontier model.
              </p>
            </div>
            <div className="bg-card border border-border rounded-lg p-8">
              <LeaderboardChart />
            </div>
          </div>
        </section>

        {/* Install */}
        <section id="install" className="px-6 py-20 border-t border-border">
          <div className="max-w-3xl mx-auto">
            <div className="text-center mb-12">
              <h2
                className="text-3xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                One command to install.
              </h2>
              <p className="text-muted-foreground">
                screamingface detects every model on your machine and configures itself
                automatically.
              </p>
            </div>

            {/* Command block */}
            <div className="bg-card border border-border rounded-xl px-6 py-5 flex items-center gap-3 text-sm mb-12">
              <span className="text-muted-foreground select-none shrink-0" style={{ fontFamily: "var(--font-sometype-mono)" }}>$</span>
              <span
                className="min-w-0 block text-foreground overflow-x-auto whitespace-nowrap"
                style={{ fontFamily: "var(--font-sometype-mono)" }}
              >
                {installCommand}
              </span>
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
      </main>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-8 text-center text-sm text-muted-foreground">
        <p>
          😱 screamingface — built by{" "}
          <a
            href="https://openmined.org"
            className="hover:text-foreground transition-colors underline underline-offset-2"
            target="_blank"
            rel="noopener noreferrer"
          >
            OpenMined
          </a>
        </p>
      </footer>
    </div>
  );
}
