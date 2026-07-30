---
ticket: OME-604
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-604 — Hard byte and time bounds in the httpx discovery adapter

## Intent

`HttpxDiscoveryClient.get` advertises `max_bytes` and `timeout_s` as safety bounds. Neither is
enforced as one. Make the adapter itself the place both are guaranteed.

## Evidence

- `parameter_discovery.py:161-165` — `chunks.append(chunk)` runs **before** `if total > max_bytes`,
  so the oversizing chunk is retained. On overflow the loop `break`s and returns a truncated body;
  the adapter's own limit never rejects anything, it only stops reading.
- `:161` reads `aiter_bytes()`, which yields **decoded** content, and httpx 0.28.1 advertises
  `gzip, deflate, br, zstd` by default. `max_bytes` therefore measures post-expansion size, and the
  decoder expands inside its own buffers before the loop sees a byte.
- `:155` — `httpx.Timeout(timeout_s)` sets connect/read/write/pool **intervals**. Each resets on
  activity, so a slow-drip source never trips it.
- Installed-source check (httpx 0.28.1, `Response.aiter_raw` + `_decoders.ByteChunker`):
  `ByteChunker.decode` writes the whole incoming read into `self._buffer` before splitting, so
  passing `chunk_size` bounds only the **yielded** chunk, not memory — it would add a copy and buy
  nothing. With `chunk_size=None` the chunker returns `[content]` untouched. **Therefore: do not
  pass a chunk size**; rely on the transport's own read sizing and never retain past the cap.
- `tests/unit/core/test_parameter_discovery_transport.py` covers oversized bodies against a *fake*
  client, so it exercises `fetch_discovery_json`'s re-measurement and never reaches this adapter.

## Design

**One accounting unit: bytes on the wire.** Read `aiter_raw()` (undecoded) and request
`Accept-Encoding: identity`. If a source compresses anyway, fail with a sanitized reason rather than
decode it. That makes wire bytes == buffered bytes == parsed bytes — one number for `max_bytes` — and
removes the decompression-bomb class outright instead of trying to bound it.

The cost is real and small: a ~1 MB public catalog transfers uncompressed once per cache TTL, on a
path that is explicitly off the dispatch critical path. The benefit is that the limit stops depending
on a response header the source controls.

**Check before retain.** Add the chunk's length to the running total first; if it would exceed the
cap, raise `DiscoveryError("oversized")` and abandon the stream. The buffer provably never exceeds
`max_bytes`. Returning a truncated body — today's behaviour — leaves a downstream re-measure to
notice, which works only because the break happens strictly *past* the cap; that is correctness by
luck, and it disappears the moment someone "tidies" the comparison to `>=`.

**A real deadline.** Wrap the whole operation in `asyncio.timeout(timeout_s)` and keep httpx's
per-interval timeout underneath as a subordinate bound. One knob, honestly total. The outer context
is placed OUTSIDE the `except httpx.HTTPError` handler so a deadline is reported as `timeout` rather
than being reclassified by httpx's own error translation.

`DiscoveryError` reason codes stay sanitized (fixed strings, no upstream text). Two new codes —
`unsupported_encoding`, `timeout` — are internal today: the only consumer maps any `DiscoveryError`
to "discovery observed nothing".

**Validation note.** The identity-only encoding decision was validated against the installed
httpx 0.28.1 source.

## Planned changes

Source (1):
- `src/aigateway/core/parameter_discovery.py` — `HttpxDiscoveryClient.get` split into an outer
  deadline wrapper and the bounded read; identity encoding requested and enforced; oversize raises.

Tests (1, appends):
- `tests/unit/core/test_parameter_discovery_httpx.py` — against the real adapter via
  `httpx.MockTransport`.

No schema, model, ORM or migration change.

## Test plan (RED first)

- **Oversized body is rejected, not truncated:** a body larger than `max_bytes` → `DiscoveryError`
  with reason `oversized`, and no `RawResponse` returned. (Today: a truncated `RawResponse`.)
- **A body exactly at the cap is accepted** — the boundary is `>`, not `>=`.
- **Identity encoding is requested:** the outgoing request carries `accept-encoding: identity`.
- **A compressed response is refused:** `content-encoding: gzip` → `unsupported_encoding`, and the
  body is never decoded.
- **Slow-drip stream hits the total deadline:** a stream emitting small chunks indefinitely →
  `DiscoveryError("timeout")`, with measured elapsed time bounded well under the test ceiling.
  (Today: runs unbounded.)

Prior tests: none modified. The three existing adapter tests (happy path, redirect not followed,
sanitized transport error) must keep passing unchanged.

## Acceptance

- The adapter's buffer cannot exceed `max_bytes` on any path.
- `max_bytes` has one documented meaning: bytes on the wire.
- A fetch cannot outlive `timeout_s` regardless of upstream chunk cadence.
- Full aigateway gate green.

## Outcome

**Status: DONE.** Committed as `5d41561b` —
`fix(aigateway): enforce the discovery max_bytes and timeout bounds`.

### Actual changes

Source (1): `core/parameter_discovery.py` (173 → 231)
- `_IDENTITY_ENCODING` module constant with a `WHY:` for the accounting policy and its cost.
- `get` is now the deadline wrapper only (`asyncio.timeout` → `DiscoveryError("timeout")`), with a
  `WHY:` explaining that httpx's `Timeout` is a set of per-interval budgets that a busy stream
  resets forever, and why the context sits outside the httpx handler.
- `_read_bounded` holds the former httpx body, now sending `accept-encoding: identity`.
- `_bounded_body` refuses a non-identity `content-encoding`, then counts **before** retaining and
  raises `oversized` instead of returning a truncated body.
- Class docstring gained the "enforces both advertised bounds" invariant.

Tests (1, pure append): `test_parameter_discovery_httpx.py` (62 → 156), 5 new tests.

### Quality gate

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only` from the repo root —
**GREEN on attempt 1**: ruff check ✓ · ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ ·
pytest --cov ≥80% ✓.

### Verification beyond the gate

RED was real for 3 of 5 (`oversized`, identity request, compressed refusal all "DID NOT RAISE" /
wrong header). The slow-drip test could not even be run against the old code — it does not
terminate, which is the finding stated as an experiment. The at-the-cap boundary test passed before
and after; it exists to pin `>` against a future "tidy-up" to `>=`.

Append-only honesty: `git diff HEAD -- apps/aigateway/tests | grep '^-'` (run from the repo root)
→ empty across both this unit and OME-603; all 33 deleted lines are source.

### Deviations

1. **`aiter_bytes` retained instead of switching to `aiter_raw`.** The plan called for `aiter_raw`.
   It broke the two pre-existing adapter tests with `httpx.StreamConsumed`: httpx marks an
   eagerly-materialised response's stream consumed at construction, and `aiter_raw` has no
   `_content` fast path while `aiter_bytes` does. Rewriting those prior tests to force streaming
   doubles would have been changing tests to fit the code. Re-deriving instead: the expansion path
   is closed by the **header refusal**, so once a non-identity encoding is rejected the remaining
   decoder is the identity decoder and `aiter_bytes` yields precisely the wire bytes. The guarantee
   is unchanged, the prior tests are untouched, and the reasoning is recorded at the call site.
2. **Two new reason codes** (`unsupported_encoding`, `timeout`). Internal today — the only consumer
   maps any `DiscoveryError` to "observed nothing" — but they keep the diagnostic distinct.
3. **Dependency evidence:** the identity-encoding decision was checked against installed httpx
   0.28.1 source.
4. **Commit:** `5d41561b`; `Refs: OME-604, OME-479`.
