"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Download,
  RefreshCw,
  TriangleAlert,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";

type UpdateWindowType =
  | "checking"
  | "none"
  | "available"
  | "downloading"
  | "error"
  | "failed";

type UpdateWindowState = {
  updateWindowType: UpdateWindowType;
  version: string;
  currentVersion: string;
  releaseNotes: string;
  error: string;
  progress: number;
};

type TauriWindow = {
  close?: () => Promise<void>;
};

type TauriWebviewWindow = {
  listen?: <T>(event: string, handler: (event: { payload: T }) => void) => Promise<() => void>;
};

type TauriGlobal = {
  core?: {
    invoke?: <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
  };
  window?: { getCurrentWindow?: () => TauriWindow };
  webviewWindow?: { getCurrentWebviewWindow?: () => TauriWebviewWindow };
};

const initialState: UpdateWindowState = {
  updateWindowType: "checking",
  version: "",
  currentVersion: "",
  releaseNotes: "",
  error: "",
  progress: 0,
};

function getTauri() {
  return (window as Window & { __TAURI__?: TauriGlobal }).__TAURI__;
}

export default function UpdatesPage() {
  const [state, setState] = useState(initialState);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    const tauri = getTauri();

    const connect = async () => {
      const nextState = await tauri?.core?.invoke?.<UpdateWindowState>(
        "get_update_window_state",
      );
      if (nextState) setState(nextState);

      const currentWindow = tauri?.webviewWindow?.getCurrentWebviewWindow?.();
      unlisten = await currentWindow?.listen?.<UpdateWindowState>(
        "update-window-state",
        (event) => setState(event.payload),
      );
    };

    void connect();
    return () => unlisten?.();
  }, []);

  const close = () => {
    void getTauri()?.window?.getCurrentWindow?.().close?.();
  };

  const later = () => {
    void getTauri()?.core?.invoke?.("update_window_response", {
      installUpdate: false,
    });
    close();
  };

  const update = () => {
    setState((current) => ({ ...current, updateWindowType: "downloading", progress: 0 }));
    void getTauri()?.core?.invoke?.("update_window_response", {
      installUpdate: true,
    });
  };

  const status = {
    checking: {
      icon: <RefreshCw className="size-5 animate-spin text-primary" />,
      title: "Checking for updates",
      description: "Looking for the latest version of ScreamingFace.",
    },
    none: {
      icon: <CheckCircle2 className="size-5 text-emerald-600 dark:text-emerald-400" />,
      title: "You’re up to date",
      description: `ScreamingFace ${state.currentVersion} is the latest version.`,
    },
    available: {
      icon: <Download className="size-5 text-primary" />,
      title: "Update available",
      description: `ScreamingFace ${state.version} is ready to install.`,
    },
    downloading: {
      icon: <Download className="size-5 text-primary" />,
      title: "Downloading update",
      description: `ScreamingFace ${state.version} is downloading.`,
    },
    error: {
      icon: <TriangleAlert className="size-5 text-destructive" />,
      title: "Update check failed",
      description: "We couldn’t check for updates.",
    },
    failed: {
      icon: <TriangleAlert className="size-5 text-destructive" />,
      title: "Update failed",
      description: "We couldn’t install the update.",
    },
  }[state.updateWindowType];

  return (
    <main className="flex h-svh select-none overflow-hidden bg-background text-foreground">
      <aside className="relative flex w-2/5 flex-col overflow-hidden bg-sidebar p-8 text-sidebar-foreground">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,var(--primary),transparent_60%)] opacity-15" />
        <div data-tauri-drag-region className="absolute inset-0" />
        <div className="relative z-10 flex items-center gap-3">
          <span className="grid size-12 place-items-center rounded-2xl bg-primary/15 text-2xl ring-1 ring-primary/20">
            😱
          </span>
          <div>
            <p className="text-xl font-semibold">ScreamingFace</p>
            <p className="text-xs text-muted-foreground">the loudest ensemble hub</p>
          </div>
        </div>

        <div className="relative z-10 mt-auto flex items-center text-xs text-muted-foreground">
          <div>
            <span className="block">Current version</span>
            <strong className="font-mono text-sm text-foreground">{state.currentVersion || "—"}</strong>
          </div>
          {state.updateWindowType === "available" && (
            <>
              <ArrowRight className="mx-4 size-4" />
              <div>
                <span className="block">New version</span>
                <strong className="font-mono text-sm text-foreground">{state.version}</strong>
              </div>
            </>
          )}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col bg-card">
        <header className="relative flex items-center gap-3 border-b px-6 py-5">
          <div data-tauri-drag-region className="absolute inset-0" />
          <span className="relative z-10 grid size-10 place-items-center rounded-xl bg-muted">
            {status.icon}
          </span>
          <div className="relative z-10 min-w-0">
            <h1 className="text-lg font-semibold">{status.title}</h1>
            <p className="truncate text-sm text-muted-foreground">{status.description}</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="relative z-10 ml-auto size-8"
            aria-label="Close updates"
            onClick={close}
            disabled={state.updateWindowType === "downloading"}
          >
            <X className="size-4" />
          </Button>
        </header>

        <div className="flex min-h-0 flex-1 flex-col justify-center overflow-y-auto p-6">
          {state.updateWindowType === "available" && (
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                What’s new
              </p>
              <div className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl border bg-muted/30 p-4 text-sm leading-relaxed">
                {state.releaseNotes}
              </div>
            </div>
          )}

          {(state.updateWindowType === "checking" || state.updateWindowType === "none") && (
            <div className="mx-auto max-w-sm text-center">
              <span className="mx-auto grid size-20 place-items-center rounded-full bg-primary/10">
                {state.updateWindowType === "checking" ? (
                  <RefreshCw className="size-9 animate-spin text-primary" />
                ) : (
                  <CheckCircle2 className="size-9 text-emerald-600 dark:text-emerald-400" />
                )}
              </span>
              <p className="mt-5 text-sm text-muted-foreground">{status.description}</p>
            </div>
          )}

          {state.updateWindowType === "downloading" && (
            <div className="mx-auto w-full max-w-sm text-center">
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-[width] duration-300"
                  style={{ width: `${state.progress}%` }}
                />
              </div>
              <p className="mt-4 font-mono text-sm text-muted-foreground">{state.progress}%</p>
            </div>
          )}

          {(state.updateWindowType === "error" || state.updateWindowType === "failed") && (
            <div className="whitespace-pre-wrap rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              {state.error}
            </div>
          )}
        </div>

        <footer data-tauri-drag-region className="flex justify-end gap-3 border-t px-6 py-4">
          {state.updateWindowType === "available" && (
            <>
              <Button variant="outline" onClick={later}>Remind me later</Button>
              <Button onClick={update}>Update now</Button>
            </>
          )}
          {(["none", "error", "failed"] as UpdateWindowType[]).includes(state.updateWindowType) && (
            <Button onClick={close}>Close</Button>
          )}
          {state.updateWindowType === "checking" && <Button disabled>Checking…</Button>}
          {state.updateWindowType === "downloading" && <Button disabled>Downloading…</Button>}
        </footer>
      </section>
    </main>
  );
}
