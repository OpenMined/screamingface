---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-18
finished: 2026-07-18
---

# OME-400 — Lock the greenfield benchmark public contract

## Intent

Define the exact public Python recipes and load → run → grade → aggregate artifacts for the
unreleased ScreamingFace SDK before replacing its current evaluation implementation. GPQA and
DRACO and a tiny in-memory benchmark must fit the same compact API without compatibility wrappers,
an ETL/loader DSL, or engine-backend details leaking into benchmark definitions.

## Planned changes

- Add a superseding benchmark public-contract spec under `docs/spec/`.
- Add syntax-valid GPQA, DRACO, in-memory, and walkthrough examples using only the proposed public
  API.
- Record the universal `Case`, plain-Python `Benchmark`, immutable in-memory `Run`, `Grades`, and
  `Report` contracts.
- Update the OME-400 plan/task mirror to point at the greenfield contract.
- Do not modify SDK implementation or notebooks in this unit.

## Test plan

- Parse and lint all Python fixtures without importing the not-yet-implemented API.
- Check Markdown and Python files for whitespace errors.
- Review all recipes side by side for identical framework syntax and benchmark-specific ordinary
  Python only.
- Verify the contract contains no direct AI Gateway client, public engine object, route-backed
  scorer, public loader/runner registry, `fork()`, `with_changes()`, or arbitrary Python
  auto-import.

## Acceptance

- GPQA, DRACO, and in-memory cases use the same `sf.Case` and `sf.Benchmark` fields.
- `Fusion.evaluate()` and the explicit four stages have one unambiguous return contract.
- Hidden references are structurally excluded from worker inputs.
- Run and grading evidence remains explicit and serializable in memory.
- The owner can review the exact proposed API before implementation begins.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** benchmark public-contract spec, phased architecture plan, four syntax fixtures,
  this work record, and the existing OME-400 task mirror.
- **Commits:** pending owner commit.
- **Gates:** Python fixtures parse; whitespace and stale-contract audits pass.
- **Deviations:** none. Runtime SDK, notebooks, URL4, AI Gateway, and the hidden Docker spike were
  not modified.
