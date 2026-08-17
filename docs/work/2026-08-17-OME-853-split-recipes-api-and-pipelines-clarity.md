---
ticket: OME-853
stack: repo
status: in_progress
started: 2026-08-17
finished:
---

# OME-853 — Split the Recipes/Models/Fusions API page + clarify the Pipelines guide

## Intent

Follow-up to OME-846 (merged). The combined "Recipes, Models, Fusions" API page documents
four types at once; move each concrete recipe type to its own home so the reference reads in
one place per type, and clarify the Pipelines guide.

## Planned changes

- `public-docs/src/navigation/sf-client.ts` — rename "Recipes, Models, Fusions" → "Recipes".
- `public-docs/src/pages/sf-client/api/RecipesPage.vue` — retitle → "Recipes"; keep only the
  abstract `Recipe` base + composition overview; drop the Model, Fusion, Pipeline sections and
  their consts; point to the new homes.
- `public-docs/src/pages/sf-client/api/ModelsCatalogPage.vue` — add the `Model` recipe class
  reference (sig/params/attributes/raises) at the top, above the discovery types.
- `public-docs/src/pages/sf-client/guides/FusionsPage.vue` — add the `Fusion` class reference.
- `public-docs/src/pages/sf-client/guides/PipelinesPage.vue` — add the `Pipeline` class
  reference; clarify the Pipeline-vs-evaluation distinction and what a Pipeline is composed of.
- Cross-links pointing at `/sf-client/api/recipes#…` → new homes (Models page / Fusions guide /
  Pipelines guide).

## Test plan

- Docs only. Gate = the `public-docs-tests.yml` CI equivalents locally (oxlint, eslint, build).

## Acceptance

- Each recipe type documented once, in its home; nav renamed; no dead `/api/recipes#…` links.
- CI-equivalent gates green.

## Outcome

- **Actual files:** as planned — `navigation/sf-client.ts`, `api/RecipesPage.vue`,
  `api/ModelsCatalogPage.vue`, `guides/FusionsPage.vue`, `guides/PipelinesPage.vue` (+ ledger +
  mirror).
- **Commits:** <sha — filled at commit>
- **Gates:** `vue-tsc` + `vite build` ✓ (built in ~0.65s) · `oxlint .` ✓ (0) · `eslint .` ✓ (0).
- **Deviations:** RecipesPage was rewritten in full (mostly removal) rather than edited in place,
  and gained a "Where each type is documented" pointer list. ModelsCatalogPage's discovery types
  are now grouped under a "Discovery types" heading below the new Model section. Generic "recipe"
  links in CandidateResult/Clients were left pointing at the surviving Recipes overview.
