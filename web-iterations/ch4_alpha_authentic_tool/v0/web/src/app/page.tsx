const installCommand = `curl -fsSL https://screamingface.ai/install | sh`;

const steps = [
  {
    number: "01",
    title: "Install",
    description: "One command. Configures locally. Nothing uploaded.",
  },
  {
    number: "02",
    title: "Auto-detect",
    description: "Finds Claude Code, Gemini CLI, Codex, and Ollama on your PATH.",
  },
  {
    number: "03",
    title: "Route",
    description: "Each prompt goes to whichever model scores best on the task.",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col">
      <main className="flex-1">
        {/* Hero */}
        <section className="px-5 pt-12 pb-10 max-w-4xl mx-auto text-center">
          <div className="text-7xl mb-6 select-none">😱</div>
          <h1 className="text-5xl font-semibold tracking-tight leading-tight mb-5">
            SOTA on your laptop.
          </h1>
          <p className="max-w-xl mx-auto leading-relaxed">
            An ensemble of the CLI models you already run. Combines their outputs, picks the best answer. Open source. No new accounts.
          </p>
        </section>

        {/* Install */}
        <section id="install" className="px-5 py-12 relative overflow-hidden">
          <div className="max-w-3xl mx-auto relative">
            <div className="text-center mb-8">
              <h2 className="text-3xl font-semibold mb-2">
                One command
              </h2>
              <p>
                Detects models on your machine. Configures itself. Nothing sent to a server.
              </p>
            </div>

            {/* Command block */}
            <div className="bg-card border border-border rounded-[15px] overflow-hidden mb-8">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-secondary/60">
                <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
                <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
                <span className="w-3 h-3 rounded-full bg-[#28c840]" />
                <span className="ml-auto text-xs font-mono">
                  bash
                </span>
              </div>
              <div className="px-5 py-4 flex items-center gap-3">
                <span className="select-none shrink-0 font-mono">
                  $
                </span>
                <span className="min-w-0 block overflow-x-auto whitespace-nowrap font-mono">
                  {installCommand}
                </span>
              </div>
            </div>

            {/* Steps */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {steps.map((step) => (
                <div key={step.number} className="flex flex-col gap-2">
                  <span className="text-xs font-mono">
                    {step.number}
                  </span>
                  <h3 className="font-medium">
                    {step.title}
                  </h3>
                  <p className="leading-relaxed">
                    {step.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* GitHub */}
        <div className="px-5 py-8 text-center">
          <a
            href="https://github.com/OpenMined/screamingface"
            target="_blank"
            rel="noopener noreferrer"
          >
            github.com/OpenMined/screamingface
          </a>
        </div>
      </main>

      {/* Footer */}
      <footer className="px-5 py-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-foreground">
        <span>😱 screamingface, built by{" "}
          <a
            href="https://openmined.org"
            target="_blank"
            rel="noopener noreferrer"
          >
            OpenMined
          </a>
        </span>
        <a
          href="https://github.com/OpenMined/screamingface"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub
        </a>
      </footer>
    </div>
  );
}
