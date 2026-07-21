---
title: url4 Cloud Runner — technical specification (apps/runner, v1)
status: proposed — design validated by a 6-lens adversarial review (2026-07-15); implementation not started
created: 2026-07-15
author: Claude (Opus 4.8) + Sergey
ticket: OME-443
related:
  - https://linear.app/openmined/issue/OME-443/url4-cloud-runner-distributed-long-running-execution-service-epic
  - docs/plan/2026-07-15-url4-cloud-runner.md
  - .claude/skills/url4-engine/SKILL.md (execution & telemetry doctrine — PROPOSED)
  - packages/url4/ (the in-process engine this service wraps)
---

# url4 Cloud Runner — technical specification (v1)

## 0. Status
Proposed. The design was hardened by a 6-lens adversarial validation (distribution, liveness, security, docker↔k8s parity, doctrine conformance, hexagonal/repo-fit) that produced 5 must-fix + 12 should-fix corrections, all folded in below. Owner-approved forks are recorded in §14. Implementation starts per the plan only on explicit approval.

## 1. Purpose & scope
### 1.1 What it is
A cloud service that executes **url4 ensemble DAGs as long-running (>15 min) distributed jobs**. It wraps the existing single-process url4 SDK `Executor` and adds the distributed machinery the SDK deliberately lacks: a REST control plane, session/node state, a container job substrate, a durable event bus, session tokens, liveness, and an owned-internal vs external node distinction.

### 1.2 What it provides
- **Control plane** (`apps/runner`, FastAPI, port 9107): schedule / execute / stop / status over REST; mints session tokens + subject-scoped NATS credentials; hosts the liveness reaper.
- **Worker** (container image): runs the url4 `Executor` over one node subtree in-process; publishes telemetry to NATS; consumes stop; heartbeats.
- **`JobRunner` port** with **Docker** and **k8s-`Job`** adapters (one interface, >15 min, run-to-completion).
- **NATS JetStream**: durable, replayable event log + control channel; clients consume events over NATS-over-WebSocket directly.
- **Postgres** (Tortoise): session/node state + terminal results.

### 1.3 Non-goals (v1)
Distributing in-process fan-out (map/lazy/guard) across workers (§6.2); non-blocking recursion (§8.3); k8s/Helm (phase P5); external-node telemetry beyond a best-effort `Link` header (§10, deferred); a url4-native GET/Enclave cache (doctrine N1, deferred — §14).

## 2. Architecture
### 2.1 Components
| Component | Responsibility | Reuses |
|---|---|---|
| Control plane | REST schedule/execute/stop/status; token + NATS-cred minting; **trust authority only, off the per-event hot path**. | scoreboard `create_app`/`_lifespan`, Pydantic settings, Tortoise `db.py` |
| Reaper | Singleton liveness component (not a web-process side-effect) — §9. | Postgres advisory lock / JetStream durable consumer |
| Worker | url4 `Executor` on one subtree; NATS pub `.out`/sub `.in`; heartbeat; node-level stop. | `packages/url4` `run()` + new SDK observation hook |
| JobRunner | Run one long container to completion, **run-once** (§7). | docker SDK / kubernetes client |
| NATS JetStream | Durable event log + control + client delivery transport. | — |
| Postgres | Session/node state registry + terminal results. | aigateway/scoreboard Tortoise pattern (plain abstract-Base, **not** the credential AES `ORMStore`) |

### 2.2 Distribution granularity (corrected)
The unit of remote execution is a url4 **sub-expression/subtree** run in-process by the existing `Executor`. **Remote distribution occurs only across `IOLayer.fetch` edges that resolve to an internal child session.** In-process fan-out — `MapNode`/`LazyExprNode`/`GuardNode` via `ctx.spawn`/`ctx.execute_node` (local cap `DEFAULT_MAP_CONCURRENCY=8`) — **stays inside one worker** in v1. Each worker is sized for whole-map in-process load, and the SDK exposes a **node-level sub-session telemetry/stop channel** so a runaway in-process map is still observable and killable from the control plane. The earlier "single seam" claim is retracted; the engine's memo table, `TaskGroup`, semaphores, and `Context` chain remain strictly per-worker.

## 3. Session & node state machine
States: `scheduled → starting → running → {succeeded | failed | dead | stopped | timed_out}`.
- **Terminal states are absorbing.** Exactly one non-terminal→terminal transition per session, behind a **single-writer compare-and-swap** (`UPDATE … WHERE status IN (<non-terminal>) RETURNING` — scoreboard's optimistic pattern). First terminal wins; every later signal (duplicate delivery, container-exit, late heartbeat) attaches diagnostics only.
- **`result` vs death disambiguation.** Container-exit is not "dead": exit-0 within grace of a durably-committed `result` **confirms** `succeeded`; non-zero with no committed terminal → `failed`. A committed `result` beats a concurrent stop (late result after commit → no-op; stop before any committed result → `stopped`, late result dropped).
- Conformance: *crash-after-success yields exactly one terminal transition and one subtree cost total.*

## 4. Control-plane API
- `POST /sessions` `{url4, ownership}` (+ authenticated parent token on recursion) ⇒ `{session_id, node_id, trace_id, token, subjects, nats_read_cred, exp}`. `trace_id`, `ownership`, and lineage on a child are taken **from the authenticated parent token, never the request body** (§5).
- `POST /sessions/{id}/execute` — start the run.
- `POST /sessions/{id}/stop` — publish stop to the node's `.in` + `JobRunner.stop()`; rejected (no-op) against a terminal session.
- `POST /sessions/{id}/refresh` — re-issue the short-lived control token **iff** the session is still live (§5).
- `GET /sessions/{id}` — state/status.
- **Client event delivery:** the client consumes events over **NATS-over-WebSocket** using a read-scoped `trace.<id>.node.>` credential minted by the control plane. There is **no** control-plane WS relay (FastAPI stays off the hot path; deletes a hand-rolled pump).

## 5. Token & NATS subject model
- **Subjects encode lineage in the path:** `trace.<trace_id>.node.<ancestor>…<self>.out` / `.in`. A parent's subtree read grant is the **`>` multi-token wildcard** on its own path — matching **descendants only, never siblings**. Per-node worker creds carry **no `node.*`** wildcard (which would grant trace-wide read + forge). The trace-wide read (`trace.<id>.node.>`) is minted **only** for the client / durable aggregator.
- **Token = signed JWT** `{session_id, node_id, trace_id, subject_prefix, scope, depth_budget, exp}`. Lifetimes are decoupled: a **short-exp (~5 min) control JWT** (refreshed via `POST /refresh`, which also re-checks liveness) + a **NATS user-JWT whose exp = `activeDeadlineSeconds`**. Every token check is also a **state check** — WS-connect and child-schedule are rejected against any terminal session; on terminal transition the NATS user is added to the account **revocation list**. The WS credential is carried in a header / short-lived socket ticket, **never** a query string.
- **Child-schedule authorization:** the control plane derives the child's `trace_id`/`ownership` from the parent token, verifies `parent_session_id == token.session_id`, and refuses when the decrementing **`depth_budget`/`spawn_budget`** claim hits zero (prevents a compromised leaf from spawning a cost bomb; doctrine N4).

## 6. Event & telemetry model
### 6.1 Signals & envelope
One `trace_id` per tree. Envelope `{trace_id, span_id, parent_span_id, session_id, node_id, type, ts, stream_seq, payload}`. Three deliberately-separate signals (doctrine O2): `log`, `span` (OTel GenAI `gen_ai.*`, token counts), `cost.usage` (separate taxonomy, `self`/`subtree`). Plus `heartbeat`, lifecycle (`started`, `sigterm`, `terminated`), `result`.
- **W3C traceparent** is threaded through `POST /sessions` into the child token; a child roots its top span on the parent's fetch-span context and stamps the correct `parent_span_id` (fixes fan-out children collapsing under the session root).
### 6.2 Delivery & dedup
- **One JetStream stream per `trace_id`**; the message's **stream sequence** is the dedup identity (forwarded verbatim into the envelope). The app-level `(trace_id, span_id, seq)` idea is discarded (span_id isn't unique per envelope; app-seq isn't unique across per-node publishers).
- **Durable terminals.** The reaper publishes the terminal envelope **durably to the same subject the client replays** (not just live-relayed) — a replay from seq 0 must always reach a terminal marker; the live path is a latency optimization only (doctrine F2 applied to lifecycle).
### 6.3 Cost authority
Under flat direct-publish, a parent is **consume-only**: it subscribes a child's `.out` solely to (a) return the payload to its `Executor` and (b) fold the child's `cost.usage{subtree}` into its own roll-up — it **never re-publishes** child events (doctrine F1 per-hop relay is superseded for the runner). The **authoritative money figure is the store-side sum of `cost.usage{scope:self}`**, deduped by an id that includes scope; parent `subtree` events are advisory. Ordering: a node publishes `result` **after** its `cost.usage{subtree}`.

## 7. JobRunner port
Contract: **run one container to completion, exactly once — no substrate-level restart.** k8s `backoffLimit: 0` + `restartPolicy: Never`; Docker no `--restart`. Retry is a **control-plane operation that mints a new session with a new `trace_id`** (in-memory url4 state makes in-place re-execution non-idempotent → double-bill + orphan fan-out).
- `poll_terminal()` returns an enum `{succeeded, failed, timed_out}` + `exit_code`, reconciled **every tick and on startup** (a k8s watch is a latency layer, not the sole source). k8s maps `Job.status.conditions` then pod `terminated.reason` (`Completed`→succeeded, `OOMKilled`/`Error`→failed, `DeadlineExceeded`→timed_out).
- `stop()` is **idempotent** and tolerant of an already-gone container; k8s deletes with `propagationPolicy=Background` + `gracePeriodSeconds` and reconciles the pod is gone before declaring `stopped`.
- A **control-plane watchdog** is the timeout floor for **every** adapter (Docker has no native timeout).
- `logs()/tail()` is an explicit port method with per-adapter guarantees (deferred detail to P5 — §14).
- Conformance on **both** adapters: a worker crash yields exactly one terminal + one subtree cost total; clean/non-zero/OOM/deadline map to equal terminal enums.

## 8. Recursion (internal children)
### 8.1 Mechanism
`InternalNodeAdapter.fetch` for an internal child expr: `POST /sessions` (lineage from the parent token) → subscribe the child's `.out` (descendants-only grant) → `POST execute` → consume-only cost fold (§6.3) → return the final payload to the `Executor`. External children: §10.
### 8.2 Capacity (owner-approved: blocking + admission)
Recursion is **blocking** (a parent's `fetch` awaits the child's whole run), so peak demand = **simultaneously-live-node count (~N), not the leaf frontier**. To prevent hold-and-wait deadlock, the control plane makes an **all-or-nothing per-tree container-budget reservation at schedule time** (fail-fast if it would exceed cap C). Parent-blocks-on-child is a **named scaling limit**.
### 8.3 Cancellation & orphans
`InternalNodeAdapter.fetch` wraps subscribe/await in `try/finally`; on `CancelledError`/timeout it **synchronously stops the child before re-raising**, and the control plane cascades the stop to the child's descendants (idempotent). `parent_session_id` is a persisted FK; on **any** terminal transition the reaper enumerates live descendants and stops each. Child failures are serialized back as the **original `Url4Error` subclass** (`.code`/`.permanent` intact) so `GuardNode` retry/optional/quorum behaves as in-process.

## 9. Liveness & death
Three independent signals: (a) **heartbeat timeout** (no `.out` heartbeat within deadline), (b) explicit **`sigterm`/`terminated`**, (c) **`JobRunner.poll_terminal()`** reports exit. The **reaper is a singleton component** (own single-replica deployable **or** every sweep gated behind a Postgres advisory lock / single-consumer JetStream durable) — never an implicit FastAPI-lifespan side-effect racing across web replicas. Heartbeat-timeout reap **fences**: it calls `JobRunner.stop()` with the terminal transition, and the NATS ingress rejects publishes for an already-terminal session (per-session fencing epoch) so a partitioned-but-alive worker cannot resurrect output after the partition heals. All transitions go through the §3 absorbing CAS.

## 10. Owned-internal vs external nodes
`NodePort` with two adapters; ownership is decided at schedule (from the authenticated context). **Internal** = full lifecycle + NATS telemetry + stop. **External** = url4 `GET` only, no lifecycle control; telemetry is best-effort via the RFC 8288 `Link: /traces/{id}` header, and a non-streaming external node's cost is recorded **`UNKNOWN`, never `$0`** (avoids silently undercounting the tree total). Full external-telemetry contract is P4 (§14).

## 11. SDK seams (packages/url4)
Added to the SDK as **ports** (core never imports runner adapters): (1) an **execution-observation hook** on `ExecutionContext` surfacing node start/end + logs/spans/cost **without touching the memo hot path**; (2) **W3C trace/span context** propagation through `spawn`/`child`; (3) a **node-level sub-session stop/telemetry channel** so in-process map/lazy/guard subtrees are observable and killable (§2.2); (4) a **streaming-capable transport extension point** the runner's Internal/External adapters plug into. v1 does **not** distribute `spawn`/`execute_node`. SDK public-surface changes get grammar-owner (CODEOWNERS) review.

## 12. Deployment & phasing
- **P0** scaffold `apps/runner` (src-layout, `create_app`, config, cli, two-stage uv Dockerfile, CI test lane, CODEOWNERS, dependabot, `.claude/sdlc.local.md` entry) · docker-compose (NATS JetStream + Postgres + control-plane + worker).
- **SDK** the §11 seams.
- **P1 (v1)** state+store · token+NATS creds · events+JetStream · JobRunner+Docker · worker · control-plane REST + NATS-over-WS delivery · **docker-compose e2e validation**.
- **P2** internal recursion (adapter + admission budget + orphan cascade + traceparent) · recursion e2e · (follow-up) non-blocking continuation.
- **P3** full liveness/death (3 signals + singleton reaper + fencing).
- **P4** external-node adapter · per-trace concurrency budget at the aigateway boundary + content-addressed result cache hook.
- **P5** k8s Job adapter · Helm chart · **Helm local-dev (kind/minikube) validation** · release lane.

## 13. Testing & conformance
TDD. Unit: JobRunner adapters (fake docker/k8s), token sign/verify + scope/lineage, event envelope + stream-seq dedup, absorbing-terminal CAS, reaper with fake clock + fencing. Integration: **testcontainers** for NATS + Postgres; **docker-compose e2e** for the single-node happy path; **kind/minikube** for the Helm path. Conformance suite: crash-after-success (one terminal, one cost total), fan-out span-tree via traceparent, cost roll-up authority, stop-cascade to descendants, both-adapter terminal-enum parity.

## 14. Out of scope / deferred (documented so they are not re-litigated)
- **Distributing in-process fan-out** (map/lazy/guard) — v1 keeps it in-worker (owner-approved fork; §2.2).
- **Non-blocking recursion** — blocking + admission budget in P2; detached-continuation is a P2 follow-up (owner-approved fork; §8.2).
- **External-GET `Link`-header telemetry return** (doctrine T2/F3) — locked in P4; record `UNKNOWN` until then.
- **JobRunner `logs()/tail()`** per-adapter guarantees — P5 (k8s pod-log semantics differ from docker).
- **Doctrine fork F4** (GET-leaf telemetry return) stays OPEN; runner-v1 has **no** url4-native GET leaf. The **N1 Enclave GET cache** is omitted (fresh container per session) — recorded as an explicit doctrine deviation for the owner, not hardcoded.
- **Diamond-dep span attribution** (a memoized node with ≥2 demand-parents) — grand total stays correct; per-node attribution refinement (OTel span links + canonical parent) is later work.

## 15. Decisions locked (owner-approved)
1. Substrate = `JobRunner` port + Docker/k8s-`Job` adapters (not Temporal/Argo), **run-once**.
2. NATS = hybrid; FastAPI mints subject-scoped creds; workers pub/sub JetStream directly; **client consumes NATS-over-WS directly** (no control-plane bridge).
3. Child spawn = control-plane-only; lineage from the authenticated token; depth budget.
4. v1 = single-node happy path; **remote granularity = fetch-edges only**; in-process fan-out stays in-worker with a node-level stop channel.
5. Recursion = blocking + per-tree container-budget admission; continuation is a follow-up.
