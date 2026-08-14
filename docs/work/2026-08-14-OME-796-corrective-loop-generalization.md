---
ticket: OME-796 (epic; sub-issues OME-827 engine, OME-828 client)
stack: url4-cloud + screamingface
status: in_progress
started: 2026-08-14
finished:
---

# OME-796 — Generalize the corrective loop: engine lift + check-surface port + client recipes + adapters

## Intent

Make the LANL corrective protocol a benchmark-independent capability. Today it is welded
into `benchmarks/ifeval/` as two registry variants and is uncompilable from the client
(the engine's `_build_lanl` emits a two-hole `$candidate_members`/`$candidate_synthesizer`
shape the linker rejects with `candidate_shape_mismatch`). After this unit: the loop
machinery lives in generic `benchmarks/ensemble/` behind a check-surface port
(`check(answer) → {passed, feedback, satisfaction}`), benchmarks advertise
`check_surface` in their manifest, and `sf.CorrectiveLoop` / `sf.SelfCorrective` compile
the whole loop client-side into ONE `$candidate`. IFEval (free deterministic check),
DRACO (`draco-pass.v1`, score ≥ 0.7, paid), and HealthBench (second rubric customer →
`rubric_check` registry component extraction) are the three adapters.

Design source of record: OME-796 issue body ("Design resolution 2026-08-14") +
`.dk/plans/2026-08-13-ome796-corrective-loop-generalization.md` (untracked working copy).

## Planned changes

ONE PR, staged commits (stage 0 → 4):

- Stage 0 (client pre-cleanup, PR #571 findings): `packages/screamingface/src/screamingface/`
  `report.py` (drop duplicate-name rejection; disambiguate display), `_evaluation/url4.py` +
  `_evaluation/candidate.py` + `_evaluation/topology.py` (single topology walker; delete dead
  `_recipe_kind`/`synthesis_root`), `_evaluation/linking.py` (re-add rendered-surface guard;
  hoist invariant benchmark parse), `recipe.py` (`then()` one-liner), `_ui/cards.py` (shared kind fn).
- Stage 1 (engine): new `apps/url4-cloud/src/url4_cloud/benchmarks/ensemble/` (lifted from
  `ifeval/runtime.py` + `iterative_correction.py` + `corrective_policy.py`); check-surface port;
  manifest `check_surface` block in `benchmarks/definition.py` + `rest/benchmarks.py`; retire
  `ifeval/lanl-ensemble` + `ifeval/self-corrective` from `builtins.py`; IFEval adapter.
- Stage 2 (client): `recipe.py`/new `corrective.py` (`CorrectiveLoop`, `SelfCorrective`),
  `_evaluation/candidate.py` (loop compilation), `_evaluation/benchmark.py` (decode
  `check_surface`), runner preflight, `stop_reason`/`rounds_executed` reporting, notebook 07
  2×2 grid via `scripts/build_notebooks.py`.
- Stage 3: DRACO check adapter (route + `draco-pass.v1` + axis-level feedback) + DRACO
  notebook corrective cell.
- Stage 4: HealthBench adapter + `rubric_check` extraction + HealthBench notebook cell.

NOTE: recon file:lines were taken at `617441da`; main has advanced (`40096845`, includes the
OME-801/802/803/804 extraction PRs) — re-verify every touch point before editing.

## Test plan

- Migrated substrate tests parameterized by a stub check surface (from
  `test_ifeval_lanl_ensemble.py`, `test_ifeval_iterative_correction.py`, `test_ifeval_member_shape.py`).
- Manifest schema pin updated for `check_surface`.
- New client tests: construction validation (member floor ≥2, root-only, `judge=` only),
  compile goldens (byte-identical loop url4), preflight fail-before-spend (no check surface;
  paid-check spend surfaced), linking still one whole-`$candidate`.
- Adapter leak tests: IFEval #528 guard stays; DRACO axis-level; HealthBench theme-level.
- Stage-0 regression: goldens stay byte-identical through cleanup.

## Acceptance

- The decisive test: manual e2e notebook runs (07 grid + DRACO + HealthBench cells) on
  several examples against the mock stack — drafts differ across rounds, feedback useful and
  leak-free, passing draft ships verbatim, `stop_reason`/`rounds_executed` coherent, cost
  matches round count. Live runs are Khoa-triggered only.
- `sf.CorrectiveLoop`/`sf.SelfCorrective` runnable against `ifeval` (and `draco`/`healthbench`
  after their stages) with benchmark switch = one changed line.
- Preflight refuses loop × no-check-surface benchmark before any spend.
- Deletion test at stage 4: HealthBench adapter is args-only.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:**
