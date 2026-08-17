---
ticket: OME-846
stack: repo
status: in_progress
started: 2026-08-17
finished:
---

# OME-846 — Copyedit and expand the sf-client public docs

## Intent

A live copyedit/polish pass over the public-docs sf-client surface, driven interactively by
the owner. It began as verbatim prose copyedits on the Overview and Home hero and grew, in the
same session, into a broader docs-accuracy pass: correcting the hosted engine URL, reframing
the Configure-engine and web-search guidance, documenting a leaderboard default and a model
parameter-discovery API, adding "work in progress" caveats where scope is currently limited,
and adding explanatory diagrams. Copy/diagrams and one URL constant only — no client behaviour
changes.

## Planned changes (as executed)

- `public-docs/src/lib/engine.ts` — hosted `SF_ENGINE_URL` → `https://fusion.dev.screamingface.ai`
  (was the `engine.screamingface.ai` placeholder).
- `public-docs/src/pages/HomePage.vue` — hero: "a real research benchmark" → "a real benchmark".
- `public-docs/src/pages/sf-client/Index.vue` — 7 prose edits (engine/caching sentence, "reported
  repeatedly", drop two sentences/para, url4 grammar+protocol, "either of two", "pay for the
  compute"); add the theme-aware **local-flow diagram** (reusing
  `/diagrams/screamingface-request-architecture-local-*.svg`) to the "How it works" section.
- `public-docs/src/pages/sf-client/QuickstartPage.vue` — description reword; DRACO → arXiv link
  (2602.11685); "1 · Point at an engine" → "1 · Configure the engine" led by what the engine
  does, linked to `/learn/engine`; local-vs-hosted engine guidance incl. peer-to-peer hosted
  access; provider/caching caveat (caching = OpenRouter + Anthropic only, WIP).
- `public-docs/src/pages/sf-client/InstallationPage.vue` — reframe "Give the engine a web-search
  key" around Hugging Face / non-search providers (most of the time not needed); add a note that
  the client defaults to the hosted leaderboard (`leaderboard.dev.screamingface.ai`) and is
  overridden via `sf.configure(scoreboard_url=...)`.
- `public-docs/src/pages/sf-client/guides/ConnectionsPage.vue` — drop "Your notebook keeps no copy."
- `public-docs/src/pages/sf-client/guides/BenchmarksPage.vue` — caveat: only a subset of benchmarks
  is live, expanding, + feedback CTA to GitHub.
- `public-docs/src/pages/sf-client/guides/ModelsPage.vue` — caveat: no automatic model discovery yet
  (fixed catalogue, WIP); new section "6 · Discover a route's parameters" using
  `sf.models.get(...).parameters` / `ModelParameter.schema`.
- `public-docs/src/pages/sf-client/guides/PipelinesPage.vue` — one inline-SVG diagram per code
  snippet (chain, `.then()`, flatten, named-nest, recursive Fusion), matching the page's existing
  hand-authored SVG convention, to make the nesting legible.

## Test plan

- Docs-only. Gate = the `public-docs-tests.yml` CI equivalents run locally.

## Acceptance

- All owner-dictated edits applied; new content technically accurate against the shipped
  `packages/screamingface` API (`configure(scoreboard_url=...)`, `discovery.ModelParameter`).
- CI-equivalent gates green.

## Outcome

- **Actual files:** 9 source files under `public-docs/src` (listed above) + this ledger + the
  `docs/tasks` mirror.
- **Commits:** <filled at commit>
- **Gates:** `vue-tsc --noEmit` ✓ · `vite build` ✓ (built in ~0.9s) · `oxlint .` ✓ (exit 0) ·
  `eslint .` ✓ (exit 0). No Prettier gate in `public-docs-tests.yml`.
- **Deviations:** Scope grew well beyond the original title (Overview/Home) during live iteration
  into a full sf-client docs pass — kept under one ticket per the owner's fold-tweaks-into-the-
  active-ticket preference; Linear title/description updated to match. SVG diagram *visual*
  correctness was not machine-verifiable (build only checks well-formedness) — owner to eyeball in
  `npm run dev`.
