---
ticket: OME-811
stack: repo
status: in_progress
started: 2026-08-13
finished:
---

# OME-811 — Fix broken Recipe docs: synthesizer, drop CorrectiveEnsemble, add Pipeline

## Intent

The `public-docs/` API reference and Fusions guide describe a `screamingface` Recipe API that no
longer exists: `Fusion(reducer=...)`, `sf.reducers.*`, and `sf.CorrectiveEnsemble` are gone, and
`Pipeline` (serial + recursive composition) is undocumented. Because `synthesizer` is now a required
argument, the docs' own `sf.Fusion([opus, gpt])` example raises on copy-paste. This unit (WS1 of the
OME-810 epic) makes the recipe pages accurate to the shipped package and adds the missing serial-
composition story.

## Planned changes

- `public-docs/src/pages/sf-client/api/RecipesPage.vue` — `reducer`→`synthesizer` (required);
  delete `CorrectiveEnsemble` section; add `Pipeline` section (`.then()`, flatten-vs-nest); refresh
  intro/description; verify `Model` default-params claim vs `_evaluation/policy.py`.
- `public-docs/src/pages/sf-client/guides/FusionsPage.vue` — `reducer`→`synthesizer` throughout
  (SVG caption, Main-APIs table, reprs, examples, `/learn/engine` link, corrective note).
- NEW `public-docs/src/pages/sf-client/guides/PipelinesPage.vue` — serial + recursive composition.
- `public-docs/src/navigation/sf-client.ts` + `public-docs/src/router/index.ts` — register the new
  Pipelines guide (minimal WS4 slice needed to ship WS1).

## Test plan

`public-docs/` is a Vue SPA with no unit-test suite; the gate is type-check + build + accuracy greps.

- `cd public-docs && npm run type-check && npm run build` — both green.
- `grep -rE 'reducer|CorrectiveEnsemble|MajorityVote|sf\.reducers'` over the two edited recipe pages
  → no hits.
- Every recipe signature/repr in the edited pages matches
  `packages/screamingface/src/screamingface/{model,fusion,pipeline}.py` and
  `tests/test_pipeline_recipes.py`.
- Every `sf.*` symbol referenced appears in `src/screamingface/__init__.py::__all__`.

## Acceptance

- The three recipe pages (Recipes API, Fusions guide, new Pipelines guide) are accurate to the
  current API; no reference to removed symbols remains on them; build + type-check green; new guide
  wired into sidebar + prev/next.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `api/RecipesPage.vue` (rewrite), `guides/FusionsPage.vue`
  (rewrite), NEW `guides/PipelinesPage.vue`, `navigation/sf-client.ts` + `router/index.ts`
  (wire the Pipelines guide). No other page touched.
- **Commits:** <sha — filled at commit>
- **Gates:** `npx oxlint .` PASS · `npx eslint .` PASS · `npm run type-check` PASS ·
  `npm run build` PASS (type-check + vite, PipelinesPage/FusionsPage/RecipesPage all built).
  Scoped stale-term grep over the three recipe pages: clean except one deliberate mention
  ("there is no `reducer` attribute", matching the source test `not hasattr(fusion, "reducer")`).
- **Deviations:**
  - The source contract had drifted further than the plan named. Corrected against
    `model.py`/`fusion.py`/`pipeline.py` + `tests/test_recipes.py`/`test_pipeline_recipes.py`:
    (a) recipes compare **by value** and are unhashable — the old "compare by identity → False"
    cell was wrong; (b) a Fusion needs **≥1** member, not ≥2; (c) there is **no** construction-time
    duplicate-member-name check; (d) a Model applies **no default `params`** (only a default
    prompt) — the old `reasoning="low"` / `max_output_tokens=4096` claim was removed.
  - `npm run format` (prettier) reformatted 11 pre-existing files unrelated to WS1; reverted them
    — CI does not gate prettier (only oxlint/eslint/build), so this is pre-existing drift for a
    later pass, not this ticket.
  - Refreshed the stale `OME-605-…` GitHub link on the Fusions page to `main` (the page was being
    rewritten anyway). Remaining stale-term hits live on `QuickstartPage.vue` and `Url4Page.vue`
    (WS3/WS4, tracked in OME-813/OME-814).
