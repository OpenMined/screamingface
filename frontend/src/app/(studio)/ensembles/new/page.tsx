"use client";

import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronLeft,
  Copy,
  Pencil,
  Plug,
  Plus,
  Repeat,
  Scale,
  Share2,
  Upload,
  X,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  type SavedEnsemble,
  useEnsembleStore,
} from "@/lib/ensemble-store";
import { cn } from "@/lib/utils";

type ReduceStrategy =
  | "majority_vote"
  | "weighted_avg"
  | "best_of_n"
  | "merge";

type Model = {
  id: string;
  name: string;
  providerId: string;
  providerName: string;
};

type Slot = {
  model: Model;
  systemPrompt: string;
  weight: number;
};

const availableModels: Model[] = [
  { id: "an-1", name: "Claude Opus 4.8", providerId: "anthropic", providerName: "Anthropic" },
  { id: "an-2", name: "Claude Sonnet 4.6", providerId: "anthropic", providerName: "Anthropic" },
  { id: "oa-1", name: "GPT-5", providerId: "openai", providerName: "OpenAI" },
  { id: "oa-3", name: "o3", providerId: "openai", providerName: "OpenAI" },
  { id: "dm-1", name: "Gemini 2.5 Pro", providerId: "deepmind", providerName: "Google DeepMind" },
  { id: "dm-2", name: "Gemini 2.5 Flash", providerId: "deepmind", providerName: "Google DeepMind" },
  { id: "ol-1", name: "Llama 3.3 70B", providerId: "ollama", providerName: "Ollama" },
  { id: "or-6", name: "DeepSeek-R1", providerId: "openrouter", providerName: "OpenRouter" },
];

const providerColors: Record<string, string> = {
  anthropic: "#ca492c",
  openai: "#53bea9",
  deepmind: "#6976ae",
  ollama: "#52aec5",
  openrouter: "#937098",
};

const strategies: {
  value: ReduceStrategy;
  label: string;
  description: string;
}[] = [
  {
    value: "majority_vote",
    label: "Majority Vote",
    description: "Judge picks the most common answer",
  },
  {
    value: "weighted_avg",
    label: "Weighted Average",
    description: "Blend answers weighted by confidence",
  },
  {
    value: "best_of_n",
    label: "Best-of-N",
    description: "Judge ranks and selects the top response",
  },
  {
    value: "merge",
    label: "Merge",
    description: "Judge merges every answer into one",
  },
];

function ProviderDot({ provider }: { provider: string }) {
  return (
    <span
      className="inline-block size-2 shrink-0 rounded-full"
      style={{ background: providerColors[provider] ?? "var(--primary)" }}
    />
  );
}

function StageSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string; description: string }[];
  onChange: (value: string) => void;
}) {
  const selected = options.find((option) => option.value === value)!;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="rounded-lg bg-card">
          {selected.label}
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60 overflow-hidden p-0">
        <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
          {options.map((option) => (
            <DropdownMenuRadioItem
              key={option.value}
              value={option.value}
              className="rounded-none py-2.5 pl-3 pr-8"
            >
              <span className="min-w-0">
                <span className="block text-xs font-medium">{option.label}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  {option.description}
                </span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function parseRecipe(raw: string) {
  const match = raw.match(/^url4:\/\/([^?]+)\?(.*)$/);
  if (!match) return null;
  const params = new URLSearchParams(match[2]);
  const slots = (params.get("models") ?? "")
    .split(/[+\s]+/)
    .map((id) => availableModels.find((model) => model.id === id))
    .filter((model): model is Model => Boolean(model))
    .map((model) => ({ model, systemPrompt: "", weight: 0.5 }));
  const reduce = params.get("reduce") as ReduceStrategy | null;
  return {
    name: decodeURIComponent(match[1]).replace(/\s+/g, "-").toLowerCase(),
    slots,
    strategy: strategies.some((item) => item.value === reduce)
      ? reduce!
      : ("majority_vote" as ReduceStrategy),
    judgeId: params.get("judge"),
  };
}

function EnsembleComposer() {
  const searchParams = useSearchParams();
  const requestedId = searchParams.get("id");
  const importedRecipe = searchParams.get("recipe");
  const [newEnsembleId] = useState(() =>
    typeof window === "undefined"
      ? "new-ensemble"
      : window.crypto.randomUUID(),
  );
  const ensembleId = requestedId ?? newEnsembleId;
  const storeHasHydrated = useEnsembleStore((state) => state.hasHydrated);
  const upsertEnsemble = useEnsembleStore((state) => state.upsertEnsemble);
  const setActiveEnsemble = useEnsembleStore(
    (state) => state.setActiveEnsemble,
  );
  const [name, setName] = useState("ensemble-1");
  const [editingName, setEditingName] = useState(false);
  const [library, setLibrary] = useState<Model[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [strategy, setStrategy] =
    useState<ReduceStrategy>("majority_vote");
  const [customReduce, setCustomReduce] = useState(false);
  const [loopMode, setLoopMode] = useState<"parallel" | "custom">("parallel");
  const [judgeId, setJudgeId] = useState<string | null>(null);
  const [tab, setTab] = useState<"compose" | "runs">("compose");
  const [copied, setCopied] = useState(false);
  const [autoSave, setAutoSave] = useState(true);
  const [loadedEnsembleId, setLoadedEnsembleId] = useState<string | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState("");
  const [savedFlash, setSavedFlash] = useState(false);

  useEffect(() => {
    if (!storeHasHydrated) return;
    const storedEnsembles = useEnsembleStore.getState().ensembles;
    const saved = requestedId
      ? storedEnsembles.find((ensemble) => ensemble.id === requestedId) ?? null
      : null;
    const parsed = importedRecipe ? parseRecipe(importedRecipe) : null;
    const frame = window.requestAnimationFrame(() => {
      if (saved) {
        setName(saved.name);
        setSlots(saved.slots);
        setLibrary(saved.slots.map((slot) => slot.model));
        setStrategy(saved.strategy);
        setCustomReduce(saved.customReduce);
        setLoopMode(saved.loopMode);
        setJudgeId(saved.judgeId);
        setSavedSnapshot(JSON.stringify({ ...saved, updatedAt: 0 }));
      } else if (parsed) {
        setName(parsed.name);
        setSlots(parsed.slots);
        setLibrary(parsed.slots.map((slot) => slot.model));
        setStrategy(parsed.strategy);
        setCustomReduce(false);
        setLoopMode("parallel");
        setJudgeId(null);
        setSavedSnapshot("");
        if (
          parsed.judgeId &&
          parsed.slots.some((slot) => slot.model.id === parsed.judgeId)
        ) {
          setJudgeId(parsed.judgeId);
        }
      } else {
        setName("ensemble-1");
        setSlots([]);
        setLibrary([]);
        setStrategy("majority_vote");
        setCustomReduce(false);
        setLoopMode("parallel");
        setJudgeId(null);
        setSavedSnapshot("");
      }
      setActiveEnsemble(ensembleId);
      setLoadedEnsembleId(ensembleId);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [
    ensembleId,
    importedRecipe,
    requestedId,
    setActiveEnsemble,
    storeHasHydrated,
  ]);

  const selectedStrategy = strategies.find((item) => item.value === strategy)!;
  const judge = slots.find((slot) => slot.model.id === judgeId)?.model;
  const weightSum = slots
    .filter((slot) => slot.model.id !== judgeId)
    .reduce((sum, slot) => sum + slot.weight, 0);
  const recipe = `url4://${name}?models=${slots.map((slot) => slot.model.id).join("+")}&reduce=${customReduce ? "script:custom" : strategy}&loop=${loopMode === "custom" ? "script:custom" : "parallel"}${!customReduce && judgeId ? `&judge=${judgeId}` : ""}`;
  const draft = useMemo<SavedEnsemble>(
    () => ({
      id: ensembleId,
      name,
      slots,
      strategy,
      customReduce,
      loopMode,
      judgeId,
      runs: 0,
      updatedAt: 0,
    }),
    [
      customReduce,
      ensembleId,
      judgeId,
      loopMode,
      name,
      slots,
      strategy,
    ],
  );
  const draftSnapshot = JSON.stringify(draft);
  const ready = loadedEnsembleId === ensembleId;
  const dirty = ready && draftSnapshot !== savedSnapshot;

  useEffect(() => {
    if (!ready || !autoSave || !dirty) return;
    const timer = window.setTimeout(() => {
      upsertEnsemble({ ...draft, updatedAt: Date.now() });
      setSavedSnapshot(draftSnapshot);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [
    autoSave,
    dirty,
    draft,
    draftSnapshot,
    ready,
    upsertEnsemble,
  ]);

  function saveDraft() {
    upsertEnsemble({ ...draft, updatedAt: Date.now() });
    setSavedSnapshot(draftSnapshot);
    setSavedFlash(true);
    window.setTimeout(() => setSavedFlash(false), 1500);
  }

  function addModel(model: Model) {
    if (slots.some((slot) => slot.model.id === model.id)) return;
    setSlots((current) => [
      ...current,
      { model, systemPrompt: "", weight: 0.5 },
    ]);
  }

  function removeModel(id: string) {
    setSlots((current) => current.filter((slot) => slot.model.id !== id));
    if (judgeId === id) setJudgeId(null);
  }

  async function copyRecipe() {
    await navigator.clipboard.writeText(recipe);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <Tabs
      value={tab}
      onValueChange={(value) => setTab(value as "compose" | "runs")}
      className="flex h-full flex-col overflow-hidden bg-background"
    >
      <header className="shrink-0 border-b px-5 py-4 sm:px-8">
        <Link
          href="/ensembles/"
          prefetch={false}
          className="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="size-3.5" />
          All ensembles
        </Link>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            {editingName ? (
              <Input
                autoFocus
                value={name}
                className="h-8 w-52 font-mono text-base font-semibold"
                onChange={(event) =>
                  setName(
                    event.target.value.replace(/\s+/g, "-").toLowerCase(),
                  )
                }
                onBlur={() => setEditingName(false)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === "Escape") {
                    setEditingName(false);
                  }
                }}
              />
            ) : (
              <button
                type="button"
                className="group flex min-w-0 items-center gap-2"
                onClick={() => setEditingName(true)}
                title="Rename ensemble"
              >
                <span className="truncate font-mono text-base font-semibold">
                  {name}
                </span>
                <Pencil className="size-3 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </button>
            )}
            <span className="text-xs text-muted-foreground">
              {slots.length} models · 0 runs
            </span>
            {!autoSave && dirty && (
              <Badge variant="secondary" className="bg-primary/15 text-primary">
                unsaved
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-2 sm:gap-3">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              Auto-save
              <Switch
                checked={autoSave}
                onCheckedChange={(checked) => setAutoSave(checked)}
              />
            </label>
            <Button
              variant="outline"
              size="sm"
              disabled={autoSave || !dirty}
              onClick={saveDraft}
            >
              {savedFlash ? (
                <Check className="size-3.5 text-accent" />
              ) : (
                <Upload className="size-3.5 rotate-180" />
              )}
              {savedFlash ? "Saved" : "Save"}
            </Button>
            <Button variant="outline" size="sm" onClick={copyRecipe}>
              {copied ? (
                <Check className="size-3.5 text-accent" />
              ) : (
                <Share2 className="size-3.5" />
              )}
              {copied ? "Copied" : "Share url4"}
            </Button>
          </div>
        </div>

        <TabsList className="-mb-4 mt-4">
          <TabsTrigger value="compose">Compose</TabsTrigger>
          <TabsTrigger value="runs">Runs</TabsTrigger>
        </TabsList>
      </header>

      <TabsContent
        value="compose"
        className="m-0 flex min-h-0 flex-1 overflow-hidden"
      >
          <aside className="w-56 shrink-0 overflow-y-auto border-r px-4 py-5">
            <p className="mb-3 text-xs text-muted-foreground">Add from library</p>
            {library.length === 0 ? (
              <div className="flex flex-col items-start gap-4">
                <p className="text-xs leading-relaxed text-muted-foreground/50">
                  No models in your library yet. Add some in the Models tab.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="rounded-lg"
                  asChild
                >
                  <Link href="/models/" prefetch={false}>
                    <Plug className="size-3.5" />
                    Connect Models
                  </Link>
                </Button>
              </div>
            ) : (
              <div className="flex flex-col gap-1">
                {library.map((model) => {
                  const selected = slots.some(
                    (slot) => slot.model.id === model.id,
                  );
                  return (
                    <button
                      type="button"
                      key={model.id}
                      disabled={selected}
                      onClick={() => addModel(model)}
                      className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      <ProviderDot provider={model.providerId} />
                      <span className="min-w-0 flex-1 truncate text-xs">
                        {model.name}
                      </span>
                      {!selected && (
                        <Plus className="size-3 shrink-0 text-muted-foreground" />
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </aside>

          <main className="min-w-0 flex-1 overflow-y-auto px-5 py-6 sm:px-8">
            <div className="mx-auto flex max-w-2xl flex-col">
              {slots.length === 1 && (
                <div className="mb-5 flex items-start gap-2.5 rounded-xl border border-primary/40 bg-primary/10 px-4 py-3 text-primary">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  <p className="text-xs leading-snug">
                    An ensemble needs at least 2 models — the loop and reduce
                    steps have no effect on a single model. Add another from the
                    library on the left.
                  </p>
                </div>
              )}

              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Repeat className="size-3.5 text-muted-foreground" />
                  <span className="text-sm font-medium">Loop</span>
                  <span className="text-xs text-muted-foreground">
                    · {loopMode === "custom" ? "Custom script…" : "runs the models"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <StageSelect
                    value={loopMode}
                    options={[
                      {
                        value: "parallel",
                        label: "Parallel",
                        description: "Run every model on each question",
                      },
                      {
                        value: "custom",
                        label: "Custom script…",
                        description: "Plug in a loop script",
                      },
                    ]}
                    onChange={(value) =>
                      setLoopMode(value as "parallel" | "custom")
                    }
                  />
                  {loopMode === "custom" && (
                    <span className="text-xs text-muted-foreground/70">
                      No loop scripts — add one in Scripts
                    </span>
                  )}
                </div>
              </div>

              <div className="flex flex-col gap-2.5">
                {slots.length === 0 ? (
                  <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border/40 py-12 text-muted-foreground">
                    <Plus className="size-5 opacity-20" />
                    <span className="text-sm opacity-50">
                      Add models from the library on the left
                    </span>
                  </div>
                ) : (
                  slots.map((slot, index) => {
                    const isJudge = slot.model.id === judgeId;
                    return (
                      <article
                        key={slot.model.id}
                        className={cn(
                          "rounded-xl border bg-card p-3.5",
                          isJudge && "border-accent/50",
                        )}
                      >
                        <div className="mb-2.5 flex items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-2.5">
                            <span className="w-4 shrink-0 font-mono text-xs text-muted-foreground/60">
                              {index + 1}
                            </span>
                            <ProviderDot provider={slot.model.providerId} />
                            <span className="truncate text-sm font-medium">
                              {slot.model.name}
                            </span>
                            <span className="shrink-0 font-mono text-xs text-muted-foreground">
                              [{slot.model.providerName}]
                            </span>
                            {isJudge && (
                              <Badge
                                variant="secondary"
                                className="shrink-0 gap-0.5 bg-accent/15 text-accent"
                              >
                                <Scale className="size-2.5" />
                                judge
                              </Badge>
                            )}
                          </div>
                          <div className="flex shrink-0 items-center gap-1.5">
                            {!customReduce && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                  setJudgeId(isJudge ? null : slot.model.id)
                                }
                                className={cn(
                                  "h-7 rounded-lg px-2",
                                  isJudge
                                    ? "border-accent/50 bg-accent/10 text-accent"
                                    : "text-muted-foreground",
                                )}
                              >
                                <Scale className="size-3" />
                                {isJudge ? "Judge" : "Make judge"}
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-7 text-muted-foreground"
                              aria-label={`Remove ${slot.model.name}`}
                              onClick={() => removeModel(slot.model.id)}
                            >
                              <X className="size-3.5" />
                            </Button>
                          </div>
                        </div>

                        <Textarea
                          rows={2}
                          value={slot.systemPrompt}
                          placeholder="System prompt (optional) — You are a helpful assistant specializing in…"
                          className="resize-none text-xs"
                          onChange={(event) =>
                            setSlots((current) =>
                              current.map((item) =>
                                item.model.id === slot.model.id
                                  ? {
                                      ...item,
                                      systemPrompt: event.target.value,
                                    }
                                  : item,
                              ),
                            )
                          }
                        />

                        {strategy === "weighted_avg" && !isJudge && (
                          <div className="mt-3 flex items-center gap-3">
                            <span className="shrink-0 text-xs text-muted-foreground">
                              Weight
                            </span>
                            <Slider
                              min={0}
                              max={1}
                              step={0.05}
                              value={[slot.weight]}
                              className="flex-1"
                              onValueChange={([value]) =>
                                setSlots((current) =>
                                  current.map((item) =>
                                    item.model.id === slot.model.id
                                      ? {
                                          ...item,
                                          weight: value,
                                        }
                                      : item,
                                  ),
                                )
                              }
                            />
                            <span className="w-7 text-right font-mono text-xs text-muted-foreground">
                              {slot.weight.toFixed(2)}
                            </span>
                            <span className="w-12 text-right font-mono text-xs">
                              {weightSum
                                ? `${Math.round((slot.weight / weightSum) * 100)}%`
                                : "—"}
                            </span>
                          </div>
                        )}
                      </article>
                    );
                  })
                )}
              </div>

              <div className="my-4 flex items-center gap-2 text-muted-foreground/40">
                <div className="h-px flex-1 bg-border" />
                <ArrowDown className="size-3.5" />
                <div className="h-px flex-1 bg-border" />
              </div>

              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Scale className="size-3.5 text-muted-foreground" />
                  <span className="text-sm font-medium">Reduce</span>
                  <span className="text-xs text-muted-foreground">
                    · combines into one answer
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <StageSelect
                    value={customReduce ? "custom" : strategy}
                    options={[
                      ...strategies,
                      {
                        value: "custom",
                        label: "Custom script…",
                        description: "Plug in a reduce script",
                      },
                    ]}
                    onChange={(value) => {
                      if (value === "custom") {
                        setCustomReduce(true);
                        setJudgeId(null);
                      } else {
                        setCustomReduce(false);
                        setStrategy(value as ReduceStrategy);
                      }
                    }}
                  />
                  {customReduce && (
                    <span className="text-xs text-muted-foreground/70">
                      No reduce scripts — add one in Scripts
                    </span>
                  )}
                </div>
              </div>

              <section className="flex flex-col gap-3 rounded-xl border bg-card px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent/10">
                    <Scale className="size-4 text-accent" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-medium">
                      {customReduce ? "Choose a script" : selectedStrategy.label}
                    </h3>
                    <p className="truncate text-xs text-muted-foreground">
                      {customReduce
                        ? "Custom reduce script"
                        : selectedStrategy.description}
                    </p>
                  </div>
                </div>
                {!customReduce && (
                  <div className="flex items-center justify-between gap-2 border-t border-border/50 pt-3">
                    <span className="text-xs text-muted-foreground">
                      Judge model
                    </span>
                    {judge ? (
                      <span className="flex items-center gap-1 text-xs text-accent">
                        <Scale className="size-2.5" />
                        {judge.name}
                      </span>
                    ) : (
                      <span className="text-xs text-primary">
                        none — use “Make judge” on a loop model
                      </span>
                    )}
                  </div>
                )}
              </section>

              {slots.length > 0 && (
                <section className="mt-6 rounded-xl border border-border/60 bg-muted/20 p-4">
                  <p className="mb-2 text-xs text-muted-foreground">
                    url4 Recipe
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="min-w-0 flex-1 break-all font-mono text-xs text-primary/90">
                      {recipe}
                    </code>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={copyRecipe}
                      aria-label="Copy url4 recipe"
                      className="size-8 shrink-0 text-muted-foreground"
                    >
                      {copied ? (
                        <Check className="size-3.5 text-accent" />
                      ) : (
                        <Copy className="size-3.5" />
                      )}
                    </Button>
                  </div>
                </section>
              )}

              <div className="mt-8 flex justify-end">
                <Button
                  className="h-10 rounded-xl px-6"
                  onClick={() => setTab("runs")}
                >
                  Next: Run
                  <ArrowRight className="size-4" />
                </Button>
              </div>
            </div>
          </main>
      </TabsContent>
      <TabsContent
        value="runs"
        className="m-0 min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-8"
      >
          <div className="mx-auto max-w-2xl">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setTab("compose")}
              className="mb-6 -ml-3 text-muted-foreground"
            >
              <ChevronLeft className="size-3.5" />
              Compose
            </Button>
            <div className="rounded-xl border border-dashed px-6 py-20 text-center">
              <h2 className="text-sm font-medium">No runs yet.</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Configure at least one model, then start a new evaluation.
              </p>
              <Button className="mt-5" disabled={slots.length === 0}>
                New Run
              </Button>
            </div>
          </div>
      </TabsContent>
    </Tabs>
  );
}

export default function EnsembleComposerPage() {
  return (
    <Suspense>
      <EnsembleComposer />
    </Suspense>
  );
}
