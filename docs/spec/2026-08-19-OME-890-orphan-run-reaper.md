# OME-890 — Tie a run's lifetime to its audience

Status: approved (owner, 2026-08-19) · Stack: screamingface-engine

## 1. Problem

A run's lifetime is tied to nothing. The Engine asks "is anyone listening?" exactly once,
at the door:

| Fact | File | Consequence |
|---|---|---|
| The 428 gate is the only reader of `has_subscriber` | `rest/routes.py:138-145` | Audience is proved at schedule time, then never again |
| `registry.remove` is bare arithmetic — no callback, no event | `ws/registry.py:57-63` | Nothing reacts to "my last subscriber vanished" |
| The bridge's `_teardown` cancels the pump, reader, and writer — never the job | `ws/bridge.py:360-368` | A dead client's run keeps running |
| The only remaining clock is `job_deadline_s` | `config.py` (57600 s = 16 h) | An orphan spends for up to 16 h |

Cancellation today needs the client to still be alive to ask for it. The SDK sends an
in-band `ai.url4.stop` on interrupt, and the multi-candidate path adds a `DELETE /` sweep.
Neither runs when the process dies: `kill -9`, a Jupyter kernel restart, laptop sleep, a
network partition, or a single-candidate run whose stop frame never leaves.

Cost when this happens:

- **Money.** A HealthBench Fusion run spends at roughly $6.5/hour scale. Sixteen hours is
  about $104 with nobody receiving the result.
- **Capacity.** The orphan holds one of `local_max_concurrent_runs` slots and keeps
  saturating the gateway's per-provider slots. Four orphaned Evaluations at the client's
  `_MAX_CANDIDATES_IN_FLIGHT = 8` fill all 32 local slots, which is what wedged a stuck
  `limit=1` eval until `just stack-down && just stack-up`.

## 2. The signal already exists, and it is prompt

`registry.remove` runs in a `finally` and is documented as firing on every disconnect
flavour (`ws/endpoint.py:103-107`). The open question was whether it fires *promptly*. The
WS heartbeat cannot help: it is outbound-only (`ws/bridge.py:334-341`), and the inbound
read has no timeout.

Uvicorn's own RFC 6455 ping answers it. Verified on uvicorn 0.52.1:

```
ws = auto    ws_ping_interval = 20.0    ws_ping_timeout = 20.0
```

`cli.py:44` passes no `ws_*` override, so both serve modes take these defaults. A
partitioned or sleeping peer is pinged, fails to pong, and uvicorn closes the socket within
about 40 s. That closes `registry.remove`.

**This is a load-bearing assumption.** Without WS ping, a dead peer would be detected only
by TCP retransmission timeout (roughly 15–30 minutes with default Linux settings), and the
reaper would barely help the ticket's headline cases. With it, total exposure is
`≤40 s + grace`.

At a 120 s grace that is about 160 s against 57600 s today — a **~360× reduction**, or
about $0.29 per orphan instead of about $104.

## 3. Risk model

This drives every decision below.

| # | Risk | Severity | Source |
|---|---|---|---|
| **R1** | **A healthy, actively-watched run is killed** | Critical | Wrong audience source; lost disarm; multi-replica |
| R2 | The reaper never fires — the issue is unfixed | High | Loop task dies; arm lost; `exists()` wrong |
| R3 | A second terminal frame corrupts the stream contract | High | Stop on an already-finished run |
| R4 | The reaper dies silently — an invisible regression to 16 h | Medium | Unhandled exception in the loop |
| R5 | Reconnect/resume regresses | Medium | Disarm not wired to `add` |
| R6 | Task leak or a hung shutdown | Medium | Fire-and-forget task |

R1 is not symmetric with the others. Failing to reap costs money. Wrongly reaping destroys
a researcher's multi-hour evaluation. **The design is biased toward not reaping.**

### 3.1 The R1 trap, and the precedent that settles it

`DenyAllGate.has_subscriber` returns `False` for every topic (`rest/interest.py:17-25`), and
the unit tests inject `FixedGate(False)` (`tests/unit/_fakes.py:164-169`). A reaper that
asked `app.state.interest` would read "nobody is listening" for every topic and **reap the
whole fleet** one grace window after boot.

The codebase already ruled on this exact distinction, at `rest/routes.py:82-83`:

> `registry` and not `interest`: the subscriber gate is a DI seam tests replace with a fixed
> answer, while the session state is the real registry the WS transport writes […]

**Decision.** The reaper asks the real `ConnectionRegistry`. It never reads the
`SubscriberGate` seam. The same answer that is harmless as an admission gate — a refused
start is visible and annoying — is destructive as a reap input.

## 4. Design

### 4.1 Shape: edge-armed, tick-verified

```
                 registry.add 0→1                    registry.remove 1→0
                 (endpoint.py:87)                    (endpoint.py:107)
                        │                                    │
                        ▼                                    ▼
   ┌──────────────┐  disarm   ┌──────────────┐   arm    ┌──────────────┐
   │   WATCHED    │◄──────────│  (no entry)  │─────────►│    ARMED     │
   │ audience > 0 │           │              │          │ deadline =   │
   └──────────────┘           └──────────────┘          │ mono + grace │
                                     ▲                  └──────┬───────┘
                                     │                         │ sweep(): mono ≥ deadline
                       drop (nothing to do)                    ▼
                                     │            ┌────────────────────────┐
                                     └────────────│ claim → re-verify:     │
                                                  │  audience back? → drop │
                                                  │  job gone?      → drop │
                                                  │  else → stop(topic)    │
                                                  └────────────────────────┘
```

The audience transition arms and disarms. One background loop verifies and stops.

### 4.2 Decisions, with the alternative each one rejected

**D1 — Edge-arm from the registry, not a periodic sweep over all live jobs.**
A level-triggered sweeper must enumerate live runs. The `JobRunner` port cannot: it exposes
`schedule` / `stop` / `exists` / `status` / `aclose`. Edge-arming needs **no port change**
and **no `routes.py` change**, because the registry already knows exactly when the audience
empties. What pure-level would buy is surviving a control-plane restart; see §6.2.

**D2 — One sweep loop with a deadline map, not a per-topic `sleep(grace)` timer task.**
Per-topic timers need cancel-and-replace on every reconnect (a race per flap), N tasks per
orphan burst, and they force real sleeps into tests. One loop makes a flap a plain dict
assignment, keeps a single owned task, and lets `sweep()` run directly against an injected
clock. Cost: reap latency is `grace` to `grace + tick` rather than exactly `grace`. For a
cost-control mechanism that is free.

**D3 — Arm unconditionally; check `exists()` only at expiry.**
A client can die *during* `_schedule`'s awaits, before the job is registered. Arming only
when a job already exists would drop that edge and leak the orphan forever. Arming
unconditionally is safe because the job appears within milliseconds and the deadline is
120 s out.

**D4 — Claim before verifying.**
`sweep()` pops the topic from the deadline map *before* any `await`. On a single-threaded
loop that makes "this topic is mine to decide" one atomic step. A reconnect that lands later
finds nothing armed, which is the correct end state either way.

**D5 — Monotonic clock.**
Deadlines use `time.monotonic`. Wall-clock would let an NTP step or a suspend jump reap a
live run. This matches `ws/bridge.py:193`, which already uses `time.monotonic()` for
duration and keeps `app.state.clock` for wire timestamps.

**D6 — Stop only. Do not purge the stream.**
`DELETE /` stops and purges. The reaper only stops. Existing stream reclamation already
covers the rest (`runner`'s `run_and_reclaim`, plus the JetStream sweep at
`adapters/jetstream.py:172-207`). Smallest in-contract change.

**D7 — Reuse `Terminated(stopped)`; no protocol change.**
The reap is indistinguishable on the wire from a client-requested stop. This keeps the
protocol, the AsyncAPI document, and the SDK untouched. The *reason* lives in the log line
and the metric. If a reconnecting client ever needs to tell them apart, that is a protocol
change and a separate issue.

**D8 — Retry `stop()` without bound.**
A transient k8s error must not hand the run back to the 16 h ceiling. On failure the topic
is re-armed one tick out. The per-tick warning log is the operator signal. Giving up would
cost real money.

**D9 — `reaper` joins `CONTROL_PLANE` in the layering gate.**
`check_layering.py` treats any module in neither half as a *shared leaf* that both halves
may import. A new top-level `reaper.py` would silently become one, which would let
`runner/*` import the control plane's reaper. Naming it in `CONTROL_PLANE` makes that
import a gate failure, which is correct.

### 4.3 Race analysis

Model: a single-threaded asyncio loop. No data races are possible. Logical races across
`await` points are the whole risk surface. `registry.add` / `remove` and the two transition
calls contain no awaits, so each is atomic by construction.

| Race | Outcome | Why it is safe |
|---|---|---|
| A reconnect lands during the sweep that expires the topic | No reap | Claim-then-verify (D4) re-checks `has_subscriber` |
| A reconnect lands after `stop()` is dispatched | Run stops; client sees `Terminated(stopped)` | Accepted. The window is sub-millisecond after a 120 s wait; committing beats an unbounded abort protocol |
| The run finishes normally, then the client disconnects | No reap | `exists()` is False at expiry, **and** `stop()` on a done task is a documented no-op — R3 is closed twice |
| Explicit `ai.url4.stop` or `DELETE /`, then a disconnect | Unchanged | Same `exists()` guard; the reaper adds nothing |
| Flap: leave / arrive / leave / arrive × N | One entry, last arm wins | Dict assignment; no tasks to cancel, so no cancel-replace race |
| The client dies mid-`_schedule`, before the job is registered | Reaped correctly | D3 |
| Two watchers, one leaves | No arm | `remove` signals only at `<= 0` |
| A sync-hold run whose WS dies | Reaped | The same dead client holds both, and `sync_max_wait_s`=30 < grace=120, so the hold converts to 202 first |
| App shutdown mid-sweep | Clean | `cancel()` + `suppress(CancelledError)` + `await`, matching `ws/bridge.py::_teardown` |

Patterns applied: **confinement** (all reaper state is owned by one object on one loop, so
no lock is needed and none is added), **structured ownership** (the task is held and awaited
by the app, never fire-and-forget), **claim-before-act** to collapse a check-then-act TOCTOU
into one step, and **idempotency** at the `stop()` boundary so retries are free.

## 5. Configuration

```
orphan_grace_s: float = 120.0     # URL4_CLOUD_ORPHAN_GRACE_S; ge=0; 0 disables
```

Helm: `config.orphanGraceS` → ConfigMap. Tick is derived as
`max(1.0, grace_s / 8)`, overridable for tests, so operators get one knob.

Values below about 60 s are not recommended. Uvicorn needs up to
`ws_ping_interval + ws_ping_timeout` (about 40 s) to notice a partitioned peer, so a shorter
window reaps mostly on clean closes and starts risking live runs on slow reconnects.

Observability: a reaped-runs counter and an armed-topics gauge on the existing
`app.state.metrics`. A gauge that stays non-zero is the "reaper is stuck" alarm.

## 6. Residual risk — what this does not close

1. **Multi-replica becomes dangerous, not merely annoying.** Today a second replica causes
   spurious 428s, which are visible. With the reaper it would kill live runs, silently. The
   chart already pins `replicaCount: 1`, and the fix when that changes is the shared
   `SubscriberGate` over NATS consumer interest that the issue's own comment describes. A
   startup log line states the single-replica assumption so it is discoverable at runtime,
   not only in a chart comment.
2. **A control-plane restart in k8s mode.** Jobs survive; the registry does not. Those
   orphans cannot be reaped and fall back to `job_deadline_s`. Fixing this needs job
   enumeration, which is a port addition — the same follow-up bucket as item 1.
3. **In-flight gateway calls still bill.** `stop()` ends the run, but calls already
   dispatched complete. That is OME-886's scope, as the issue states.
4. **The reap is indistinguishable on the wire** from a client-requested stop (D7).
5. **Uvicorn WS ping must stay enabled** (§2). A comment at `cli.py:44` records this so
   nobody "cleans up" the defaults and reopens the partition path.

## 7. Out of scope

- Gateway client-disconnect awareness — belongs with OME-886's admission/execution bounding.
- The SDK's single-candidate `DELETE /` fallback — the reaper closes every orphan path
  including that one, so the fallback is optional cleanup, not part of this fix.
- Multi-replica shared interest (item 1 above).
