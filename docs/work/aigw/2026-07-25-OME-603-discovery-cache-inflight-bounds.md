---
ticket: OME-603
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-603 — Bound the observation cache's in-flight coordination state

## Intent

`ObservationCache` bounds its entry table (`max_entries`, LRU) but not its lock table. Give the
in-flight coordination state a lifecycle owned by the callers inside `get_or_refresh`, and make the
failure path coalesce the way the success path already does.

## Evidence

- `parameter_discovery_cache.py:98` — `self._locks.setdefault(key, asyncio.Lock())`. The lock is
  created per key and only ever removed in `_store`.
- `:106-109` — a refresh that raises `DiscoveryError` returns via `_on_refresh_error` **without
  calling `_store`**. Cold failure therefore leaves a lock behind and no entry: N distinct failing
  keys → 0 entries, N locks. The advertised bound covers only half the state.
- `:131-136` — eviction drops the evicted key's lock only `if not evicted_lock.locked()`. Evicting a
  key while a caller holds its lock leaks that lock permanently; nothing re-checks it afterwards.
- `:100-103` — success coalescing is incidental: a waiter re-reads `self._entries` after acquiring
  the lock and finds the value the winner stored. There is no equivalent for failure, because
  failure stores nothing — so each queued waiter calls `refresh()` again (`:107`).

## Design

**One owner for in-flight state.** Locks are coordination state for *callers currently inside the
critical section*, not metadata about *entries*. Tying their removal to `_store` is the category
error that produces both leaks. Replace it with explicit acquire/release around the critical
section: a waiter count per key, incremented before awaiting the lock and decremented in a
`finally`; the last caller out drops the key's coordination state. Locks are then bounded by
concurrent callers, which is inherently bounded, and no eviction interaction remains — so the
lock-dropping branch in `_store` is deleted rather than patched. That is strictly simpler than the
code it replaces.

**Failure coalescing, symmetric with success.** A caller records a sequence number before queuing.
When an attempt fails, the cache records that failure's outcome against the key with the next
sequence number. A waiter that acquires the lock and sees a recorded failure newer than the sequence
it observed on entry knows the failure happened *while it was waiting* — so it is a genuine
single-flight loser and reuses that outcome instead of re-dialling. A caller that arrives later (its
observed sequence is at or after the record) is a new attempt and does dial. This deliberately does
NOT add a negative-caching TTL: the record lives only as long as the in-flight batch, so it cannot
suppress a legitimate retry after the outage clears.

**Why the recorded outcome is safe to reuse.** `_on_refresh_error` derives its outcome from the
entry table and the clock, both unchanged during the wait (the winner held the lock throughout and
stored nothing). Reusing it is therefore equal to recomputing it, minus the network call.

Freshness labelling, TTL, stale window, revision isolation and the LRU bound are untouched.

## Planned changes

Source (1):
- `src/aigateway/core/parameter_discovery_cache.py` — `_acquire`/`_release` waiter-counted
  coordination state; per-key failure record consulted by single-flight losers; delete the
  lock-dropping branch in `_store`.

Tests (1, appends):
- `tests/unit/core/test_parameter_discovery_cache.py` — cold-failure lock bound, in-flight-eviction
  lock bound, failed single-flight coalescing, and the negative case (a later caller still retries).

No schema, model, ORM or migration change.

## Test plan (RED first)

- **Cold-failure bound:** 100 distinct keys each failing cold → 0 entries AND 0 residual locks.
  (Today: 100 locks.)
- **In-flight eviction bound:** `max_entries=1`, one key mid-refresh while another key stores and
  evicts it → after both settle, no residual coordination state. (Today: both locks retained.)
- **Failed single-flight coalesces:** two concurrent callers on one key, the winner's refresh fails
  → `refresh` invoked exactly once, both receive the same degraded outcome. (Today: 2 invocations.)
- **A later caller still retries:** after the failed batch fully settles, a fresh call dials again —
  proving the record is in-flight scope, not a negative cache.
- **Stale-path coalescing keeps its label:** losers on a failure inside the stale window receive
  `stale` with the last good value, not `degraded`.

Prior tests: none modified. Verified no existing test touches `_locks` or asserts an invocation
count on the failure path beyond a single caller.

## Acceptance

- Residual coordination state is zero once no caller is inside `get_or_refresh`, on every path.
- An outage costs one upstream attempt per batch, not one per waiter.
- All ten existing cache tests pass unmodified. Full aigateway gate green.

## Outcome

**Status: DONE.** Committed as `9f1c7995` —
`fix(aigateway): bound discovery cache coordination state by concurrent callers`.

### Actual changes (match plan)

Source (1): `core/parameter_discovery_cache.py` (136 → 208)
- New `_InFlight` dataclass holding the per-key `lock`, `waiters` refcount, `attempts` counter and
  `failure` record, with a `WHY:` naming the category error it replaces (caller state vs entry
  state).
- `_enter`/`_leave` own its lifecycle; `_leave` deletes the batch when the last caller exits.
  An implementation note records why they are safe without a lock of their own — no `await` between the
  lookup and the counter change, so the event loop cannot interleave.
- `get_or_refresh` reads `attempts` **before** queuing and, after acquiring the lock, reuses a
  recorded failure only when `attempts` moved while it waited. Wrapped in `try/finally`.
- `_store` lost its lock-reconciliation branch entirely (net simplification — 9 lines to 6).
- New public `inflight_key_count` property so the bound is assertable without touching internals.

Tests (1, pure append): `test_parameter_discovery_cache.py` (188 → 310), 6 new tests.

### Quality gate

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only` from the repo root —
**GREEN on attempt 1**: ruff check ✓ · ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ ·
pytest --cov ≥80% ✓.

### Verification beyond the gate

RED was specific and matched the finding: `assert 3 == 1` on the coalescing test (three waiters, three
upstream dials), plus `AttributeError` on the three bound tests. After the change all 16 tests in the
file pass, the 10 pre-existing ones unmodified.

A second defect surfaced while reproducing, beyond the two named: `_store` dropped locks only for
**evicted** keys, so every key that was stored and stayed resident also kept its lock forever. The
simplest RED case is a single successful call leaving one residual lock —
`test_successful_refresh_leaves_no_coordination_state` pins it.

Append-only honesty: `git diff HEAD -- apps/aigateway/tests | grep '^-'` → empty. All 22 deleted
lines are source.

### Deviations

1. **A public property was added** (`inflight_key_count`) rather than testing via `cache._locks`.
   A memory bound that can only be checked by reaching into privates is not really guaranteed; this
   also gives operations a real diagnostic. It is the only new public surface.
2. **No negative-cache TTL.** The shared failure record dies with the batch. A TTL would have been
   the "obvious" design but introduces a liveness hazard: under continuous traffic a pinned outage
   verdict could outlive the outage. `test_a_caller_arriving_after_a_failed_batch_retries` pins the
   chosen semantics.
3. **Commit:** `9f1c7995`; `Refs: OME-603, OME-479`.
