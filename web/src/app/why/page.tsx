import EmailCapture from "@/components/EmailCapture";
import CollaboratorsGrid from "@/components/CollaboratorsGrid";
import { ChevronRight } from "lucide-react";

// All sections use max-w-4xl as the outer container for consistent left-edge alignment.
// Body text is constrained to max-w-2xl mx-auto within the outer max-w-4xl container.
// The hero uses the full 4xl width for its two-column layout.

const stakes = [
  { title: "Privacy",         body: "Institutions contribute data while keeping full control." },
  { title: "Copyright",       body: "Creator attribution rights survive model training." },
  { title: "Hallucination",   body: "Predictions stay traceable back to their sources." },
  { title: "Bias",            body: "Each community governs its own contributions." },
  { title: "Value Alignment", body: "AI values shaped by everyone who uses it." },
  { title: "Democracy",       body: "Strength from everything the free market builds together." },
];

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
              An open letter
            </p>

            {/* Headline */}
            <h1
              className="text-4xl md:text-5xl font-semibold tracking-tight leading-[1.1] mb-12 max-w-3xl"
              style={{ fontFamily: "var(--font-rubik)" }}
            >
              The best AI is{" "}
              <span className="text-gradient-gold">built together.</span>
            </h1>

            {/* Two-column body: narrative left, stat callout right */}
            <div className="grid grid-cols-1 md:grid-cols-[1fr_200px] gap-10 items-start">
              <div className="space-y-5 text-muted-foreground leading-relaxed">
                <p className="text-foreground/80">
                  We are in a narrow window. Right now, open ensembles — systems that combine the outputs of many AI models — consistently outperform any single model on every benchmark we&apos;ve tested. That&apos;s not a temporary anomaly. It&apos;s a structural advantage that belongs to no one company.
                </p>
                <p>
                  But it won&apos;t last. Within roughly two years, the major AI labs will respond — by building their own ensembles, tightening API access, or making the open combination structurally harder. The window to establish open AI infrastructure, before the commercial response closes it, is now.
                </p>
              </div>

              {/* Stat callout */}
              <div className="md:border-l md:border-border md:pl-8 pt-1 flex flex-col gap-3">
                <div
                  className="text-4xl font-semibold leading-none text-gradient-gold"
                  style={{ fontFamily: "var(--font-rubik)" }}
                >
                  ~2 yrs
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  The estimated window before major AI companies respond to open ensembles — with competing systems or restricted access.
                </p>
              </div>
            </div>

          </div>
        </section>

        {/* ── We've been here before ───────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto space-y-5 text-muted-foreground leading-relaxed">
              <h2
                className="text-2xl font-semibold text-foreground mb-2"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                We&apos;ve been here before.
              </h2>
              <p>
                When governments began digitizing public records, libraries, and civic data in the 1990s and 2000s, the organizations that acted early built lasting infrastructure. The ones that waited bought vendor lock-in.
              </p>
              <p>
                The same pattern is unfolding now. Public institutions — governments, universities, hospitals, civil society organizations — are generating some of the most valuable training data in the world: medical records, legal precedents, scientific literature, public discourse. If that data trains models controlled by private companies, the public interest loses twice: once when the data leaves, and again when the intelligence comes back behind a paywall or a terms-of-service agreement.
              </p>
              <p>
                The window between now and the commercial response is the time to fund federated data infrastructure — open, auditable, collectively governed — that can compete with what any single company builds alone. That requires public funding, institutional collaboration, and people who care enough to push for it.
              </p>
            </div>
          </div>
        </section>

        {/* ── What's at stake ─────────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto mb-10">
              <h2
                className="text-2xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                What&apos;s at stake.
              </h2>
              <p className="text-muted-foreground">
                Centralized AI creates specific, solvable problems. Open, federated systems address each of them.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-5 max-w-2xl mx-auto">
              {stakes.map((item) => (
                <div key={item.title} className="flex gap-2.5">
                  <ChevronRight className="w-3.5 h-3.5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <h3
                      className="text-sm font-medium text-foreground"
                      style={{ fontFamily: "var(--font-rubik)" }}
                    >
                      {item.title}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      {item.body}
                    </p>
                  </div>
                </div>
              ))}
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

        {/* ── The proof exists ────────────────────────────────────────────── */}
        <section className="px-6 py-16 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto">
              <h2
                className="text-2xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                The proof exists.
              </h2>
              <p className="text-muted-foreground leading-relaxed mb-6">
                screamingface is a working AI ensemble, built by{" "}
                <a
                  href="https://openmined.org"
                  className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  OpenMined
                </a>
                , that combines Claude Code, Gemini CLI, Codex, and Ollama into a system that beats any single model on published benchmarks. The evaluation code is open source and the results are reproducible. This isn&apos;t a theoretical argument — it&apos;s running today.
              </p>
              <a
                href="/"
                className="inline-flex items-center gap-1.5 text-sm text-primary hover:opacity-80 transition-opacity"
              >
                See the technical proof
                <ChevronRight className="w-3.5 h-3.5" />
              </a>
            </div>
          </div>
        </section>

        {/* ── Collaborators ───────────────────────────────────────────────── */}
        <CollaboratorsGrid />

        {/* ── Get involved ────────────────────────────────────────────────── */}
        <section id="get-involved" className="px-6 py-20 border-t border-border bg-card/40">
          <div className="max-w-4xl mx-auto">
            <div className="max-w-2xl mx-auto">
              <h2
                className="text-2xl font-semibold mb-3"
                style={{ fontFamily: "var(--font-rubik)" }}
              >
                Get involved.
              </h2>
              <p className="text-muted-foreground text-sm mb-10 leading-relaxed">
                We&apos;re looking for researchers, journalists, and policy advocates to co-author writing, share institutional perspectives, and help build the case for federated public AI. If that&apos;s you, say hello.
              </p>
              <EmailCapture />
            </div>
          </div>
        </section>

      </main>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
        <span>
          😱 screamingface — built by{" "}
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
            href="https://attribution-based-control.ai/#societal-consequences"
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
