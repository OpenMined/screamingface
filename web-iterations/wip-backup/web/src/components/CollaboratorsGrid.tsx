// Placeholder collaboration cards.
// Replace logos and content as real partnerships, papers, blogs, and integrations are confirmed.

import {
  LogoHuggingFace,
  LogoMozilla,
  LogoArXiv,
  LogoMIT,
  LogoWired,
  LogoEleutherAI,
} from "@/components/logos";

type LogoComponent = React.ComponentType<{ className?: string }>;

const collaborators: {
  Logo: LogoComponent;
  type: string;
  description: string;
  href: string;
}[] = [
  {
    Logo: LogoArXiv,
    type: "co-authored paper",
    description: "Ensemble accuracy methodology on the HLE benchmark.",
    href: "#",
  },
  {
    Logo: LogoHuggingFace,
    type: "blog",
    description: "Featured in Open LLM Leaderboard coverage.",
    href: "#",
  },
  {
    Logo: LogoEleutherAI,
    type: "integration",
    description: "Pythia and GPT-NeoX model series natively supported.",
    href: "#",
  },
  {
    Logo: LogoMIT,
    type: "research",
    description: "Collaboration on federated AI benchmarking design.",
    href: "#",
  },
  {
    Logo: LogoMozilla,
    type: "partnership",
    description: "Named in the Responsible AI infrastructure report.",
    href: "#",
  },
  {
    Logo: LogoWired,
    type: "press",
    description: "Can open AI ensembles outpace the frontier labs?",
    href: "#",
  },
];

export default function CollaboratorsGrid() {
  return (
    <section className="px-6 py-20 border-t border-border">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-12">
          <p
            className="text-xs text-muted-foreground uppercase tracking-widest mb-3"
            style={{ fontFamily: "var(--font-sometype-mono)" }}
          >
            placeholder — replace with real collaborations
          </p>
          <h2
            className="text-3xl font-semibold"
            style={{ fontFamily: "var(--font-rubik)" }}
          >
            Collaborations
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {collaborators.map((c, i) => (
            <a
              key={i}
              href={c.href}
              className="bg-card border border-border rounded-[5px] overflow-hidden hover:border-foreground/20 transition-colors group"
            >
              {/* Logo area */}
              <div className="h-24 flex items-center justify-center px-8 text-foreground/80 group-hover:text-foreground transition-colors">
                <c.Logo className="h-8 w-auto max-w-[140px]" />
              </div>

              {/* Divider + details */}
              <div className="border-t border-border px-5 py-4 flex flex-col gap-2">
                <span
                  className="text-[10px] text-muted-foreground self-start"
                  style={{ fontFamily: "var(--font-sometype-mono)" }}
                >
                  {c.type}
                </span>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {c.description}
                </p>
              </div>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
