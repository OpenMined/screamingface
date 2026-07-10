---
name: arch-electron-layout
description: >-
  Use when DESIGNING or REVIEWING the workbench/UI layout of a ScreamingFace Electron
  app — shell regions, view containers and slots, where an extension view may land,
  layout persistence, focus/reveal behavior, status-bar contributions, DEBUG view
  placement. Binding invariants: core-owned shell (title/activity bar, sidebar, main
  area, panel, status bar), views-in-containers, manifest placement is a hint, user
  override wins and persists, no focus stealing, per-window layout trees. Structural
  layer between arch-electron (platform doctrine) and screamingface-design (visual
  brand law).
---

# Workbench Layout Doctrine — Electron

**Announce at start:** "Using the arch-electron-layout skill — binding workbench layout
doctrine."

This is a **RIGID** doctrine skill, the structural layer between two neighbors it never
duplicates: `arch-electron` owns the platform (processes, extension mechanics — T/X/B/P/D/S
rules referenced below), `screamingface-design` owns every visual/brand decision inside the
structure. Build-time work runs under `sdlc-electron` (its a11y gate S1 consumes L11).
Deviating from an invariant is a Confidence-Gate decision: STOP and ask the owner.

## The shell — initial layout (v1)

The v1 default is based on the **Ensemble Studio** design
(https://irinambejan.github.io/model-ensemble-studio/, researched 2026-07-09; screenshots
in `.docs/ensemble-studio-research/`):

```
+----------------------------------------------------------------------------+
| TITLE BAR (native chrome / minimal custom)                                 |
+------------------+---------------------------------------------------------+
| PRIMARY SIDEBAR  | MAIN AREA — one view at a time:                         |
|  brand + theme   |  hub · list+detail · document · table · cards           |
|  nav: Ensembles  |                                                         |
|   Models         |  document view: header (name · meta · Share url4)       |
|   Leaderboard    |                 + document tabs (Compose | Runs)        |
|   Scripts [2]    +---------------------------------------------------------+
|  MY ENSEMBLES    | PANEL — hidden; DEBUG log lanes when DEBUG=on (L10)     |
|  compute card    +---------------------------------------------------------+
|  user footer     | STATUS BAR — reserved, hidden in v1 (L9)                |
+------------------+---------------------------------------------------------+
```

Rendered diagram (SVG + PNG): `docs/diagrams/electron-workbench-layout.*`.

**Initial-layout facts (from the Studio design):**

- **One rich sidebar, no activity bar in v1.** The sidebar carries: brand header + theme
  toggle · primary nav (Ensembles, Models, Leaderboard, Scripts — with count badges) ·
  a **MY ENSEMBLES** section listing the user's ensemble documents · the subsidized-compute
  program card (key connect) · the user identity footer. If view containers multiply beyond
  what one sidebar holds, adding an activity bar is the escalation path — an owner decision,
  not an extension's.
- **The main area shows one view at a time**, navigated from the sidebar. Five view
  archetypes: **hub** (hero + top ensembles), **list+detail** (Models: provider library
  column + detail pane), **document** (ensemble: breadcrumb, header with name/meta/auto-save/
  Share-url4, internal tab strip **Compose | Runs**; Compose = library pane + pipeline
  canvas Loop→Reduce; Runs = new-run wizard + history), **table page** (Leaderboard:
  benchmark tabs + scope filter + table), **card list** (Scripts: grouped cards with inline
  code).
- **The ensemble document is the app's document type** (L7): one open at a time in v1,
  reachable via MY ENSEMBLES; each document owns its internal tab strip. A multi-document
  tab strip in the main area is a future escalation, not v1.
- **Panel and status bar exist in the layout model but are hidden in v1**: the panel
  appears only as the DEBUG log-view home (L10, D2-gated); the status bar is reserved
  (L9 binds whenever it ships). The Studio design has neither — don't add visible chrome
  the design doesn't call for.
- Visual styling (colors, type, density, dark mode) is `screamingface-design` territory —
  this section binds structure only.

## Invariants (L)

- **L1 — The shell is core-owned.** Exactly these regions: title bar, primary sidebar,
  main area, panel, status bar (activity bar: deferred — absent in v1, see initial layout).
  Extensions never add top-level regions, floating/always-on-top surfaces, or windows.
  *One coherent layout model; window creation is a privileged capability (arch-electron
  T3).*
- **L2 — Views live in view containers; containers dock into slots.** A contributed view
  belongs to a view container (its own or a shared one); containers dock into the sidebar
  or panel. Both are declared in the manifest (arch-electron X1) — rendered with zero
  extension code.
- **L3 — Manifest placement is a HINT.** It positions a view the first time only.
- **L4 — User override wins and persists.** Users may move, hide, resize, and reorder any
  view or container; the override outlives restarts, updates, and re-installs, and always
  beats the manifest hint. Extensions cannot force placement. *The user owns the
  workbench; extensions are guests.*
- **L5 — No focus stealing.** An extension may reveal/focus its view only in response to a
  direct user action routed through the API mechanism (arch-electron X4). Unsolicited
  focus, auto-expansion, or attention-grabbing re-docking is a defect, not a feature.
- **L6 — Layout state is a core-owned tree.** Visibility, order, sizes, and dock positions
  persist per window in core storage (arch-electron S1). Extensions never read or write
  layout state directly — reveal/focus of their OWN views via the API is the whole surface.
- **L7 — The main area is document-centric.** It hosts primary work surfaces — in v1 the
  **ensemble document** (one at a time, with its internal Compose | Runs tab strip); tool/
  auxiliary views belong to the sidebar or panel. An extension reaches the main area only
  by contributing a document/editor type — never by docking a tool view there.
- **L8 — One layout tree per window.** Multi-window means independent trees; **no
  cross-window docking in v1** (YAGNI). Revisiting this is an owner decision.
- **L9 — Status-bar contributions are bounded.** Priority-ordered items with core-imposed
  truncation; no arbitrary widths, no interactive complexity beyond click/menu.
- **L10 — The DEBUG process-log view lands in the panel** as one lane per process, under
  arch-electron D1–D3 gating (registered only when DEBUG is on).
- **L11 — Regions are a11y landmarks.** Each shell region is a labeled landmark; keyboard
  traversal across regions (and into extension view content) is core-owned and always
  available. Feeds the sdlc-electron S1 a11y gate — landmark/keyboard assertions land with
  shell changes.
- **L12 — Chrome is core-rendered.** View headers, collapse/expand, drag handles, tab
  strips, badges: core. Extension content exists only INSIDE the view frame (declarative
  components or a webview — arch-electron X6). *A webview reimplementing dock/drag is a
  hard red flag.*

## Red flags — STOP immediately

| Thought | Action |
|---|---|
| "This extension needs a floating always-on-top window." | STOP (L1). Panel/sidebar view, or an owner decision. |
| "Force the view visible/expanded on activation." | STOP (L5). Reveal only on direct user action. |
| "Persist my view's position in extension storage." | STOP (L6). Layout state is core-owned. |
| "Dock this tool UI as a main-area tab." | STOP (L7). Contribute a document type or use sidebar/panel. |
| "Reset layout on update so users see the new default." | STOP (L4). User override survives updates. |
| "Custom drag/dock UX inside the webview." | STOP (L12). Chrome is core-rendered. |
| "Skip landmarks, it's just an internal tool view." | STOP (L11). a11y is a gate (S1). |
