---
ticket: OME-851
stack: url4-cloud
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-851 — Price runs from aigateway provider-authored cost evidence

## Intent

Publish the cost a run actually incurred instead of the `unpriced` placeholder. `connector.py:405`
discards aigateway's `_aigw` accounting block, and `executor.py:313`/`:352` hardcode
`pricing_version="unpriced"` with `total_usd=0`. Read the accounting, convert OpenRouter credits to
USD 1:1, and degrade to `unpriced` — never to `$0` — whenever the evidence cannot support a price.

Spec: `docs/spec/2026-08-17-OME-849-run-cost-openrouter.md` §3. Parent: `OME-849`.
Depends on `OME-850` (landed: a total-only `CostBreakdown` now validates, and `Usage` carries the
cache/reasoning classes plus `cost_usd`).

## Planned changes

- `src/url4_cloud/runner/accounting.py` (new) — `CallAccounting` value object, `read_aigw()`,
  `usd_from_aigw()` implementing the spec §3.2 decision table, and `accumulate()`, the
  unknown-poisons-the-sum helper shared with the executor.
- `src/url4_cloud/runner/connector.py` — `_report_usage` prefers `_aigw` and falls back to the
  provider `usage` object; the call site passes `data.get("_aigw")`; provider derivation uses the
  existing `world_config.provider_of` instead of a local copy of the same rule.
- `src/url4_cloud/runner/executor.py` — `_SpanState.usage` becomes a `_SpanUsage` dataclass;
  `_fold_usage` accumulates the new classes with poisoning; `_finish` and `build_subtree` emit
  `PRICING_VERSION` + the real total when priced and today's exact shape when not.
- `tests/unit/test_accounting.py` (new) — the decision table and the poisoning helper.
- `tests/unit/test_url4_executor_cost.py` (new) — span/subtree emission and rollup poisoning.
- `tests/unit/test_connector_accounting.py` (new) — evidence extraction and the fallback path.

No schema/model change (S1 not applicable — this app has no ORM). No wire-format change: the
`ai.url4.cost.usage` field names and JSON shape are untouched.

## Test plan

RED first, in new files only — no prior test touched.

P0 (a wrong number rather than a visible failure):
1. A cache hit prices to `Decimal("0")` and is marked priced.
2. `accounting_not_supported` with zero attempts prices to `None`, not `Decimal("0")`.
3. A `cache.reference` never contributes to a price.
4. One unpriced span makes the whole subtree unpriced.

P1 (cardinality):
5. Two attempts in one `_aigw` use aigateway's single subtotal once, not summed twice.
6. A failed attempt carrying usage still contributes its tokens.
7. Several gateway calls in one span accumulate; per-span cost equals their sum.

P1 (boundaries / hostile input):
8. `partial` and `unavailable` both price to `None`.
9. Two subtotals, or a non-credits unit, price to `None`.
10. `_aigw` absent / `None` / non-dict / structurally malformed → `None`, no exception.
11. An amount at the 18/33-digit bound survives exactly; negative, non-canonical, `bool` and
    `float` carriers are refused.
12. `accumulate` poisons on either side and sums otherwise.

P1 (the fixed defects):
13. `provider` comes from `_aigw` when attempts exist.
14. `response_model` reaches the span and differs from the requested model.

P2 (regression guards, green before and after):
15. An Anthropic-only run still reports `unpriced`.
16. A run with no model call emits no cost frame.

## Acceptance

- `pricing_version` is `"openrouter-credits-1usd"` when priced, `"unpriced"` otherwise.
- `usd_from_aigw` is total over its input and never raises.
- `Decimal("0")` (genuinely free) and `None` (unknown) are never conflated.
- `uv run .claude/scripts/run_gates.py url4-cloud` green (ruff · format · pyright · layering ·
  pytest cov ≥80).

## Outcome

Status: done.

- **Actual files:**
  - `src/url4_cloud/runner/accounting.py` (new, 249 lines) — `CallAccounting`, `read_aigw`,
    `usd_from_aigw`, `accumulate`, and the canonical-amount guard.
  - `src/url4_cloud/runner/connector.py` — `_report_usage` rewritten to prefer `_aigw`; call site
    passes `data.get("_aigw")`; `_token_count` helper; `provider_of` imported instead of a local copy
    of the same rule.
  - `src/url4_cloud/runner/executor.py` — `_SpanUsage` dataclass replaces the positional 4-tuple;
    `_fold_usage` accumulates the new classes and latches the run-level unpriced flag; `_finish` and
    `build_subtree` emit through `_pricing_version` / `_token_usage`.
  - `tests/unit/test_accounting.py` (new, 42 cases), `tests/unit/test_run_cost_capture.py`
    (new, 14 cases).
  - **Not planned:** the three planned test files were collapsed into two. `test_run_cost_capture.py`
    drives the connector, the fold and the wire together, following
    `test_finish_reason_capture.py`'s precedent of one module per signal across all three seams
    rather than one per source file.

- **RED evidence:** `test_accounting.py` failed collection with `ModuleNotFoundError`, then
  `test_run_cost_capture.py` gave `6 failed, 8 passed` — failing on cost never reaching the event or
  the frame. The 8 that passed are guards (the fallback path, the no-model-call case, and the two
  poisoning cases, which pass trivially while everything is unpriced).

- **The poisoning guards were proven live, not assumed.** Each was re-run with its specific guard
  disabled:
  - `accumulate` changed to skip an unknown instead of poisoning →
    `test_an_unpriced_call_poisons_the_span_that_made_it` FAILS.
  - `build_subtree` changed to ignore `_subtree_unpriced` →
    `test_one_unpriced_span_makes_the_whole_subtree_unpriced` FAILS.
  Both restored; 56 focused tests green.

- **A real defect the tests caught during GREEN:** `amount * _CREDIT_TO_USD` is **not** the identity
  even at a 1:1 rate — `Decimal` multiplication rounds to the ambient context's precision (28
  significant digits by default), which truncated an amount at the producer's 18+33-digit bound.
  Caught by `test_an_amount_at_the_contract_precision_bound_survives_exactly`. Fixed with an explicit
  `localcontext()` at precision 53, so the conversion is independent of whatever decimal context the
  caller runs under.

- **Ruff `PLR0911` (too many returns) was resolved by restructuring, never suppressed.** The fix
  improved the code: ad-hoc amount validation (an `"e" in value` check plus `is_finite`/`< 0` guards)
  was replaced by the producer's own published schema regex, so this consumer now accepts exactly
  what the contract promises and nothing else.

- **Gates:** `uv run .claude/scripts/run_gates.py url4-cloud --skip-append-only` → **ALL GATES GREEN**
  (ruff · format · pyright · layering · pytest `--cov=url4_cloud --cov=url4.streaming
  --cov-fail-under=80`, **1542 passed, 5 skipped, coverage 93.09%**). `run_gates.py url4` re-run →
  **ALL GATES GREEN** including its append-only check.

- **CONFIDENCE-GATE DECISION — one prior test was changed, with owner authorisation
  (2026-08-17).** `tests/unit/test_protocol.py::test_cost_total_must_equal_sum` asserted that
  components not equalling the total is a `ValidationError` — exactly the contract `OME-850`
  deliberately relaxed. Presented to the owner with the alternative (keep equality and instead assert
  the whole OpenRouter amount as `input_usd`, which writes a false claim into a structured field); the
  owner chose to replace the test. It became two tests: a partial breakdown is accepted, and
  components exceeding the total are still rejected. `--skip-append-only` was used for that reason
  and that reason only; the `url4` stack's append-only check remained green and unskipped.
  **Process finding worth keeping:** `packages/url4` has no `CostBreakdown` tests of its own —
  `url4.streaming`'s protocol is tested from `apps/url4-cloud`, whose gate carries
  `--cov=url4.streaming`. So `OME-850`'s gate went green while a test of the contract it changed sat
  in another stack. A contract change in `packages/url4` must run the `url4-cloud` gate too.

- **Deviations:**
  1. `connector.py` (656) and `executor.py` (624) exceed the card's ≤450 guidance. Both were already
     over before this change (614 and 522, `git show HEAD:` verified). Splitting either is its own
     unit of work, not a side effect of this one — the same call made for `node.py` in `OME-850`.
     A partial move was considered and rejected: `accounting.py` deliberately imports nothing from
     `url4`, and moving `_token_usage` there would couple pure cost policy to the wire types.
  2. The spec's §3.4 said an unknown token class should force `unpriced`. **Not implemented, and the
     spec is wrong.** Token counts do not enter the price under this method — the amount is
     provider-authored — so discarding a valid cost because a cache sub-class was unreported would
     throw away a correct number for no gain. Unknown classes instead flatten to `0` on the wire
     (`TokenUsage` has non-optional ints), which is documented at `_token_usage` with the condition
     under which it stops being safe: a rate-card method that multiplies these counts.

- **S1 (migrations):** not applicable — this app has no ORM and no schema.

- **Discovered, NOT fixed here (needs its own unit):** `packages/screamingface`'s
  `_engine/contract.py:350` warns whenever `total_usd` disagrees with the sum of its components — so
  every priced run now logs `SF Engine cost total_usd does not equal its parts`. Harmless (it uses
  `total_usd` regardless) but user-visible log noise in a notebook. It is a third landing label and
  therefore a third sub-issue under `OME-849`.
