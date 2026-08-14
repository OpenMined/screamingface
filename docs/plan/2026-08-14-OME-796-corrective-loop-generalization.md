# Plan — OME-796: staged delivery across the owning work items

Spec: `docs/spec/2026-08-14-OME-796-corrective-loop-generalization.md` · Ledger:
`docs/work/2026-08-14-OME-796-corrective-loop-generalization.md` · Branch:
`OME-796-corrective-loop` (review worktree `/private/tmp/sf-OME-796-corrective-loop`).

**Delivery record:** stage 0 landed separately in PR #597; stages 1–2 are PR #598;
the DRACO adapter is PR #599 and the HealthBench adapter is PR #600. Each PR remains
owned by its named work item and is rebased onto `main` as its prerequisite merges.

**Recon caveat**: file:line references were surveyed at `617441da`; main is now
`40096845` (includes the OME-801/802/803/804 extraction merges) — **re-verify every touch
point against the worktree before editing**; the shapes below are the contract, the lines
are hints.

## Stage 0 — client pre-cleanup (merged PR #597) · OME-826

All in `packages/screamingface/`:

1. Duplicate-member-name paid-run bug: drop the report-side uniqueness rejection
   (`report.py::_members`); keying is by `operation_id`; disambiguate equal display names at
   render. Test: fusion with two providers of the same model produces a Report.
2. Unify the three topology walkers (`_evaluation/url4.py::_validate_topology_node`,
   `_evaluation/candidate.py::_validate_topology_dependencies` +
   `_topology_operation_dependencies`) into one shared walker in `_evaluation/topology.py`
   returning per-binding dependency tuples.
3. Re-add the rendered-surface guard in `_evaluation/linking.py` (scan rendered output for
   unresolved `$candidate*` before returning).
4. Delete dead `_recipe_kind` + unused `synthesis_root` param in `_evaluation/candidate.py`;
   make one typed kind-function and import it from `_ui/cards.py`.
5. `recipe.py::then()` → `Pipeline((self, next_recipe))` one-liner.
6. Hoist the loop-invariant benchmark parse out of the per-candidate `link_candidate` path.

Gate: existing suite green; goldens byte-identical.

## Stage 1 — engine lift + port + manifest + retirement (PR #598) · OME-827

`apps/url4-cloud/src/url4_cloud/benchmarks/`:

1. New `ensemble/` module: lift from `ifeval/runtime.py` (resolve-candidate,
   member-record/answer, gate, select, envelope), `ifeval/iterative_correction.py`
   (expression builders), `corrective_policy.py` (routes/prose; revision scheme moves and
   re-hashes). Every `CHECK_ROUTE` reference becomes a port parameter.
2. Port: benchmark adapters implement
   `check({input, invocation}) → {schema, passed, feedback, satisfaction, answer, invocation}`;
   `_strict_satisfaction` computation moves behind IFEval's adapter (fraction of
   instructions satisfied); generic code reads the number.
3. Manifest: `check_surface` block emitted by `definition.py` metadata/resource and served
   by `rest/benchmarks.py`; schema-pin test updated.
4. Retire `ifeval/lanl-ensemble` + `ifeval/self-corrective`: delete the two `Benchmark`
   declarations, drop from `builtins.py`; delete their transport goldens (heads-up posted on
   OME-796 for Keelan — two public ids disappear).
5. IFEval adapter = `deterministic_check` (relocation; free; #528 leak guard stays).

Gate: url4-cloud suite + migrated substrate tests (parameterized by a stub check surface).

## Stage 2 — client recipes + compilation + preflight + notebook 07 (PR #598) · OME-828

`packages/screamingface/`:

1. `sf.CorrectiveLoop(members, judge=..., max_rounds=3)` + `sf.SelfCorrective(model,
   max_rounds=3)`: join `_recipe()` normalization + `_is_supported_recipe`; member floor ≥2;
   root-only enforcement at compile.
2. `_CandidateCompiler` loop context: render member/round/gate/select expression
   client-side with manifest `check_surface` routes; bind as ONE whole `$candidate`.
3. `_RecipeTopology`: new kinds `corrective_loop`/`self_corrective` (+ members, judge,
   max_rounds, check revision); encoder/decoder + the (now single) walker updated.
4. `_evaluation/benchmark.py`: decode `check_surface` from the resource.
5. Runner preflight after `load_benchmark`: missing surface → `PlanningError` permanent;
   paid surface → expected check spend surfaced.
6. Reporting: `stop_reason` + `rounds_executed` per case.
7. Notebook 07 → 2×2 grid (plain kimi · Fusion · SelfCorrective(kimi) ·
   CorrectiveLoop([haiku, gemini], judge=kimi)) via `scripts/build_notebooks.py`; one
   comparison cell (score + cost + rounds_executed).

Gate: compile goldens (byte-identical), preflight tests, construction validation, notebook
check green against local stack (free models only).

## Stage 3 — DRACO adapter + notebook cell (PR #599) · OME-829

1. DRACO check route: one judge pass over the case rubric for a single answer (paid).
2. `draco-pass.v1`: passed = normalized weighted score (clipped [0,1]) ≥ 0.7; satisfaction
   = same score. Named + revisioned; carried in manifest + reports.
3. Feedback policy: axis-level only ("factuality unmet") — leak test asserts no criterion
   text ever crosses the feedback route.
4. `expected_check_cost: "paid"`; judge-call hygiene: prompts salted with answer hash,
   failed verdicts never cached, in-flight cap.
5. DRACO notebook corrective cell (one changed line vs notebook 07; prints preflight spend
   estimate; mock stack default).

## Stage 4 — HealthBench adapter + `rubric_check` extraction (PR #600) · OME-830

1. HealthBench adapter written against the DRACO shape → extract the shared part as the
   `rubric_check` registry component with named args (rubric source, threshold — clamped
   score (negative total never passes), feedback vocabulary).
2. Migrate DRACO's adapter onto the component (goldens byte-identical).
3. **Deletion test: HealthBench = args only.** If it needs new Python, stop — the template
   failed; do not ship a pass-through.
4. HealthBench notebook corrective cell.

## Test map (stage → tests)

See ledger "Test plan". Invariant naming per house rule (e.g. "gate skips coaching for
already-passing members because exact-round coaching is anti-LANL spend").

## Risks

- Same-PR retirement of two public benchmark ids → Keelan heads-up + compat lane before merge.
- `LANL_FLOW` revision re-hash: results not comparable across the boundary (accepted, noted in PR).
- `draco-pass.v1` may be revised in review → stage-3/4 goldens re-bake once (contained: named arg).
- Corrective-on-DRACO may prove structurally weak once sanitized feedback exists — valid outcome.
