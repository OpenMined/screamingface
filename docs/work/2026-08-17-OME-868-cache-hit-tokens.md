---
ticket: OME-868
stack: url4-cloud
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-868 — Stop counting a cache hit's replayed tokens as freshly consumed

## Intent

A cache hit publishes the ORIGINAL response's token counts as though the provider had consumed
them again. `runner/connector.py:342` falls back to the replayed cached body's `usage` whenever
`_aigw` carries no attempts — which is exactly the cache-hit shape — so a hit publishes
`input=651, output=25, cost=$0`.

This contradicts the boundary `OME-851` already enforces for money. aigateway labels the cache
reference `incurred_in_current_request: false`, and
`test_a_cache_reference_never_contributes_to_the_price` exists so a cached answer is never billed.
Counting the same reference's tokens as consumed treats one piece of evidence two opposite ways.

`_report_response`'s INVARIANT already concedes that `_report_usage` "bills it as a fresh call"
and mitigates by publishing `cache_status` beside it — but that mitigation never reaches
`build_subtree`, which emits bare run totals with no cache status attached. A cache-heavy
benchmark therefore overstates provider consumption with nothing in the frame to signal it.

Parent: `OME-849`. Found in peer review of PR #620, not by any gate.

## Planned changes

- `src/url4_cloud/runner/connector.py` — `_report_usage` takes the `CacheOutcome` already in hand
  at the call site (`:449`) and reports zero tokens when `status == "hit"`. Using `CacheOutcome`
  rather than re-deriving hit-ness from `_aigw` keeps the fix working against an older gateway
  that emits no accounting block at all. `WHY:`/`INVARIANT:` anchors naming the producer's
  `incurred_in_current_request: false` contract.
- `tests/unit/test_cache_hit_tokens.py` (new) — RED first, in its own module so no prior test file
  is touched.

No wire/schema change. No new dependency.

## Test plan

RED first, in a new file.

1. A cache hit publishes zero tokens for every class, and still prices at `0` with
   `PRICING_VERSION` — the saving stays visible. (This is the bug.)
2. The same body served as a MISS publishes the provider's real token counts — the guard is
   narrow, not a blanket zeroing.
3. A `bypass` behaves like a miss.
4. No `_aigw` at all (older gateway) still falls back to the provider's own `usage` for a non-hit
   call — the pre-`_aigw` behaviour is preserved.
5. A cache hit still increments `RunCacheCounters`, so "caching saved you this" is not lost.

## Acceptance

- A hit publishes zero tokens and `total_usd == 0`, priced not unpriced.
- Miss and bypass unchanged; the no-`_aigw` fallback unchanged for non-hit calls.
- `uv run .claude/scripts/run_gates.py url4-cloud` green (append-only check intact — no prior test
  is touched).

## Outcome

Status: done.

- **Actual files:** as planned —
  - `src/url4_cloud/runner/connector.py` — new `_report_served_from_cache`, a `cache: CacheOutcome
    | None` parameter on `_report_usage`, and the call site passing the `outcome` it already had
    in hand.
  - `tests/unit/test_cache_hit_tokens.py` (new, 8 cases).

- **RED evidence:** `3 failed, 5 passed`. Each failure was exactly `assert 651 == 0` — the
  replayed cached body's token counts arriving as this request's consumption. The five that passed
  are the guards (miss, bypass, no cache header, the pre-`_aigw` fallback, and the priced-zero
  invariant), and they hold on both sides of the change, which is what makes the fix narrow rather
  than a blanket zeroing.

- **Design choice: hit-ness comes from `CacheOutcome`, not from `_aigw`.** Both could answer it —
  `usd_from_aigw` already reads `usage_accounting.cache.status` to price a hit at zero. The
  published `CacheOutcome` was chosen for two reasons: it is derived from the response headers, so
  it still works against an older gateway that emits no accounting block at all (pinned by
  `test_a_cache_hit_without_any_accounting_block_still_reports_no_tokens`); and it is the SAME
  value `_report_response` publishes as the span's `cache_status`, so the tokens stay consistent
  with the cache outcome printed beside them. Consistency with the *published* status is the
  property that matters — a span reading `cache_status: hit` beside 12,480 consumed tokens is the
  contradiction this unit removes.

- **Zeros, not `None`.** `None` means "the gateway did not report it". A hit reports something
  definite — nothing was consumed — and `OME-869`'s run totals must be able to add that in rather
  than treat it as a gap.

- **Prior art this confirms rather than discovers:** `runner/cache_readback`'s module docstring
  already stated the defect outright ("A cache hit costs nothing upstream, yet `_report_usage`
  bills it exactly like a fresh call"). The mitigation chosen then was to publish `cache_status`
  beside the tokens; that mitigation never reached `build_subtree`, which emits bare run totals
  with no status attached. This unit fixes the numbers rather than annotating them.

- **Checked, not changed:** the revalidation path (`_fetch_completion`) already refuses to report
  the discarded response's usage and returns the outcome of the round trip that produced the
  CONSUMED response, so the outcome passed here is the right one and no double-count is possible.

- **Gates:** `uv run .claude/scripts/run_gates.py url4-cloud --base origin/main` →
  **ALL GATES GREEN** (ruff · format · pyright · layering · pytest
  `--cov=url4_cloud --cov=url4.streaming --cov-fail-under=80` → **1697 passed, 5 skipped, 93%**).
  The append-only check reports only `test_protocol.py`, the owner-authorised `OME-850` exception
  that predates this unit; this unit touched no prior test.

- **Deviations:** none.

- **S1 (migrations):** not applicable — no ORM or schema in this app.
