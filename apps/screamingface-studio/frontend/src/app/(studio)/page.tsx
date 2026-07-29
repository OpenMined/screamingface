import { ArrowRight, ChevronRight, Lock, Plus, TrendingUp } from "lucide-react";
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
    <div className="flex h-full flex-col overflow-hidden bg-background">
      <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background/95 px-5 backdrop-blur sm:px-6">
        <div data-tauri-drag-region className="flex min-w-0 flex-1 items-center self-stretch">
          <div>
            <h1 className="text-sm font-semibold">Home</h1>
            <p className="hidden text-[11px] text-muted-foreground sm:block">Your fusion workspace</p>
          </div>
        </div>
        <Button size="sm" className="rounded-lg shadow-sm" asChild>
          <Link href="/ensembles/new/" prefetch={false}><Plus className="size-4" />Compose fusion</Link>
        </Button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl p-5 sm:p-6 lg:p-8">
          <section className="flex flex-col gap-5 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="font-mono text-[11px] font-medium uppercase tracking-wider text-primary">Welcome back, irina</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight">Your models are smarter together.</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Continue building fusions, compare evaluation results, or see what is performing best across the hub.</p>
            </div>
            <div className="flex shrink-0 items-center gap-5 font-mono text-[11px] text-muted-foreground">
              <span><strong className="block text-base font-semibold text-foreground">9,431</strong>fusions</span>
              <span className="h-8 w-px bg-border" />
              <span><strong className="block text-base font-semibold text-foreground">184k</strong>evals run</span>
              <span className="h-8 w-px bg-border" />
              <span><strong className="block text-base font-semibold text-accent">+25.6</strong>top gain</span>
            </div>
          </section>

          <section className="pt-7">
            <header className="flex items-end justify-between">
              <div><div className="mb-1 flex items-center gap-2"><TrendingUp className="size-4 text-accent" /><h2 className="text-base font-semibold">Top fusions</h2></div><p className="text-xs text-muted-foreground">Ranked by gain over the best single model.</p></div>
              <Button variant="ghost" size="sm" className="shrink-0 rounded-lg text-muted-foreground hover:text-foreground" asChild><Link href="/leaderboard/" prefetch={false}>View leaderboard <ChevronRight className="size-4" /></Link></Button>
            </header>

            <div className="mt-4 overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm">
              <div className="hidden h-9 items-center gap-3 border-b bg-muted/40 px-5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground sm:flex">
                <span className="w-7" /><span className="min-w-0 flex-1">Fusion</span><span className="w-28 shrink-0">Benchmark</span><span className="w-16 shrink-0 text-right">Gain</span>
              </div>
              {topEnsembles.map((ensemble, index) => (
                <Link className="group flex items-center gap-3 border-b border-border/70 px-4 py-3 font-medium transition-colors last:border-b-0 hover:bg-secondary/45 sm:px-5" href={`/leaderboard/?ensemble=${encodeURIComponent(ensemble.recipe)}`} prefetch={false} key={ensemble.recipe}>
                  <span className="grid size-7 shrink-0 place-items-center rounded-md bg-muted font-mono text-[11px] font-semibold text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">{index + 1}</span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5"><span className="truncate font-mono text-sm font-semibold tracking-tight">{ensemble.recipe}</span>{ensemble.private && <Lock className="size-3 shrink-0 text-muted-foreground" />}</span>
                    <span className="mt-1 flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
                      <span className="flex items-center -space-x-0.5" aria-hidden="true">{ensemble.models.map((provider, dotIndex) => <span className="size-2.5 rounded-full border border-card" key={`${provider}-${dotIndex}`} style={{ background: providerColors[provider] }} />)}</span>
                      <span className="font-mono">{ensemble.models.length} models</span><span className="opacity-40">·</span><span className="truncate">by {ensemble.author}</span>
                    </span>
                  </span>
                  <span className="hidden w-28 shrink-0 font-mono text-[11px] font-medium text-muted-foreground sm:block">{ensemble.benchmark}</span>
                  <span className="w-16 shrink-0 text-right font-mono text-sm font-semibold text-accent">+{ensemble.uplift}</span>
                </Link>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between px-1 text-[11px] text-muted-foreground">
              <span>Updated from recent public evaluations</span>
              <Link href="/ensembles/" prefetch={false} className="inline-flex items-center gap-1 font-medium hover:text-foreground">Your fusions <ArrowRight className="size-3" /></Link>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
