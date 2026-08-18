---
ticket: OME-850
stack: url4
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-850 — Allow a cost total without a per-class breakdown

## Intent

`apps/url4-cloud` must be able to publish the cost OpenRouter authored: one amount, no per-class
split. Two things in `packages/url4` block that today, and both are widenings that leave every
existing caller unchanged.

`CostBreakdown` enforces `total_usd == Σ(five components)` with every component defaulting to
`Decimal("0")`, so a total-only cost raises. And the `Usage` observation event carries only
`input_tokens` / `output_tokens`, while the wire `TokenUsage` it feeds already has five token
classes — the observation seam is the narrow part, and it is the only channel that can attribute a
cost to the right span (the engine binds the sink per node task).

Spec: `docs/spec/2026-08-17-OME-849-run-cost-openrouter.md` §2. Parent: `OME-849`.
Consumer that follows: `OME-851`.

## Planned changes

- `src/url4/streaming/protocol/taxonomy.py` — `CostBreakdown._total_is_sum` becomes
  `Σ components <= total_usd`; docstrings state that the components are an optional partial
  breakdown and `total_usd` is authoritative.
- `src/url4/observe.py` — `Usage` gains `cache_read_tokens`, `cache_creation_tokens`,
  `reasoning_tokens` (`int | None = None`) and `cost_usd` (`Decimal | None = None`); the
  `UsageSink` kwargs comment is updated to match.
- `src/url4/dag/node.py` — `ExecutionContext.report_usage` accepts and forwards the four new
  keyword arguments.
- `tests/unit/test_cost_breakdown.py` (new) — the validator contract.
- `tests/unit/test_usage_sink.py` (append) — the widened sink.

No schema/model change (S1 not applicable — this package has no ORM). No wire-format change: field
names, aliases and JSON shape are untouched.

## Test plan

RED first, all new files/cases appended — no prior test touched.

`CostBreakdown`:
1. A total with no components validates (the OpenRouter shape).
2. Components summing exactly to the total still validate (existing behaviour preserved).
3. Components summing to LESS than the total validate (partial breakdown).
4. Components summing to MORE than the total are rejected — over-reporting stays an error.
5. `total_usd=Decimal("0")` with no components still validates (today's live shape).
6. A partial breakdown keeps exact `Decimal` precision, no float coercion.

`Usage` / sink:
7. `Usage` built with no new kwargs is unchanged, and all four new fields default to `None`.
8. `report_usage` forwards each new kwarg onto the emitted `Usage`.
9. `None` is preserved as `None` — never coerced to `0` — for every new token class.
10. `cost_usd` survives as an exact `Decimal`.

## Acceptance

- A `CostBreakdown` carrying only `total_usd` validates; over-reporting components are rejected.
- Existing exact breakdowns, including `total_usd=0`, keep validating unchanged.
- `Usage(...)` and `report_usage(...)` calls that pass no new arguments behave exactly as today.
- New token classes and `cost_usd` distinguish `None` (not reported) from `0`.
- `uv run .claude/scripts/run_gates.py url4` green (ruff · format · pyright · pytest cov ≥95).

## Outcome

Status: done.

- **Actual files** — as planned, plus one the plan missed:
  - `src/url4/streaming/protocol/taxonomy.py` — `_total_is_sum` → `_total_covers_components`,
    equality becomes `components > total_usd` rejection. Private method, single reference, verified
    by grep before renaming.
  - `src/url4/observe.py` — the four optional `Usage` fields, `Decimal` import, and the `UsageSink`
    kwargs comment with its optional-by-invariant note.
  - `src/url4/dag/node.py` — `ExecutionContext.report_usage` accepts and forwards the four kwargs;
    `Decimal` import added.
  - `tests/unit/test_cost_breakdown.py` (new, 6 cases), `tests/unit/test_usage_cost_fields.py`
    (new, 4 cases).
  - **Not planned:** `tests/unit/test_usage_sink.py` was NOT appended to. A dedicated new file was
    used instead, matching the precedent set by `test_usage_response_model.py` — the file created the
    last time a field was added to `Usage`. Keeps the change append-only by construction.

- **RED evidence:** `7 failed, 3 passed`. The three that passed are the preservation cases (an exact
  breakdown, `total_usd=0`, and over-reporting rejected) — they must and do pass on both sides of the
  change, so they are blast-radius guards rather than tautologies. The seven failed for two distinct
  right reasons: `ValidationError` from the equality rule, and
  `TypeError: report_usage() got an unexpected keyword argument 'cost_usd'`.

- **Gates:** `uv run .claude/scripts/run_gates.py url4` → **ALL GATES GREEN** (append-only test check
  vs HEAD · ruff check · ruff format --check · pyright · pytest `--cov=url4 --cov-fail-under=95`).
  No prior test modified, weakened or deleted — the append-only gate proves it.

- **Blast radius, checked rather than assumed:**
  - `Usage` is constructed at exactly ONE site (`dag/node.py:384`, verified by grep) and
    positionally, so appending fields after `response_model` is safe; that site was updated.
  - Relaxing validation cannot invalidate a previously-valid payload, so no existing producer or
    consumer breaks. `CostBreakdown` is re-exported from `streaming/protocol/__init__.py`; the wire
    field names, aliases and JSON shape are untouched.
  - The three pre-existing `Usage` test files continue to pass unmodified.

- **Deviations:**
  1. `dag/node.py` is 490 lines, past the card's ≤450 guidance. It was **already 475 before this
     change** (`git show HEAD:` verified); the 15 lines added are the new kwargs and their docstring.
     Splitting that module is its own unit of work, not a side effect of this one.
  2. The validator method was renamed, which the plan did not call out. It is private, had a single
     reference, and the old name (`_total_is_sum`) would have actively misdescribed the new rule.

- **S1 (migrations):** not applicable — this package has no ORM and no schema.
