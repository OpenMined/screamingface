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
  3. Added beyond the plan: an end-to-end test that resolves the BUILT professional
     expression against a fake judge and proves the official clip reaches the reported
     score (-3.0 per Case → 0.0 exam score), plus a privacy assertion that the new board's
     cases route leaks no rubric text.

## Follow-ups (not in this unit)

- **Scoreboard seed entry** — `apps/scoreboard/charts/scoreboard/values.yaml` needs a
  `healthbench-professional` block with revision `d8fb037307f35415`. Separate landing
  label → its own sub-issue (cross-cutting rule). NOTE while filing it: the seeded
  worst30 revision there is `6cd57aee171fbdc4`, while `main` now computes
  `39cfd96b068f7230` — that board's seed is stale and should be re-copied in the same
  change.
- SDK example notebook for the new board — optional.
- The first paid full-525 run is owner-executed.
