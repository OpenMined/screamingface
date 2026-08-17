---
id: OME-853
linear_url: https://linear.app/openmined/issue/OME-853/split-the-combined-recipesmodelsfusions-api-page-and-clarify-the
status: in_progress
type: task
priority: P2
labels: [repo, agentic, autonomous, task]
created: 2026-08-17
closed:
---

Follow-up to OME-846 (merged). Split the combined "Recipes, Models, Fusions" API page so each
recipe type lives in one home, and clarify the Pipelines guide.

- Rename nav + page "Recipes, Models, Fusions" → "Recipes" (keep only the `Recipe` base).
- Move `Model` → `api/ModelsCatalogPage.vue`; `Fusion` → `guides/FusionsPage.vue`; `Pipeline` →
  `guides/PipelinesPage.vue`. Update `/api/recipes#…` cross-links.
- Pipelines guide: clarify Pipeline-vs-evaluation and what a Pipeline is composed of.

Ledger: `docs/work/2026-08-17-OME-853-split-recipes-api-and-pipelines-clarity.md`.
