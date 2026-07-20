"use client";

import { GitFork, Layers, Plug, Plus, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function EnsemblesPage() {
  const router = useRouter();
  const [importing, setImporting] = useState(false);
  const [importValue, setImportValue] = useState("");
  const [importError, setImportError] = useState("");

  function importRecipe() {
    const match = importValue.trim().match(/^url4:\/\/([^?]+)\?(.*)$/);
    if (!match) {
      setImportError(
        "Not a valid url4 — expected url4://name?models=…&reduce=…",
      );
      return;
    }

    const knownModelIds = new Set([
      "ol-1", "ol-2", "ol-3", "ol-4",
      "or-1", "or-2", "or-3", "or-4", "or-5", "or-6",
      "hf-1", "hf-2",
      "cs-1", "cs-2", "cs-3",
      "cx-1", "cx-2",
      "gs-1", "gs-2",
      "an-1", "an-2", "an-3",
      "oa-1", "oa-2", "oa-3", "oa-4",
      "dm-1", "dm-2", "dm-3",
      "px-1", "px-2", "px-3",
    ]);
    const params = new URLSearchParams(match[2]);
    const models = (params.get("models") ?? "").split(/[+\s]+/);

    if (!models.some((model) => knownModelIds.has(model))) {
      setImportError("No known models found in that url4.");
      return;
    }

    setImporting(false);
    setImportValue("");
    setImportError("");
    router.push(`/ensembles/new/?recipe=${encodeURIComponent(importValue.trim())}`);
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b px-5 py-5 sm:px-8">
        <div
          data-tauri-drag-region
          className="min-w-0 flex-1"
        >
          <h1 className="text-base font-semibold">Ensembles</h1>
          <p className="mt-1 text-xs text-muted-foreground">
            Your recipes. Open one to compose, run evals, and analyze results.
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="rounded-lg"
            onClick={() => {
              setImporting((current) => !current);
              setImportError("");
            }}
          >
            <GitFork className="size-3.5" />
            Import url4
          </Button>
          <Button
            size="sm"
            className="rounded-lg shadow-sm"
            disabled
          >
            <Plus className="size-4" />
            New Ensemble
          </Button>
        </div>
      </header>

      {importing && (
        <section className="shrink-0 border-b bg-muted/20 px-5 py-4 sm:px-8">
          <div className="w-full">
            <div className="mb-2 flex items-start justify-between gap-4">
              <p className="text-xs text-muted-foreground">
                Paste a url4 recipe to create an ensemble from it
              </p>
              <Button
                variant="ghost"
                size="icon"
                className="-my-2 size-8"
                aria-label="Close import"
                onClick={() => {
                  setImporting(false);
                  setImportError("");
                }}
              >
                <X className="size-3.5" />
              </Button>
            </div>

            <div className="flex max-w-2xl items-center gap-2">
              <Input
                autoFocus
                value={importValue}
                onChange={(event) => {
                  setImportValue(event.target.value);
                  setImportError("");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") importRecipe();
                }}
                placeholder="url4://my-recipe?models=an-1+dm-1&reduce=majority_vote"
                className="h-9 rounded-lg font-mono text-xs"
              />
              <Button size="sm" onClick={importRecipe}>
                Create
              </Button>
            </div>

            {importError && (
              <p className="mt-1.5 text-xs text-destructive">
                {importError}
              </p>
            )}
          </div>
        </section>
      )}

      <main className="min-h-0 flex-1 overflow-y-auto px-5 py-8 sm:px-8">
        <section className="flex flex-col items-center justify-center gap-4 py-24 text-center">
          <Layers className="size-7 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">
            Connect some models first to start building ensembles.
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
        </section>
      </main>
    </div>
  );
}
