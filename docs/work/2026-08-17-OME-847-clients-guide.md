---
ticket: OME-847
stack: repo
status: in_progress
started: 2026-08-17
finished:
---

# OME-847 — Add a "Clients vs sf.* shortcuts" user guide to the docs site

## Intent

The ScreamingFace Client SDK can be driven two ways: module-level shortcuts
(`import screamingface as sf` → `sf.evaluate(...)`, `sf.connect(...)`, `sf.configure(...)`,
`sf.close()`) that delegate to a single lazy, process-wide default `Client`, or an explicit
`Client` / `AsyncClient` the caller constructs and owns. The `public-docs` site already
documents the *types* (API Reference › Clients) but never explains *when to use which*.
Every other guide mixes both styles without ever drawing the distinction. This unit adds a
comprehensive User Guide, placed first under _User Guides_, that makes the difference clear —
config source, lifecycle, async (no module-level async — event-loop footgun), custom
transports, thread model, and multiple engines.

## Planned changes

Follows the docs site's standard "add a page" pattern (create page → route → nav entry):

- `public-docs/src/pages/sf-client/guides/ClientsPage.vue` (new) — the guide, built on
  `DocLayout` + `CodeBlock`/`NbCell`/`NbTextOut`/`Note`, mirroring `guides/ConnectionsPage.vue`
  and `api/ClientsPage.vue`.
- `public-docs/src/router/index.ts` — route `/sf-client/guides/clients`
  (name `sf-client-guides-clients`), before the `connections` route.
- `public-docs/src/navigation/sf-client.ts` — nav entry `{ title: 'Clients',
  path: '/sf-client/guides/clients' }` as the first child of _User Guides_.

## Test plan

No automated test setup exists for `public-docs` (Vue docs site). Gates:

- `npm run type-check` (vue-tsc) — passes.
- `npm run lint` (oxlint + eslint) — clean.
- `npm run build` — succeeds.
- `npm run dev` walkthrough: `/sf-client/guides/clients` renders inside `DocLayout`;
  sidebar shows **Clients** first under _User Guides_ (above Connections); prev/next wire
  automatically; all `RouterLink`s resolve (esp. `/sf-client/api/clients`).

## Acceptance

- A new **Clients** guide is the first _User Guides_ entry and reads as a "when to use which"
  page distinct from the API-reference Clients page.
- Every API name / signature / output on the page matches the verified surface in
  `client.py`, `_default_client.py`, and `api/ClientsPage.vue` — no invented surface.
- type-check + lint + build all green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** exactly as planned —
  `public-docs/src/pages/sf-client/guides/ClientsPage.vue` (new),
  `public-docs/src/router/index.ts` (route before `connections`),
  `public-docs/src/navigation/sf-client.ts` (nav entry, first under _User Guides_), plus this
  ledger and the `docs/tasks/` mirror.
- **Commits:** (filled post-commit)
- **Gates:** `npm run type-check` (vue-tsc) clean; `npm run lint` (oxlint + eslint --fix) clean,
  no files reformatted; `npm run build` ✓ in 865ms (emits `ClientsPage-*.js` for both the new
  guide and the existing api page — filename reuse across `guides/`+`api/` confirmed, matching
  the Benchmarks/Url4/Leaderboard precedent). Dev server boots in 612ms with no errors;
  `/sf-client/guides/clients` returns 200. No automated test suite exists for `public-docs`.
- **Deviations:** Per CLAUDE.md rule 3 (spec→plan→code), the approved plan-mode plan
  `.claude/plans/add-a-user-guide-jolly-conway.md` stands in for formal `docs/spec/` +
  `docs/plan/` artifacts, since this is a docs-only page with no product-behavior or
  architecture change. Landing label `py-screamingface` chosen because `public-docs/` has no
  landing leaf of its own and this documents that product.
