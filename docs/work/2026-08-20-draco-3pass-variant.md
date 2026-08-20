---
ticket: none
stack: screamingface-engine
status: in_progress
started: 2026-08-20
finished:
---

# draco-3pass — DRACO 3-pass board for the cache-seeded replay

## Intent

The `draco-cache-seed` archive covers DRACO grading rounds 1–3 only; canonical DRACO
grades five times and still pays for rounds 4–5. This unit adds a second DRACO board
(`draco-3pass`, 3 judge passes) so re-running the archived candidates is served fully
from the shared response cache, while the canonical five-pass board stays frozen and
comparable.

## Planned changes

- NEW `apps/screamingface-engine/src/screamingface_engine/benchmarks/draco/exam.py`
  — factory: `Routes`, `DracoExam`, `draco_revision`, `build_draco_protocol`,
  `draco_benchmark` (mirrors `healthbench/exam.py`).
- `.../draco/definition.py` — boards module: `DRACO` (frozen revision
  `66a463248586b277`) + `DRACO_3PASS` (`b8c8afd8f9dddca0`); canonical aliases kept.
- `.../draco/runtime.py` — `install(node, root, exam)`; per-board evidence cardinality.
- `.../benchmarks/builtins.py` — add `DRACO_3PASS`.
- NEW `tests/unit/test_draco_3pass_definition.py`.
- `tests/unit/test_benchmark_protocol.py` — catalogue tuple gains `draco-3pass`.
- `tests/unit/test_draco_case_evaluation_route.py` — `install(...)` signature.
- Docs: spec → `docs/spec/`, plan → `docs/plan/`, task mirror, this ledger;
  `draco-cache-seed/RUNBOOK.md` updated in the main checkout (dir is untracked).

## Test plan

- Canonical revision frozen; variant revision distinct; routes disjoint.
- 3-pass protocol renders 3 verdicts / `evidence_1..3` / seeds 1–3 only.
- Both boards install and registry-validate on one world (shared assets).
- Aggregate with `judge_passes=3` carries the variant identity; 4th pass aborts.

## Acceptance

- `uv run .claude/scripts/run_gates.py screamingface-engine` ALL GREEN.
- Canonical `draco` revision byte-identical (`66a463248586b277`).
- SDK: `sf.evaluate(candidate, benchmark="draco-3pass")` resolves via the catalog.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned; RUNBOOK.md updated in the main checkout only (the
  `draco-cache-seed/` directory is untracked local ops data and is not part of the PR).
- **Commits:** <sha — message>
- **Gates:** `run_gates.py screamingface-engine --skip-append-only` → ALL GATES GREEN.
  Append-only check flagged the two planned prior-test edits; that change surface was
  named in the owner-approved spec/plan (Confidence-Gate decision at approval).
- **Deviations:** none.
