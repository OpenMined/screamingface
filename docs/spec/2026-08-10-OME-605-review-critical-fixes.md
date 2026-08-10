---
ticket: OME-605
status: approved
created: 2026-08-10
stack: screamingface
---

# OME-605 — Critical fixes from the branch review

## Why this exists

The `OME-605-screamingface-client` branch went through a multi-agent code review before
merge (PR #539). The review found three Critical defects and one missing safety mechanism.
This document is the normative contract for those four fixes only. It does not change the
public interface of the package, and it does not address the Important or Minor findings
from the same review — those stay as separate work.

All four defects share one property: each one either spends money incorrectly or throws
away work the user has already paid for. That is why they block the merge.

## Decisions taken before implementation

Three forks were resolved by the owner on 2026-08-10:

1. **Async stop scope** — implement the small symmetric fix that mirrors the existing
   synchronous behaviour. Relocating the active-run registry so that each Evaluation owns
   its own (which would additionally fix the cross-Evaluation blast radius, the
   single-Candidate gap, and the mint window) is deferred to separate work.
2. **Access replay** — implement the status gate **and** the explicit replay-safety
   marking. The gate alone leaves the safety property resting on Cloudflare's choice of
   status codes.
3. **Existing test files** — additive edits to existing test doubles are permitted for
   this unit of work, so that a new Protocol member does not fail the type gate.

One further decision was taken during specification: the Access challenge status set stays
at `{302, 401, 403}`. Cloudflare Access does not challenge with 301/303/307/308, and
widening the set adds false-positive surface to a change whose purpose is to narrow.

---

## Fix 1 — Cloudflare Access challenge detection and request replay

### Defect

`_access_audience` in `_engine/access_contract.py` reports an Access audience whenever a
response carries a `cf-access-aud` header, or a `Location` header with exactly one `kid`
query parameter. It never inspects the status code.

`sync_auth_flow` and `async_auth_flow` in `_engine/auth.py` treat any non-`None` audience
as a login challenge: they perform an interactive browser login and then re-send the
original request. The Run start is `GET /?q=<url4>` with `Prefer: respond-async`, whose
success is a **202 carrying a `Location` header**. A success can therefore be read as a
challenge, and a non-idempotent start request is re-sent.

The WebSocket sibling, `_is_access_websocket_rejection` in `_engine/transport.py`, already
gates on status. The three call sites disagree.

### Confirmed blast radius

`apps/url4-cloud/src/url4_cloud/rest/routes.py` schedules one job per topic and answers a
duplicate start with 409 Conflict, so a replay fails the Run rather than billing it twice.
The defect is a contract defect, not a live double-spend. A client library must not depend
on a separate service refusing duplicates for its own safety property.

### Required behaviour

1. One predicate decides "is this response an Access challenge, and what is its audience".
   It takes a status code and a header mapping, so that both `httpx.Response` and the
   `websockets` response satisfy it. It returns the validated audience or `None`.
2. A status outside `{302, 401, 403}` is never a challenge, whatever headers it carries.
3. The predicate backs all three call sites: both `httpx` auth flows and the WebSocket
   rejection test. The WebSocket path additionally gains the audience-format validation it
   did not have, and loses the inconsistency where it accepted a `Location` carrying two
   `kid` parameters while the HTTP path required exactly one.
4. A request is re-sent after a successful login **only** if the caller marked it as safe
   to repeat. The marking is per-request and default-deny.
   - Replay-safe: `POST /token` (mint) and `DELETE /` (stop).
   - Not replay-safe: `GET /?q=` (start).
   - An unmarked request that meets a genuine challenge completes the login and then
     raises a retryable `AuthenticationError` with code `access_reauthenticated`, so the
     caller reissues deliberately. The next request already carries the token.
5. `_start_sync` and `_start_async` stop re-issuing the start request once the response is
   not the attachment-registration problem they retry on. Today the loop runs to
   exhaustion on any other non-202, re-sending a non-idempotent start up to seven times.

### Out of scope

Whether a real Cloudflare edge ever stamps `cf-access-aud` on a 2xx is unverified. The
tests are contract tests of the predicate, not reproductions of a field incident, and must
say so.

---

## Fix 2 — Unsequenced advisory CloudEvents

### Defect

`_RunState.accept` in `_engine/contract.py` routes only `ai.url4.heartbeat` and
`ai.url4.error` to the unsequenced path. Every other type goes through `_sequence`, which
raises `ExecutionError` unless `sequencetype == "Integer"` and `sequence` is a positive
digit string.

`url4-cloud` injects advisory notices as `ai.url4.log` out of band, from `ws/bridge.py` and
`rest/routes.py` via `notices.warn`. These bypass the broker sequencer, so
`CloudEvent.sequence` and `sequencetype` are serialised as explicit `null`. Such a frame
aborts a paid Run. The REST notice is queued before the Run is scheduled, so it can be the
first frame the Client ever sees.

### Required behaviour

1. The discriminator is the presence of `sequence` **alone**. `sequencetype` is a type
   annotation for `sequence`; with no `sequence` it annotates nothing.
   - INVARIANT: this is load-bearing. An existing test removes `sequencetype` from a
     *sequenced* `started` frame and requires it to still raise. A both-fields
     discriminator would silently reclassify that frame as advisory and break it.
2. `ai.url4.heartbeat` and `ai.url4.error` remain always-unsequenced. `ai.url4.log` joins
   them **only** when it carries no sequence. A log with a sequence keeps today's path.
3. No other type may travel unsequenced.
   - INVARIANT: only frames that mutate no `_RunState` may arrive unsequenced. Gap
     detection, event-id de-duplication, and replay ordering all live on the sequenced
     path. An unsequenced `terminated` would build an outcome from an unverified stream; an
     unsequenced `cost.usage` would corrupt the billing total in the user's Report.
4. An unsequenced frame is still fully validated — its data object, its severity, its
   attributes, and its run subject. Dropped from the Event stream is not unvalidated.
5. The notice reaches a human. It cannot become a public `Event`, because `Event.sequence`
   is a mandatory positive integer and inventing one would pollute replay order. It is
   written to the module logger instead. `ai.url4.error` gains the same treatment: it is
   validated and discarded today, which hides server nacks.

### Known limitation

Discriminating on the absence of a field is a tolerant-reader shim. "Out of band by
design" and "the broker dropped the sequence" are indistinguishable on the wire. The
durable fix is a distinct server-side CloudEvent type for advisory notices, which is
separate work on `url4-cloud`.

---

## Fix 3 — Candidate references in source position

### Defect

`_text_references` in `_evaluation/linking.py` collects references from `Text` nodes and
raw `str` dataclass fields. A reference in **source position** parses to
`VarRef(name='candidate', path=())`: the `$` sigil is stripped and the name is a bare
string the `\$candidate` pattern can never match.

- A total miss rejects a valid Benchmark with `Benchmark URL4 does not invoke the
  Candidate`.
- A partial miss is worse. A Benchmark naming one member in a position the walker sees and
  another in a position it does not passes the arity check and emits an expression
  containing an unresolved `$candidate_member_N`, which fails only once the paid Run is
  underway.
- The arity message is actively misleading in that case: it reports the count the walker
  found, so it blames the user's Fusion for the walker's blindness.

### Required behaviour

1. `_text_references` recognises `VarRef`, contributing `"$" + name` to the same existing
   matcher, and continues to recurse into `path`.
   - `path` segments are field selectors on the resolved value, never references, so they
     must not be joined into the name.
   - The existing false-positive guard must survive: `$candidate_result` is plumbing, not
     an invocation.
2. The walker also recurses into mappings. `Source.weight` and `Source.budgets` may hold a
   `dict`, which today halts the walk.
3. `$$` is an escape for a literal `$`, so an escaped `$$candidate` is not a reference.
   The matcher must not treat it as one — `_template_literal` relies on that escape to keep
   user-facing member names literal.
4. After rendering, the linked artifact is checked for any `$candidate*` reference that no
   emitted binding resolves. An unresolved reference raises `PlanningError` with code
   `candidate_shape_mismatch`.
   - INVARIANT: this is the load-bearing guard. `_requirements` reasons over the parsed
     tree, where a reference has several shapes and the node set can change upstream.
     `render` collapses them all into one surface form, so the check is
     representation-independent and closes the whole bug class rather than one instance of
     it. It converts a mid-Run failure into a plan-time failure.

---

## Fix 4 — Asynchronous cancellation cannot stop paid Runs

### Defect

`SyncRunTransport` declares `cancel_active`; `AsyncRunTransport` does not.
`AsyncUrl4CloudTransport` keeps no registry of active capabilities and has no `DELETE /`
fallback. On asynchronous interruption the only stop attempt is the in-band
`ai.url4.stop` frame sent from inside `_run_connected`, which is already inside a cancelled
task and cannot work when the socket is what failed. The paid Run is orphaned.

Measured before the fix, with two Candidates in flight: the synchronous path issues two
`DELETE`s; the asynchronous path issues none.

### Required behaviour

1. `AsyncUrl4CloudTransport` registers each minted capability and discards it on exit,
   mirroring the synchronous transport.
   - The registry is a plain set with no lock. One transport instance is driven by one
     event loop, `httpx.AsyncClient` is loop-bound after first use, and no `await` sits
     between any read and write of the set. A lock would introduce suspension points into
     a region that is currently atomic. The synchronous twin keeps its `threading.Lock`,
     because a thread pool genuinely drives it. The asymmetry is deliberate and documented.
2. `AsyncRunTransport` gains `cancel_active`. `_run_candidates_async` calls it from its
   interruption handler.
3. **Ordering is load-bearing.** The sweep runs **before** the sibling tasks are cancelled,
   exactly as the synchronous path already does. Each Run discards its own capability on
   the way out, so cancelling first empties the registry and makes the fallback a
   guaranteed no-op.
4. `CancelledError` raised while stopping is never swallowed. A stop failure is recorded as
   a note on the original exception, as the synchronous path already does.
5. The stop request carries a short timeout of its own, so an interruption cannot block for
   the full 30-second client timeout per orphaned capability.
6. The stop is idempotent at the call site. With the in-band stop frequently succeeding
   first, the `DELETE` often arrives at an already-finished Run. A 404, 409, or 410 answer
   is success, not an error to report.

### Explicitly not in this unit of work

- The registry stays on the transport, so two concurrent Evaluations sharing one Client
  still stop each other's Runs.
- The `len(candidates) == 1` short circuit in both runners still bypasses the handler
  entirely, in the synchronous path as well as the asynchronous one.

Both are real and were measured. They are deferred by decision 1 above and must be filed as
follow-up work rather than forgotten.

---

## Verification

- Every fix is driven by a test that fails first for the stated reason.
- No existing assertion is weakened, deleted, or skipped. Additive stubs on existing test
  doubles are permitted by decision 3, so that a new Protocol member does not fail the type
  gate.
- The fake Engine in `tests/protocol_server.py` reproduces the real wire shape. The
  advisory notice carries its sequence keys present and null, because that is what
  `url4.streaming.codec.encode` emits — not omitted, which is what a hand-written fixture
  would assume.
- Gates: `uv run .claude/scripts/run_gates.py screamingface` — ruff check, ruff format,
  pyright, pytest with a 95% coverage floor, notebook determinism, build, distribution
  check.
