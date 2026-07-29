"use client";

import {
  Boxes,
  Check,
  Cpu,
  Globe,
  Key,
  Plug,
  Plus,
  Search,
  Terminal,
  X,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  PROVIDER_COLORS,
  useModelStore,
  type ModelProvider,
} from "@/lib/model-store";
import { cn } from "@/lib/utils";

const groupOrder: ModelProvider["group"][] = [
  "Local & Sessions",
  "Providers",
  "Hubs",
];

function ProviderIcon({
  provider,
  className,
}: {
  provider: ModelProvider;
  className?: string;
}) {
  const Icon =
    provider.kind === "session"
      ? Terminal
      : provider.kind === "local"
        ? Cpu
        : Globe;
  const color = PROVIDER_COLORS[provider.id] ?? "var(--primary)";

  return (
    <span
      className={cn(
        "grid size-8 shrink-0 place-items-center rounded-lg",
        className,
      )}
      style={{ background: `color-mix(in srgb, ${color} 10%, transparent)` }}
    >
      <Icon className="size-4" style={{ color }} />
    </span>
  );
}

function ProviderRow({
  provider,
  active,
  onSelect,
}: {
  provider: ModelProvider;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
        active
          ? "border-primary/50 bg-primary/5 shadow-sm ring-1 ring-primary/15"
          : "border-transparent hover:bg-secondary/40",
      )}
      onClick={onSelect}
    >
      <ProviderIcon provider={provider} className="size-7" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">
          {provider.name}
        </span>
        <span className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
          {provider.connected ? (
            <>
              <span className="size-1.5 rounded-full bg-accent" />
              <span className="text-accent">
                {provider.models.length} models
              </span>
            </>
          ) : (
            "Not connected"
          )}
        </span>
      </span>
    </button>
  );
}

function ProviderConnect({ provider }: { provider: ModelProvider }) {
  const patchProvider = useModelStore((state) => state.patchProvider);
  const discoverProvider = useModelStore((state) => state.discoverProvider);
  const keyless = provider.kind === "local" || provider.kind === "session";

  return (
    <div className="flex max-w-md flex-col gap-3 rounded-xl border bg-card p-4">
      {keyless ? (
        <p className="text-xs text-muted-foreground">
          {provider.kind === "session"
            ? `Uses your authenticated ${provider.name} — no API key required.`
            : "Ollama must be running locally. No API key required."}
        </p>
      ) : (
        <>
          <div>
            <label
              htmlFor={`${provider.id}-api-key`}
              className="mb-1.5 block text-xs text-muted-foreground"
            >
              API Key
            </label>
            <div className="relative">
              <Key className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                id={`${provider.id}-api-key`}
                type="password"
                placeholder="sk-…"
                value={provider.apiKey}
                className="h-9 pl-9 text-xs"
                onChange={(event) =>
                  patchProvider(provider.id, { apiKey: event.target.value })
                }
              />
            </div>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
            <Switch
              checked={provider.useOM}
              onCheckedChange={(checked) =>
                patchProvider(provider.id, { useOM: checked })
              }
            />
            Use OpenMined key (subsidized)
          </label>
        </>
      )}

      <Button
        size="sm"
        className="rounded-lg self-start"
        disabled={provider.discovering}
        onClick={() => discoverProvider(provider.id)}
      >
        {provider.discovering ? (
          <>
            <span className="size-3 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground" />
            {provider.kind === "session" ? "Connecting…" : "Discovering…"}
          </>
        ) : (
          <>
            <Search className="size-3.5" />
            {keyless ? "Connect & Discover" : "Discover Models"}
          </>
        )}
      </Button>
    </div>
  );
}

export default function ModelsPage() {
  const providers = useModelStore((state) => state.providers);
  const library = useModelStore((state) => state.library);
  const toggleLibraryModel = useModelStore(
    (state) => state.toggleLibraryModel,
  );
  const [selectedId, setSelectedId] = useState<string | null>(
    providers.find((provider) => provider.connected)?.id ?? null,
  );
  const [search, setSearch] = useState("");

  const active =
    providers.find((provider) => provider.id === selectedId) ?? null;
  const filteredModels = useMemo(
    () =>
      active?.models.filter((model) =>
        model.name.toLowerCase().includes(search.toLowerCase()),
      ) ?? [],
    [active, search],
  );
  const recipe = `url4://ensemble-${library.length}?models=${library.map((model) => model.id).join("+")}&reduce=majority_vote&loop=parallel`;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      <header className="shrink-0 border-b px-5 py-5 sm:px-8">
        <h1 className="text-base font-semibold">Models</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Connect providers once, then build a reusable library of models for
          your ensembles.
        </p>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="flex w-64 shrink-0 flex-col gap-5 overflow-y-auto border-r px-4 py-6">
          {groupOrder.map((group) => (
            <section key={group} className="flex flex-col gap-1">
              <h2 className="px-1 pb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {group}
              </h2>
              {providers
                .filter((provider) => provider.group === group)
                .map((provider) => (
                  <ProviderRow
                    key={provider.id}
                    provider={provider}
                    active={provider.id === selectedId}
                    onSelect={() =>
                      setSelectedId((current) =>
                        current === provider.id ? null : provider.id,
                      )
                    }
                  />
                ))}
            </section>
          ))}
        </aside>

        <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
          <div className="flex flex-wrap items-center gap-2 border-b px-6 py-4">
            {library.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No models added yet — pick some below.
              </p>
            ) : (
              <>
                {library.map((model) => (
                  <span
                    key={model.id}
                    className="inline-flex items-center gap-1.5 rounded-lg border bg-card py-1 pl-2 pr-1 text-xs"
                  >
                    <span
                      className="size-2 shrink-0 rounded-full"
                      style={{
                        background:
                          PROVIDER_COLORS[model.providerId] ??
                          "var(--primary)",
                      }}
                    />
                    <span className="max-w-56 truncate font-mono">
                      {model.name}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-5 shrink-0 text-muted-foreground"
                      aria-label={`Remove ${model.name}`}
                      onClick={() => toggleLibraryModel(model)}
                    >
                      <X className="size-3" />
                    </Button>
                  </span>
                ))}
                <Button className="ml-auto rounded-lg" size="sm" asChild>
                  <Link
                    href={`/ensembles/new/?recipe=${encodeURIComponent(recipe)}`}
                    prefetch={false}
                  >
                    <Boxes className="size-3.5" />
                    Build an Ensemble
                  </Link>
                </Button>
              </>
            )}
          </div>

          <div className="min-h-0 flex-1 px-6 py-6">
            {!active ? (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-muted-foreground">
                <Plug className="size-7 opacity-20" />
                <p className="text-sm opacity-50">
                  Select a provider on the left.
                </p>
              </div>
            ) : !active.connected ? (
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-3">
                  <ProviderIcon provider={active} />
                  <div>
                    <h2 className="text-sm font-medium">{active.name}</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {active.description}
                    </p>
                  </div>
                </div>
                <ProviderConnect provider={active} />
              </div>
            ) : (
              <>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <ProviderIcon provider={active} />
                    <div>
                      <h2 className="text-sm font-medium">
                        {active.name} Models
                      </h2>
                      <p className="mt-0.5 flex items-center gap-1 text-xs text-accent">
                        <span className="size-1.5 rounded-full bg-accent" />
                        {
                          library.filter(
                            (model) => model.providerId === active.id,
                          ).length
                        }{" "}
                        in your library
                      </p>
                    </div>
                  </div>
                  <div className="relative w-44">
                    <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={search}
                      placeholder="Search…"
                      className="h-9 pl-9 text-xs"
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </div>
                </div>

                {filteredModels.length === 0 ? (
                  <p className="py-8 text-center text-xs text-muted-foreground/60">
                    No models match these filters.
                  </p>
                ) : (
                  <div className="grid gap-3 xl:grid-cols-2">
                    {filteredModels.map((model) => {
                      const selected = library.some(
                        (item) => item.id === model.id,
                      );
                      return (
                        <button
                          type="button"
                          key={model.id}
                          aria-pressed={selected}
                          className={cn(
                            "flex w-full items-center justify-between rounded-xl border bg-card px-4 py-3.5 text-left transition-colors",
                            selected
                              ? "border-primary/50 bg-primary/5"
                              : "hover:border-foreground/20",
                          )}
                          onClick={() => toggleLibraryModel(model)}
                        >
                          <span className="flex min-w-0 items-center gap-3">
                            <span
                              className="size-2 shrink-0 rounded-full"
                              style={{
                                background:
                                  PROVIDER_COLORS[model.providerId] ??
                                  "var(--primary)",
                              }}
                            />
                            <span className="truncate text-sm">
                              {model.name}{" "}
                              <span className="font-mono text-xs text-muted-foreground">
                                [{model.providerName}]
                              </span>
                            </span>
                          </span>
                          {selected ? (
                            <Check className="size-4 shrink-0 text-primary" />
                          ) : (
                            <Plus className="size-4 shrink-0 text-muted-foreground" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
