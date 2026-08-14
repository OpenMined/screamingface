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

- **Actual files:** engine — new `apps/url4-cloud/src/url4_cloud/benchmarks/ensemble/`
  (policy, runtime: gate/select/answer), `ifeval/{definition,runtime,aggregate}.py`
  (check-surface adapter, retirement), `benchmarks/{definition,builtins}.py`,
  `runner/main.py`; deleted `ifeval/{iterative_correction,corrective_policy}.py` + 4
  variant-only test files; new `tests/unit/{test_ensemble_corrective,
  test_ifeval_check_surface,test_ifeval_grading_feedback,test_corrective_loop_e2e}.py`
  + `tests/unit/data/*.url4` client-rendered goldens. client — new
  `src/screamingface/corrective.py`, `_evaluation/corrective.py` (loop renderer);
  extended `recipe/report/_evaluation/{candidate,topology,benchmark,compilation,
  runner,model,url4}.py`, `__init__.py`; notebook 07 rebuilt as the 2×2 grid; new
  `tests/{test_corrective_recipes,test_corrective_compilation,
  test_check_surface_preflight}.py`.
- **Commits:** `9f47489a` (stage 1, engine), `70627b6c` (stage 2, client),
  `78c1f8a4` (cross-stack e2e + transport goldens). Stage 0 landed separately as
  PR #597 (`OME-826`); this branch is stacked on its head.
- **Gates:** url4-cloud ALL GREEN (ruff, format, pyright, layering, pytest
  1405p/5s with cov≥80); screamingface ALL GREEN (ruff, format, pyright, pytest
  819p/1s with cov≥95, check_notebooks, build, check_distribution). Append-only
  check skipped deliberately for the plan-approved variant retirement (deleted
  variant tests are named in the stage-1 commit).
- **Deviations:**
  1. **Check port is input-addressed** (`check({input, answer})`, new
     `/benchmarks/ifeval/<rev>/check-surface` route) — a black-box `$candidate`
     only sees `$input`, so the plan's implied case-addressed check was
     unimplementable; the adapter resolves the case by exact prompt text.
  2. **Engine expression builders NOT lifted** — with the client owning loop
     compilation they would be dead code; the generic module is only the three
     pure data→data endpoints + policy. Deletion test applied.
  3. **Ensemble gate/select/answer routes are `/ensemble/corrective/v1/*` wire
     constants** (same class as `/benchmarks/candidate`), not manifest fields —
     the manifest advertises only the benchmark-owned check surface.
  4. **`stop_reason`/`rounds_executed` reporting DEFERRED** — loop internals
     cannot reach the canonical aggregate without a case-evaluation contract
     change; needs its own ticket.
  5. **URL4 replay of loop artifacts rejected with a named error** — the flat
     call scan cannot see gated rounds; extension is follow-up work.
  6. **SelfCorrective gates its rounds (early exit)** — deliberate improvement
     over the retired engine variant's unconditional three attempts.
  7. **Stages 3–4 (DRACO/HealthBench adapters) intentionally NOT in this PR**
     per Khoa's 2026-08-14 instruction ("corrective loop only"); the plan's
     stage 3/4 sections remain open under `OME-827`.
  8. TDD inverted for the client loop renderer (url4 render-rule discovery
     forced iteration); behavior locked afterwards by the compilation tests and
     the engine-side e2e with client-rendered goldens.
