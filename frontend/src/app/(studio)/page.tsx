import { ArrowRight, ChevronRight, Lock, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

const providerColors: Record<string, string> = { anthropic: "#ca492c", deepmind: "#6976ae", openai: "#53bea9", ollama: "#52aec5", mistral: "#f79763" };
const topEnsembles = [
  { recipe: "private-data-bridge-v1", author: "siddhant_r", models: ["anthropic", "deepmind", "openai"], benchmark: "GPQA Diamond", uplift: "25.6", private: true },
  { recipe: "5-model-heavy", author: "fusion_hunter", models: ["anthropic", "deepmind", "openai", "ollama", "mistral"], benchmark: "GPQA Diamond", uplift: "22.1" },
  { recipe: "llama-boost-v2", author: "tauquir_m", models: ["ollama", "openai"], benchmark: "GPQA Diamond", uplift: "21.9" },
  { recipe: "claude-gemini-fusion", author: "mwatson", models: ["anthropic", "deepmind"], benchmark: "GPQA Diamond", uplift: "19.9" },
  { recipe: "opus-gemini-v3", author: "elena_k", models: ["anthropic", "deepmind"], benchmark: "GPQA Diamond", uplift: "15.0" },
  { recipe: "code-triad", author: "dmitry_b", models: ["anthropic", "openai", "deepmind"], benchmark: "HumanEval+", uplift: "3.6" },
];

export default function HomePage() {
  return (
    <div className="relative h-full overflow-y-auto [scrollbar-color:transparent_transparent] scrollbar-thin hover:[scrollbar-color:color-mix(in_srgb,var(--muted-foreground)_28%,transparent)_transparent] [&::-webkit-scrollbar-thumb:hover]:bg-muted-foreground/40 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-transparent hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/25 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar]:w-1.5 bg-[radial-gradient(circle_at_top_right,color-mix(in_srgb,var(--primary)_9%,transparent),transparent_34%),radial-gradient(circle_at_20%_30%,color-mix(in_srgb,var(--accent)_6%,transparent),transparent_28%)]">
      <section className="mx-auto w-full max-w-4xl px-6 pb-12 pt-24 sm:px-10 sm:pt-24">
        <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-primary/15 bg-card/70 px-3 py-1.5 shadow-sm backdrop-blur">
          <span className="select-none text-lg" aria-hidden="true">😱</span>
          <span className="text-xs font-semibold">ScreamingFace</span>
          <span className="hidden font-mono text-[10px] text-muted-foreground sm:inline">the loudest ensemble hub</span>
        </div>
        <h1 className="max-w-3xl text-4xl font-semibold leading-[1.08] tracking-[-0.035em] sm:text-5xl">Ensembles that beat <span className="text-primary">any single model.</span></h1>
        <p className="mt-5 max-w-2xl text-base leading-7 text-muted-foreground">Compose, evaluate, and share model ensembles that are louder—and smarter—together.</p>
        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Button className="h-10 rounded-lg px-4 shadow-sm" asChild><Link href="/ensembles/new/" prefetch={false}><Sparkles className="size-4" />Compose an ensemble <ArrowRight className="size-4" /></Link></Button>
          <Button variant="outline" className="h-10 rounded-lg bg-card/70 px-4 shadow-sm backdrop-blur" asChild><Link href="/leaderboard/" prefetch={false}><TrendingUp className="size-4" />View leaderboard</Link></Button>
        </div>
        <div className="mt-8 flex flex-wrap gap-2 font-mono text-[11px] text-muted-foreground">
          <span className="rounded-full border bg-card/60 px-3 py-1.5">9,431 ensembles</span>
          <span className="rounded-full border bg-card/60 px-3 py-1.5">184k evals run</span>
          <span className="rounded-full border bg-card/60 px-3 py-1.5">0 of them calm</span>
        </div>
      </section>

      <section className="mx-auto w-full max-w-4xl px-6 pb-24 sm:px-10">
        <header className="flex items-end justify-between border-t border-border/70 pt-9">
          <div><div className="mb-1 flex items-center gap-2"><TrendingUp className="size-4 text-accent" /><h2 className="text-lg font-semibold">Top ensembles</h2></div><p className="text-sm text-muted-foreground">Ranked by gain over the best single model.</p></div>
          <Button variant="ghost" className="h-8 shrink-0 rounded-lg text-muted-foreground hover:text-foreground" asChild><Link href="/leaderboard/" prefetch={false}>All results <ChevronRight className="size-4" /></Link></Button>
        </header>

        <div className="mt-5 overflow-hidden rounded-2xl border border-border/80 bg-card/90 text-card-foreground shadow-[0_16px_50px_-32px_rgba(23,22,29,0.35)] backdrop-blur">
          {topEnsembles.map((ensemble, index) => (
            <Link className="group flex items-center gap-3 border-b border-border/70 px-4 py-3.5 font-medium transition-all last:border-b-0 hover:bg-secondary/45 sm:px-5" href={`/leaderboard/?ensemble=${encodeURIComponent(ensemble.recipe)}`} prefetch={false} key={ensemble.recipe}>
              <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-muted font-mono text-[11px] font-semibold text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">{index + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5"><span className="truncate font-mono text-sm font-semibold tracking-tight">{ensemble.recipe}</span>{ensemble.private && <Lock className="size-3 shrink-0 text-muted-foreground" />}</span>
                <span className="mt-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center -space-x-0.5" aria-hidden="true">{ensemble.models.map((provider, dotIndex) => <span className="size-2.5 rounded-full border border-card" key={`${provider}-${dotIndex}`} style={{ background: providerColors[provider] }} />)}</span>
                  <span className="font-mono">{ensemble.models.length} models</span><span className="opacity-40">·</span><span className="truncate">by {ensemble.author}</span>
                </span>
              </span>
              <span className="hidden shrink-0 font-mono text-[11px] font-medium text-muted-foreground sm:block">{ensemble.benchmark}</span>
              <span className="w-16 shrink-0 rounded-lg bg-accent/10 px-2 py-1 text-right font-mono text-sm font-semibold text-accent">+{ensemble.uplift}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
