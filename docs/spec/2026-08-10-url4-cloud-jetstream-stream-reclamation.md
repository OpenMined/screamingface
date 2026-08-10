# url4-cloud — JetStream stream reclamation

Status: approved (owner, 2026-08-10) · Landing: `apps/url4-cloud` · No Linear item (owner
directive: spec → implement only)

## 1. Problem

Production fails every run with:

```
nats.js.errors.ServerError: code=500 err_code=10047
description='insufficient storage resources available'
```

`err_code=10047` is `JSInsufficientResourcesErr`. JetStream refuses to **place a new stream**
because committed storage reservations already fill the store. It is not a per-message limit.

The cause is a leak of stream *objects*, one per run:

1. `ensure_stream()` creates one stream per topic with `max_bytes = 256 MiB`
   (`adapters/jetstream.py:27`). JetStream **reserves** that amount at creation. An empty
   stream still holds the full 256 MiB.
2. The NATS PVC is `10Gi`, so the ceiling is `10240 / 256` = **40 streams**. The 41st
   `add_stream` returns 10047.
3. `max_age` (24 h) expires **messages**, never the stream object. The invariant comment at
   `adapters/jetstream.py:20-23` claims it "reclaims the ones no client ever gets around to
   deleting" — that claim is **false** and is the root defect.
4. The only reclamation path is `DELETE /` → `delete_stream` (`rest/routes.py:485`), which
   requires a capability token. `JwtCodec.sign` sets `exp = iat + iat_window_s` = **60 s**
   (`auth/jwt.py:41-44`), and `POST /token` always mints a **fresh** topic
   (`rest/routes.py:321`), so a token can never be re-issued for an existing topic.
   **Any run longer than 60 s is structurally unable to delete its own stream.**
5. `except BadRequestError` (`adapters/jetstream.py:127`) does **not** catch this: `ServerError`
   (500) and `BadRequestError` (400) are siblings under `APIError`. The error escapes uncaught.

Failure is monotonic and total: past ~40 leaked runs every subsequent run fails.

## 2. Scope

In scope: stream reclamation, stream sizing, and error surfacing. Out of scope: the
shared-stream redesign (evaluated and deferred — it changes `sequence` semantics), token
lifetime, and the replay-window contract.

## 3. Design

### 3.1 Reclamation is the runner's job (owner decision)

The runner deletes its own stream at the end of its lifecycle. Reclamation is a deployment
concern, not a protocol one, so it lives in the runner's composition root
(`runner/main.py`) — **`packages/url4` is not modified**.

`delete_stream` is declared on `EventConsumer`, not `EventPublisher`
(`packages/url4/src/url4/streaming/interfaces/stream.py:35`), and the runner holds a
`JetStreamPublisher`. It is **not** promoted to `EventPublisher`: `EventStream` inherits
`(EventPublisher, EventConsumer)`, so a definition on `EventPublisher` would win the MRO and
silently replace `EventConsumer`'s purge-delegating default — breaking local-mode teardown.
The concrete `_JetStreamConnection` base already implements `delete_stream`, so the runner's
composition root calls it directly on the concrete type.

### 3.2 Grace delay before deletion

`delete_stream` destroys the stream *and its consumers*. Deleting immediately after the
terminal frame is published would race a client that has not drained yet, which loses the
terminal frame and hangs the client. The runner therefore waits
`URL4_RUNNER_STREAM_GRACE_S` (default **60 s**, matching `iat_window_s` — the widest window
in which any client can still be attached) after `lifecycle.run` returns, then deletes.

### 3.3 Lazy sweep backstop (crash-safety)

A `finally` block does not run on OOMKill, eviction, node loss, or `activeDeadlineSeconds`.
Those runs would leak exactly as today, so reclamation cannot rest on the runner alone.

Rather than a background reaper (rejected: needs a loop, leader election, and RBAC), the
sweep is **lazy** — it runs only when `ensure_stream` actually hits 10047, then retries once:

```
ensure_stream(topic):
    try: add_stream(...)
    except BadRequestError:  pass            # already exists
    except APIError as e:
        if e.err_code != 10047: raise
        swept = sweep_orphans()
        if swept == 0: raise                 # nothing reclaimable — surface it
        add_stream(...)                      # retry exactly once
```

A stream is an orphan when either holds:

- **Expired** — `state.messages == 0 and state.last_seq > 0`. Every message aged out, so
  nothing is replayable. `last_seq > 0` is load-bearing: a freshly created stream that has
  not been published to yet also has `messages == 0`, but `last_seq == 0`, so it is never
  swept out from under a starting run.
- **Terminated** — the last message decodes to `ai.url4.terminated` and its envelope `time`
  is older than the grace window. The run is definitively over.

- **Never started** — `messages == 0 and last_seq == 0`, `consumer_count == 0`, and
  `StreamInfo.created` older than `never_started_s` (30 min). This case was **missed in the
  first draft** and is the one that matters most: the control plane declares the stream when a
  client attaches, *before* the Job is scheduled, so an `ImagePullBackOff`, a quota rejection,
  or a crash during world resolution strands a stream that `max_age` can never reclaim (no
  messages to expire). Treating it as permanently-not-orphan left the sweep structurally unable
  to clear the outage it exists for.

`StreamState` exposes no timestamp — but `StreamInfo.created` does, and it is a **server-side**
value, so no runner clock is trusted. The earlier claim here that no timestamp was available at
all was wrong and produced the gap above.

The sweep costs one `streams_info()` plus at most one `get_last_msg` per candidate, and only
on the rare exhaustion path.

### 3.4 Sizing

`DEFAULT_STREAM_MAX_BYTES`: 256 MiB → **50 MB** (owner directive). Ceiling rises from 40 to
~200 concurrent runs.

**Correction.** An earlier draft justified this as "safe" because per-run frame counts are
bounded by the `_Bridge` caps. That is wrong: `_Bridge` bounds the *in-flight backlog*
(`queue_cap=1024`), not the cumulative frames a 16-hour run publishes. With `DiscardPolicy.OLD`,
a run exceeding `max_bytes` silently drops its **oldest** frames, and that threshold just fell
5×. A heavy-log run can therefore lose early frames, breaking replay from sequence 1. The trade
is still judged correct — 200 concurrent runs beats 40, and `result_cap` (1 MiB) bounds the one
frame most likely to be large — but it is a trade, not a free win, and log-heavy runs are the
exposure.

`max_age` stays at 24 h as a byte-level bound; it is explicitly *not* a reclamation mechanism,
and the false invariant comment is corrected.

### 3.5 Error surfacing

When the sweep cannot free space, 10047 must not escape as a raw 500 traceback:

- Control plane: RFC 9457 problem, **503** `insufficient stream storage`.
- Runner: the failure is already inside `lifecycle.run`'s outcome policy, which publishes
  `TerminatedEvent(status="failed")` — but only if the stream exists. When `ensure_stream`
  itself fails there is nowhere to publish, so the runner logs and exits non-zero rather than
  dying on an unhandled traceback.

## 4. Configuration

| Setting | Default | Notes |
|---|---|---|
| `DEFAULT_STREAM_MAX_BYTES` | 50 MB | was 256 MiB |
| `URL4_RUNNER_STREAM_GRACE_S` | 60 s | drain grace before self-delete |
| `DEFAULT_STREAM_MAX_AGE_S` | 86 400 s | unchanged; byte bound only |

## 5. Test plan

RED first, per `sdlc-python`.

1. `ensure_stream` sweeps and retries once on 10047; succeeds when the sweep frees a stream.
2. `ensure_stream` re-raises when the sweep frees nothing (no infinite retry).
3. `ensure_stream` still swallows `BadRequestError` (stream already exists).
4. **Regression:** a `ServerError(500, err_code=10047)` is not caught by the `BadRequestError`
   arm — pins the sibling-class bug that let this escape.
5. Orphan test: `messages == 0, last_seq > 0` → swept; `messages == 0, last_seq == 0` (fresh)
   → **not** swept.
6. Orphan test: last frame `ai.url4.terminated` older than grace → swept; newer → not swept.
7. Runner deletes its stream after `lifecycle.run` returns, and only after the grace delay.
8. Runner still deletes on a failed/timed-out run (the `finally` path).
9. `DEFAULT_STREAM_MAX_BYTES == 50 * 1000 * 1000` and is passed to `add_stream`.
10. Local mode (`InMemoryEventStream`) teardown is unchanged — guards the MRO trap in §3.1.

## 6. Operational note

The fix is not retroactive. Streams already stranded in prod must be cleared once:

```sh
nats stream ls --names | grep '^url4-cloud_' | xargs -n1 nats stream rm -f
```

After deploy the lazy sweep reclaims stranded streams on its own, but only once storage is
exhausted again — the manual pass restores headroom immediately.

## 7. Known residual risk

Runs killed before their `finally` block leak until the next exhaustion-triggered sweep.
This is accepted: the sweep bounds the leak's consequence (a run fails, sweeps, and
recovers) rather than eliminating the leak. The shared-stream redesign (one stream, subject
per run, `max_msgs_per_subject`) removes the failure mode entirely and remains the
recommended follow-up.
