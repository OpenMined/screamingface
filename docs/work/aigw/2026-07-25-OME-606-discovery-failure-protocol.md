---
ticket: OME-606
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-606 — One failure protocol for discovery

## Intent

Narrow `None` to mean exactly "no attempt was made", so a failed fetch is distinguishable from a
provider that simply has no dynamic source — and therefore reaches the cache's stale/degraded paths
instead of being stored as fresh.

## Evidence

- `plugins/openrouter_provider/discovery.py:196-197` — `except DiscoveryError: return None`. The
  sanitized reason code is discarded here.
- `plugins/openrouter_provider/plugin.py:351-356` — the hook returns `None` at `:352` and `:355`
  for **not attempted** (bad gateway prefix / invalid upstream id, no connection opened), then
  returns the helper's value at `:356`, which is `None` for **attempted and failed**.
- `core/plugin_base.py:272-278` — the port docstring states both meanings in one paragraph:
  "returns sanitized None on any failure" and "Default: None — no dynamic source".
- `core/parameter_discovery_cache.py` `get_or_refresh` — only an `except DiscoveryError` reaches
  `_on_refresh_error`. Any value returned normally, `None` included, is stored via `_store` and
  labelled `fresh`. So under the current protocol an outage would evict the last good snapshot and
  publish fresh emptiness.
- Prior-test survey (`tests/unit/openrouter/test_openrouter_discovery_snapshot.py`): exactly one
  test pins failure→None (`test_fetch_failure_returns_none_for_local_fallback`, `:102-109`). The
  hook-level None tests at `:127-135` and `:138-151` are both **not attempted** cases and stay
  valid. No other module references either symbol.

## Design

Three outcomes, three signals:

| situation | signal |
|---|---|
| reached the source | `ProviderDiscoverySnapshot` (empty snapshot = reached, model not listed) |
| attempted, failed | raise sanitized `DiscoveryError` |
| no attempt made | `None` |

**Where the raise lives — owner decision.** At the low-level fetch helper, so both layers share one
convention. The alternative (translate at the hook) needed no test change but left adjacent layers
disagreeing and replaced the specific reason code with a generic one. Recorded as an explicit
decision because it rewrites a prior test.

`discover_openrouter_snapshot` therefore drops its `try/except` entirely and its return type loses
`| None`: every path either returns a snapshot or propagates. This is a **deletion**, not new
machinery — the swallowing was the defect.

The hook keeps `| None` for its two not-attempted guards and propagates the error untouched. The
port docstring is rewritten to state the three-way contract, replacing the sentence that documents
two meanings for one value.

**Prior test rewritten (Confidence-Gate decision, approved).**
`test_fetch_failure_returns_none_for_local_fallback` asserts the exact contract being replaced, so
it becomes `test_fetch_failure_raises_for_the_cache_to_degrade`. Its other assertion — attempted
exactly once, no retry storm — is preserved verbatim, since that behaviour is unchanged.

## Planned changes

Source (3):
- `plugins/openrouter_provider/discovery.py` — remove the swallow; narrow the return type; docstring.
- `plugins/openrouter_provider/plugin.py` — docstring: `None` now means not-attempted only.
- `core/plugin_base.py` — port docstring states the three-outcome contract.

Tests (1):
- `tests/unit/openrouter/test_openrouter_discovery_snapshot.py` — **1 rewritten** (above) plus
  appends: the hook propagates rather than swallowing, and the cache maps a raising hook to
  stale-then-degraded rather than fresh `None`.

No schema, model, ORM or migration change.

## Test plan (RED first)

- **Helper raises on fetch failure**, carrying the sanitized reason, and still dials exactly once.
- **Hook propagates** the failure instead of returning `None`.
- **Not-attempted paths still return `None` and never dial** — the two existing tests, unmodified.
- **End-to-end through the cache** (the case that motivates the ticket): good snapshot → TTL expiry
  → source failure → `stale` with the previous value → stale window expiry → `degraded`. Under the
  old protocol the first failure would have produced `fresh` `None`.

## Acceptance

- No code path can report a failed fetch as successful evidence.
- `None` has exactly one meaning at the port.
- Full aigateway gate green.

## Outcome

**Status: DONE.** Committed as `0941ef53` —
`fix(aigateway): degrade on a discovery outage instead of caching it as fresh`.

### Actual changes (match plan)

Source (3):
- `plugins/openrouter_provider/discovery.py` — `try/except DiscoveryError: return None` **deleted**;
  return type narrowed to `ProviderDiscoverySnapshot`; docstring rewritten with an implementation note
  spelling out why a `return None` must not come back (the cache reads a normal return as success).
  The now-unused `DiscoveryError` import was removed.
- `plugins/openrouter_provider/plugin.py` — the hook's `None` documented as NOT ATTEMPTED; the
  invariant now says a `DiscoveryError` propagates.
- `core/plugin_base.py` — the port docstring replaced by the three-outcome table, plus an
  implementation note against widening `None` back to cover failure.

Tests (1 file): **1 rewritten** (approved), 2 appended, module docstring invariant updated.

### Quality gate

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only` from the repo root —
**GREEN on attempt 1**: ruff check ✓ · ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ ·
pytest --cov ≥80% ✓. Targeted run beforehand: 628 passed across `tests/unit/core` +
`tests/unit/openrouter`.

### Verification beyond the gate

RED was decisive on the end-to-end test — `AssertionError: assert 'fresh' == 'stale'`. That is the
finding itself: a live outage, driven through the real plugin hook and the real cache, recorded as
fresh evidence with the last good snapshot discarded. After the change the same sequence yields
`fresh → stale (last good value retained) → degraded`.

`--skip-append-only` used with a stated exception. Deleted test lines this unit (verified from the
repo root): the module docstring's old 3-line invariant, the renamed test's `def` line, its two
explanatory comment lines, and its two assertions — 8 lines, all inside the one test whose contract
was deliberately replaced. `assert client.calls == [MODELS_URL]` was preserved verbatim because that
behaviour is unchanged. No other test was touched, weakened, or skipped.

### Deviations

1. **Prior test rewrite approved by the owner** — raised as an explicit question and approved
   before any edit. The alternative (translate at the plugin hook, zero test changes) was rejected
   by the owner in favour of one convention across both layers.
2. **The fix is a deletion.** No new abstraction: the swallow *was* the defect, and removing it plus
   narrowing a return type is the whole change. The added lines are comments and tests.
3. **Commit:** `0941ef53`; `Refs: OME-606, OME-479`.
