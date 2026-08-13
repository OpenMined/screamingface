---
id: OME-811
linear_url: https://linear.app/openmined/issue/OME-811/fix-broken-recipe-docs-synthesizer-drop-correctiveensemble-add
status: in_progress
type: task
priority: P1
labels: [repo, agentic, autonomous, task]
created: 2026-08-13
closed:
---

WS1 of OME-810. Fix the `public-docs/` pages that are factually wrong today and add the missing
serial-composition story:

- `src/pages/sf-client/api/RecipesPage.vue` — `reducer`→`synthesizer` (required), drop
  `CorrectiveEnsemble`, add `Pipeline` section.
- `src/pages/sf-client/guides/FusionsPage.vue` — `reducer`→`synthesizer` throughout.
- NEW `src/pages/sf-client/guides/PipelinesPage.vue` — serial + recursive composition; wired into
  `src/navigation/sf-client.ts` + `src/router/index.ts`.

Ledger: `docs/work/2026-08-13-OME-811-public-docs-recipe-fix.md`.
