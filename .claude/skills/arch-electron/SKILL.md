---
name: arch-electron
description: >-
  Use when DESIGNING or REVIEWING the architecture of any ScreamingFace Electron app —
  new app scaffold, extension/plugin platform work, integrating external processes
  (server CLI, tools), IPC surface design, extension API changes, diagnostics/logging
  surfaces. Binding invariants (VS Code model): manifest-first contribution points, lazy
  activation, one utilityProcess extension host, narrow versioned injected API, disposable
  registrations, core-owned ProcessSupervisor, DEBUG-gated process-log view. Design-time
  companion to sdlc-electron (which owns the per-iteration loop + security checklist).
---

# Electron Architecture Doctrine

**Announce at start:** "Using the arch-electron skill — binding architecture doctrine for
Electron apps."

This is a **RIGID** doctrine skill: the rules below are MUST-level invariants for every
ScreamingFace Electron app, each with its rationale. It binds at **design time** — new app,
new subsystem, extension API change, external-process integration, architecture review.
Per-iteration build work runs under `sdlc-electron` (rigid TDD loop + the official Electron
**security checklist** — not duplicated here); the concrete extension-API surface is owned
by a dedicated API-surface skill (separate deliverable) — this skill covers application-level
architecture only. Deviating from an invariant is a Confidence-Gate decision: STOP and ask
the owner.

This doctrine is the CLAUDE.md hexagonal mandate pushed across process boundaries: core
defines ports, extensions/adapters implement them, wiring goes through registries — and the
port between core and extensions is a *process* boundary crossed by RPC.

## Process topology (T)

```
+----------------------------------------------------------------------------+
| MAIN (the only privileged process)                                         |
|   window/session security · IPC hub · contribution registries              |
|   extension manager (manifests, install, host lifecycle)                   |
|   ProcessSupervisor (spawn/kill/restart, ring buffers)                     |
+----------------------------------------------------------------------------+
   | typed contextBridge IPC | RPC over MessagePort  | spawn + signals
+------------------------+ +-------------------------+ +---------------------+
| RENDERER               | | EXTENSION HOST          | | SUPERVISED          |
|  sandboxed UI          | |  one utilityProcess     | | CHILDREN            |
|  registry-driven       | |  injected `api` mod     | |  server CLI, tools  |
|  webviews for ext UI   | |  activate()/dispose()   | |  stdio->ring buffer |
+------------------------+ +-------------------------+ +---------------------+
```

Rendered diagrams (SVG + PNG): `docs/diagrams/electron-extension-architecture.*`
(this topology) and `docs/diagrams/electron-extension-load-sequence.*` (lifecycle:
scan → merge → render → event → load → activate; disable/uninstall/safe-mode paths).

- **T1 — Four process classes, fixed responsibilities.** MAIN is the only privileged
  process (windows, IPC hub, spawning, external I/O). RENDERER is a sandboxed projection of
  observable state — no Node, no network, no spawning. EXTENSION HOST is one Node
  `utilityProcess` for all extensions. SUPERVISED CHILDREN are external binaries under the
  ProcessSupervisor. *Privilege lives in exactly one place; everything else is contained.*
- **T2 — The renderer talks only through the typed contextBridge surface.** No dev-only
  backdoors. IPC contract discipline (typed payloads, both-side tests, sender validation)
  is enforced per `sdlc-electron` rule S2 + its security checklist.
- **T3 — Every privileged capability is a main-process port.** Filesystem outside app
  storage, network, process spawning, shell/OS integration: main-process services behind
  typed interfaces. *Generalizes the standing external-HTTP-in-main rule.*

## Extension platform (X) — the VS Code model

- **X1 — Manifest-first contribution points.** An extension declares WHAT it contributes
  (commands, menus, views, settings schema) as data in its manifest; core renders UI from
  these declarations **without loading extension code**. `activate()` binds behavior, never
  UI presence. *Install/enable changes the app instantly because only JSON was parsed.*
- **X2 — Lazy activation.** Extension code loads only when a declared activation event
  fires (`onCommand:*`, `onView:*`, `onStartupFinished`). Startup time MUST NOT scale with
  the number of installed extensions.
- **X3 — One process-isolated extension host.** All extension code runs in a single
  `utilityProcess.fork()` Node runtime — never in main, never in a renderer. *Crash
  containment, killability, and the renderer keeps its sandbox.*
- **X4 — Narrow, versioned, injected API.** Extensions import exactly one app API module,
  which does not exist on disk — the host injects it (module-resolution interception) as a
  facade of RPC proxies. The manifest's `engines` semver range gates loading. The API is
  additive-only once published. *The injected API surface is a public contract forever —
  keep it an order of magnitude smaller than you're tempted to.*
  **Scope boundary:** this skill binds only the MECHANISM (existence, injection, engines
  gating, additive-only evolution). The concrete API surface — namespaces, capabilities,
  types — is owned by a dedicated API-surface skill (separate deliverable); do not grow
  API design into this skill.
- **X5 — Every registration returns a Disposable.** Commands, providers, listeners, UI
  items — all collected into the extension's subscription bag; deactivate = dispose the
  bag. *This is the mechanism that makes runtime enable/disable real.*
- **X6 — Extensions never touch the app DOM.** Extension UI is declarative
  (registry-rendered by core) or a sandboxed webview with its own message channel.
- **X7 — Unload = refork the host.** Node cannot safely evict loaded modules; uninstall or
  update of already-loaded code restarts the extension host process (the window survives,
  other extensions re-activate). Never fake unload by purging module caches.
- **X8 — Safe mode exists.** A startup flag/gesture launches with all extensions disabled.
  *The recovery path when an extension breaks startup.*
- **X9 — Isolation is escalatable, not improvised.** Default: signed/reviewed extensions in
  the shared host (full Node power — extensions are trusted-ish). Genuinely untrusted
  marketplace code requires an interpreter sandbox (QuickJS-in-WASM / isolated-vm) with a
  capability-based API — that is a separate owner-level design decision, never a patch.

## Core vs extension — the boundary litmus (B)

- **B1 — Needed to diagnose or recover a broken extension system → core.** Process
  supervision, the process-log view, the extension-manager UI, safe mode.
- **B2 — Needed by both core features and extensions → core, behind a port.**
- **B3 — Needs privilege (spawn, fs, network) → core-mediated:** extensions reach it only
  through the injected API against manifest-declared capability grants.

## Process supervision (P)

- **P1 — The ProcessSupervisor is core (main process), never an extension.** B1+B2+B3 all
  apply: launching the server CLI is a first-party concern; orphan cleanup must survive any
  extension being disabled; spawning is the most privileged capability in the app.
- **P2 — Every child process is registered:** id, command, cwd, env, restart policy, health
  probe. No ad-hoc `spawn()` anywhere else in the codebase.
- **P3 — No orphans.** The supervisor guarantees children die with the app: graceful
  SIGTERM → bounded wait → SIGKILL on quit, plus best-effort cleanup of stale children on
  next start (crash recovery).
- **P4 — Restart policies are declared and bounded** (max retries + backoff). Unbounded
  auto-restart is a crash loop, not resilience.
- **P5 — Extensions spawn only via the supervisor API** with a manifest-declared process
  grant (which binaries, surfaced to the user at install). Direct `child_process` access
  from extension code is a defect.
- **P6 — stdout/stderr of every child feeds a bounded in-memory ring buffer** per process,
  structured entries `{ts, pid, stream, line}`.

## Diagnostics (D)

- **D1 — A core process-log view exists**: one lane per process — main, each renderer, the
  extension host, every supervised child. Core, not an extension (B1): it must work
  precisely when the extension system is broken.
- **D2 — DEBUG-gated registration.** The view and its streaming IPC channel register only
  when DEBUG mode is on. DEBUG is a **runtime toggle** (env var + in-app developer
  setting), not a build variant — support flipping it on in the field.
- **D3 — Buffers always on; rendering on demand.** Ring buffers collect regardless of DEBUG
  (bounded memory), so enabling DEBUG right after an incident still shows recent history.
  Lines stream to the renderer only while the view is open (subscribe/unsubscribe, batched
  with backpressure — never unconditional push).
- **D4 — Memory-only by default.** Child output may contain secrets: no disk persistence of
  process logs except an explicit user export, with a redaction hook before display/export.

## State & persistence (S)

- **S1 — Core owns storage locations.** Everything lives under `app.getPath('userData')`;
  extensions get scoped key-value state (global/workspace-style) via the injected API —
  never raw filesystem paths.
- **S2 — Secrets go through main-process `safeStorage`** (or the app's designated secret
  store) — never plaintext in extension state, renderer storage, or logs. *Same posture as
  the AIGateway SecretStoreMixin rule.*

## Red flags — STOP immediately

| Thought | Action |
|---|---|
| "Load the plugin in-process, it's simpler." | STOP (X3). Extension host only. |
| "Register this menu item from activate()." | STOP (X1). UI presence is manifest-declared. |
| "The extension can spawn the tool itself." | STOP (P5). Supervisor + manifest grant. |
| "Purge the require cache to unload." | STOP (X7). Refork the host. |
| "Expose this internal service object to extensions directly." | STOP (X4). Versioned injected API only. |
| "Make the log view an extension — nice dogfooding." | STOP (B1/D1). Diagnostics are core. |
| "Persist child logs to a file, easier to debug." | STOP (D4). Ring buffer; explicit export only. |
| "Auto-restart the CLI forever until it comes up." | STOP (P4). Bounded retries + backoff. |
| "We'll version the extension API later." | STOP (X4). `engines` gating from the first release. |
