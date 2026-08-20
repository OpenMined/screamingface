---
ticket: OME-903
stack: screamingface-engine
status: done
started: 2026-08-20
finished: 2026-08-20
---

# OME-903 — Add the full HealthBench Professional board (525 cases, official clipped score)

## Intent

Serve a SECOND HealthBench identity over the answer key the image already bakes: all 525
`openai/healthbench-professional` cases, scored with the official clipped mean, so a fan
can put our leaderboard next to a published HealthBench number and the comparison is fair.
The existing worst-30% challenge board keeps its frozen 157-case list, its unclipped
metric, and its revision — untouched. Spec:
`docs/spec/2026-08-20-OME-903-healthbench-professional.md`; plan:
`docs/plan/2026-08-20-OME-903-healthbench-professional.md`.

## Planned changes

- NEW `apps/screamingface-engine/src/screamingface_engine/benchmarks/healthbench/pins.py`
  — dataset / judge / preparer / check-criterion pinning both boards share (moved
  verbatim, values unchanged).
- NEW `…/healthbench/exam.py` — `Routes`, `Exam`, `exam_revision`,
  `build_exam_protocol`, `healthbench_benchmark()`.
- NEW `…/healthbench/professional.py` — the 525-case board.
- MOD `…/healthbench/definition.py` — worst30 rewired onto the factory; route constants
  derived from its `Exam`; pinning names move to `pins`.
- MOD `…/healthbench/scoring.py` — add `clipped_mean` (the official aggregate).
- MOD `…/healthbench/aggregate.py` — `aggregate(..., mean=…)` instead of a hardcoded
  `unclipped_mean`.
- MOD `…/healthbench/runtime.py` — `install(node, root, exam)`.
- MOD `…/healthbench/prepare.py` — row-count invariant (525) + import move.
- MOD `…/benchmarks/builtins.py` — register the new board.
- NEW `apps/screamingface-engine/tests/unit/test_healthbench_professional.py`; appended
  cases in `test_healthbench_definition.py`, `test_healthbench_aggregate.py`,
  `test_healthbench_runtime.py`, `test_healthbench_prepare.py`; import-only updates where
  the pinning names moved; the catalogue tuple in `test_benchmark_protocol.py` grows to
  four benchmarks.

## Test plan

RED first, per the plan's §2 table:

- Identity: registered under `healthbench-professional`; 525 cases; ids exactly `1..525`;
  revision differs from worst30's and pins every route.
- Protocol: expression renders, re-parses, < 4000 chars; judge-call bytes identical to
  worst30's; candidate invoked with `web_search=false`; `limit=3` slices without
  redefining the board; check surface advertised under this board's prefix with criterion
  `healthbench-pass.v1`, cost `paid`.
- Scoring: `clipped_mean` floors a negative mean at 0.0, passes a normal mean through,
  returns `None` on empty; the SAME case set scores 0.0 on the professional board and
  stays negative on worst30 — the one real behavioural difference.
- Regression guard: worst30's `REVISION` stays `39cfd96b068f7230`.
- Coexistence: both exams install into one Runner node with disjoint routes off one asset
  root.
- Build invariant: `prepare.emit()` raises `PrepareError` when the dataset no longer holds
  exactly 525 rows.

## Acceptance

- `GET /v1/benchmarks` lists four boards; `healthbench-professional` reports
  `case_count: 525` and its own revision.
- A `limit=N` offline/fake-judge run through the professional routes produces a report
  whose score is the clipped mean, with worst30's behaviour unchanged.
- `uv run .claude/scripts/run_gates.py screamingface-engine` green.
- Follow-up named, not silently dropped: the scoreboard seed entry carrying this board's
  revision is a scoreboard sub-issue (cross-cutting rule).

## Outcome

- **Actual files:** as planned. New: `healthbench/pins.py`, `healthbench/exam.py`,
  `healthbench/professional.py`, `tests/unit/test_healthbench_professional.py`. Modified:
  `healthbench/{definition,scoring,aggregate,runtime,check_policy,prepare}.py`,
  `benchmarks/builtins.py`, and the five test files listed under Deviations. Mirror
  `docs/tasks/2026-08-20-OME-903-healthbench-full-benchmark.md` moved to `in_progress` and
  now carries the computed revision.
- **Computed identity:** `healthbench-professional` · revision `d8fb037307f35415` · 525
  Cases. worst30 unchanged at `39cfd96b068f7230` (now pinned by a test).
- **Gates:** `run_gates.py screamingface-engine` — ALL GATES GREEN (ruff · ruff format ·
  pyright · check_layering · pytest). 1861 passed, 5 skipped, coverage 93.5% (floor 80%).
- **Commits:** see the PR.
- **Deviations:**
  1. **The append-only check was skipped, with owner approval (2026-08-20).** Four prior
     test files changed and the gate correctly stopped on rule 5:
     - `test_benchmark_protocol.py` — the public catalogue tuple grows from three
       benchmarks to four. UNAVOIDABLE: it is the assertion this ticket exists to change.
     - `test_healthbench_aggregate.py` (14 call sites) and
       `test_benchmark_outcome_conformance.py` (1) — `aggregate()` gained the required
       `mean=` keyword, so every call site names its board's metric. Call sites only; no
       assertion touched.
     - `test_healthbench_runtime.py` (10 call sites) — `install()` gained the `exam`
       argument, and the one test that imported the private `_build` now goes through the
       public `HEALTHBENCH_WORST30.protocol(1)`. Call sites and imports only.
     The alternative — defaulting `mean` to the challenge metric and keeping
     worst30-shaped shims — was declined: a silent default would hand a future caller the
     wrong metric, and the shims would exist only to spare old test call sites.
  2. `build_exam_protocol` fixes a latent defect carried over with the moved code: in
     `definition._build` the docstring sat AFTER the first statement, so Python treated it
     as a no-op string expression, not a docstring. It is now the first statement.
  3. **Both boards live in one `definition.py`; `professional.py` was folded in and
     deleted (owner call, 2026-08-20).** Reviewing the branch, the split read wrong: a
     reader looking for the full board opened `definition.py` and found only worst30,
     because that generic filename historically meant "the worst30 board". One file with
     two clearly-headed sections matches the sibling packages (`draco/definition.py`,
     `ifeval/definition.py`) and puts the difference between the boards on one screen.
     Consequence: the module-level route/id/revision aliases are gone — a board is reached
     through `<BOARD>_EXAM.routes.*` / `.revision`, so no unprefixed name can silently
     mean one of the two. That rewired ~30 mechanical call sites in
     `test_healthbench_{runtime,check_surface,definition}.py`. worst30's rendered resource
     was re-verified byte-identical to `main` afterwards, and both revisions are unmoved.
  4. Added beyond the plan: an end-to-end test that resolves the BUILT professional
     expression against a fake judge and proves the official clip reaches the reported
     score (-3.0 per Case → 0.0 exam score), plus a privacy assertion that the new board's
     cases route leaks no rubric text.

## Folded in — the SDK example notebook (owner call, 2026-08-20)

`OME-905` was filed for this and then folded back into this unit at the owner's direction:
one PR, one review. `OME-905` is canceled in Linear pointing here.

The only HealthBench example was named and written as if the worst-30% challenge were the
whole benchmark, so shipping the professional board would have left it invisible in the
examples — and the filename would have implied it did not exist.

- `08_healthbench_worst30.ipynb` → `08_healthbench.ipynb`, regenerated from
  `scripts/build_notebooks.py` (never hand-edited); `_healthbench_worst30_e2e()` →
  `_healthbench_e2e()`.
- The notebook opens with what actually differs between the boards (which conversations
  are asked; floored vs unfloored average) and what does not (same rubrics, same judge),
  then evaluates the SAME Fusion on both — each at `limit=1`, publication still behind
  `PUBLISH_RESULT = False`, so **Run All** spends nothing unexpected.
- `09_corrective_loops.ipynb`'s check-cost table gains the professional row (same paid
  judge, 525 Cases instead of 157).
- One README line named the old file.
- Gates: `run_gates.py screamingface` — ALL GREEN (ruff · format · pyright · pytest 95%
  floor · check_notebooks · uv build · check_distribution).
- **No new graphic.** The existing `healthbench-worst30-benchmark.svg` still illustrates
  the worst-30% board and the comparison is a markdown table; a companion SVG is a design
  decision, flagged not invented.
- **Notebook cell formatting is enforced by `ruff format` THROUGH the generated file**, so
  the builder must emit code cells already in ruff's preferred shape — a wrapped
  `sf.evaluate(...)` call failed the gate until written on one line.

## Follow-ups (not in this unit)

- **Scoreboard seed entry** — `apps/scoreboard/charts/scoreboard/values.yaml` needs a
  `healthbench-professional` block with revision `d8fb037307f35415`. Separate landing
  label → its own sub-issue (cross-cutting rule). NOTE while filing it: the seeded
  worst30 revision there is `6cd57aee171fbdc4`, while `main` now computes
  `39cfd96b068f7230` — that board's seed is stale and should be re-copied in the same
  change.
- **Pre-existing generated-notebook drift, deliberately kept out of this PR:** rebuilding
  regenerates `00_quickstart.ipynb` and `01_client_tour.ipynb` with shifted cell ids
  (`cell-05` → `cell-04` …) — the committed files came from an older builder that emitted
  one extra early cell. `check_notebooks.py` misses it because it compares authored cell
  SOURCES, not ids. Reverted out here to keep the diff scoped; the drift AND the gate's
  blind spot deserve their own ticket, since the next rebuild hits the same noise.
- **Pre-existing README drift, untouched:** the same list names
  `examples/06_draco_full_e2e.ipynb` and `examples/07_ifeval_e2e.ipynb`, but the generated
  files are `06_draco.ipynb` and `07_ifeval.ipynb` — two broken links predating this
  change.
- The first paid full-525 run is owner-executed.
