# url4 Cloud Runner — Implementation Plan

**Ticket:** OME-443 (epic) · **Spec:** `docs/spec/2026-07-15-url4-cloud-runner-spec.md`
**Goal:** Ship a cloud service that executes url4 ensemble DAGs as long-running (>15 min) distributed jobs — FastAPI control plane (`apps/runner`, port 9107), Docker/k8s `JobRunner` substrate, NATS JetStream event streaming, Postgres session/node state, session tokens, owned-internal vs external node split — delivered single-node-first, then recursion, liveness, external nodes, and k8s/Helm.
**Architecture:** Wrap the in-process url4 `Executor`; distribute only across `IOLayer.fetch` edges that resolve to internal child sessions (in-process map/lazy/guard stay in-worker with a node-level stop channel). Control plane = trust authority only; clients consume NATS-over-WS directly. See spec §2.
**Tech stack:** Python 3.12 · uv · hatchling (src-layout) · FastAPI + Pydantic settings · Tortoise ORM (SQLite-local / Postgres-hosted) · NATS JetStream · docker SDK / kubernetes client · pytest + testcontainers · ruff + pyright. Reuses aigateway/scoreboard `create_app`/`db.py`/Dockerfile/Helm patterns.

## Phase P0 — Foundations
- [ ] **Scaffold `apps/runner`.** src-layout, `create_app`/`_lifespan`, `config.py` (Pydantic, `RUNNER_` prefix), `cli.py`, two-stage uv Dockerfile, `runner-tests.yml` CI lane, CODEOWNERS, dependabot ecosystem, `.claude/sdlc.local.md` stack entry.
- [ ] **docker-compose local-dev infra.** NATS JetStream + Postgres + control-plane + worker image, healthchecks, one-command bring-up + README.

## Phase SDK — url4 execution seams (`packages/url4`)
- [ ] **SDK seams (spec §11).** Execution-observation hook (no memo-hot-path touch) · W3C trace/span propagation through `spawn`/`child` · node-level sub-session stop/telemetry channel (in-process map/lazy/guard observable + killable) · streaming-transport extension point. No `spawn` distribution in v1. Grammar-owner review.

## Phase P1 — Single-node happy path (v1)
- [ ] **Session/node state + Store.** scoreboard-style abstract-Base + domain `Store` Protocol (NOT the credential AES `ORMStore`); **absorbing terminal + single-writer CAS** (spec §3); Tortoise migrations.
- [ ] **Token + scoped NATS creds.** Hierarchical subject path + descendants-only `>` grant; lineage-from-authed-token; depth/spawn budget; short control-JWT exp + `/refresh`; NATS-JWT exp = `activeDeadlineSeconds`; revoke-on-terminal (spec §5).
- [ ] **Event envelope + JetStream.** One stream per `trace_id`; **stream-seq dedup**; durable terminal events; `cost.usage` self/subtree with store-side authoritative sum; traceparent-rooted spans (spec §6).
- [ ] **JobRunner port + Docker adapter.** **Run-once/no-restart** contract; `poll_terminal()` enum + exit; idempotent `stop()`; control-plane watchdog timeout floor (spec §7).
- [ ] **Worker runtime.** url4 `Executor` on one subtree; NATS pub `.out`/sub `.in`; heartbeat; observation-hook→events; node-level stop wiring.
- [ ] **Control-plane REST + client NATS-over-WS delivery.** schedule/execute/stop/refresh/status; read-scoped `trace.<id>.node.>` cred to the client; **no WS bridge** (spec §4).
- [ ] **Docker-compose end-to-end validation.** schedule → attach (NATS-over-WS) → execute → stream logs/telemetry/cost → terminal; testcontainers (NATS+Postgres) + compose smoke; crash-after-success conformance.

## Phase P2 — Recursion (internal children)
- [ ] **InternalNodeAdapter.** control-plane-only child scheduling; lineage+traceparent from token; consume-only cost fold (no re-publish); **per-tree container-budget admission** (fail-fast); orphan stop-cascade; typed-error passthrough for Guard (spec §8).
- [ ] **Recursion e2e.** nested ensemble; whole-tree subscription via `trace.<id>.node.>`; cost roll-up authority + span-tree conformance.
- [ ] **(follow-up) Non-blocking detached-continuation recursion.** break the parent-blocks-on-child limit (deferred).

## Phase P3 — Liveness & death
- [ ] **Full liveness/death.** 3 signals unified; **singleton reaper** (advisory lock / durable consumer); **fencing** (reject post-terminal publishes); stop-cascade to descendants (spec §9).

## Phase P4 — External nodes & scale limits
- [ ] **ExternalNodeAdapter.** url4 `GET` only; no lifecycle; cost `UNKNOWN` (not `$0`); best-effort `Link`-header telemetry (spec §10).
- [ ] **Per-trace concurrency budget** at the aigateway boundary (token-bucket/lease keyed by trace) + content-addressed result-cache hook.

## Phase P5 — Kubernetes & Helm
- [ ] **K8sJobAdapter.** `backoffLimit:0`/`restartPolicy:Never`; terminal enum from Job conditions + pod reason; `stop()`=delete `propagationPolicy=Background`+grace+reconcile; `logs()/tail()`.
- [ ] **Helm chart.** clone scoreboard `charts/<app>` + `charts/db`; NATS dependency; deployment/service/ingress/configmap/secret/job-migrate/networkpolicy.
- [ ] **Helm local-dev validation.** kind/minikube: `helm lint` + `helm template` + install + migrate job + one run through the k8s adapter.
- [ ] **Release lane.** release-please python entry or manual `runner-v*` tag + `release-runner.yml` (GHCR image + Helm publish).

## Phase process
- [ ] **Reconcile `.claude/task-board.local.md`** label taxonomy vs live Linear (done this session; closes on commit).

## Ticket cascade (Linear, under OME-443)
_Filed — IDs below. Landing `url4-engine` unless noted `pkg/url4-python-sdk` (SDK) or `repo` (process); who-acts `autonomous` (·`deferred` for the follow-up); actor `agentic`._

| Phase | Deliverable | OME-# |
|---|---|---|
| P0 | Scaffold apps/runner + CI/CODEOWNERS/dependabot/sdlc entry | _(filing)_ |
| P0 | docker-compose local-dev infra | _(filing)_ |
| SDK | url4 execution seams (observability + node-stop + traceparent + transport ext) | _(filing)_ |
| P1 | Session/node state + Store (absorbing terminal CAS) | _(filing)_ |
| P1 | Token + scoped NATS creds | _(filing)_ |
| P1 | Event envelope + JetStream | _(filing)_ |
| P1 | JobRunner port + Docker adapter | _(filing)_ |
| P1 | Worker runtime | _(filing)_ |
| P1 | Control-plane REST + NATS-over-WS delivery | _(filing)_ |
| P1 | Docker-compose e2e validation | _(filing)_ |
| P2 | InternalNodeAdapter recursion (+ admission budget + orphan cascade) | _(filing)_ |
| P2 | Recursion e2e | _(filing)_ |
| P2 | (follow-up) non-blocking continuation | _(filing)_ |
| P3 | Full liveness/death (reaper singleton + fencing) | _(filing)_ |
| P4 | ExternalNodeAdapter | _(filing)_ |
| P4 | Per-trace concurrency budget + result cache hook | _(filing)_ |
| P5 | K8sJobAdapter | _(filing)_ |
| P5 | Helm chart | _(filing)_ |
| P5 | Helm local-dev (kind) validation | _(filing)_ |
| P5 | Release lane | _(filing)_ |
| process | Reconcile stale task-board card | _(filing)_ |

## Non-goals / follow-ups
Distributing in-process fan-out; non-blocking recursion (P2 follow-up); external-GET `Link` telemetry contract (P4); `logs()/tail()` k8s semantics (P5); N1 Enclave GET cache + doctrine F4 (deferred, owner). See spec §14.

## Risks (and how they were retired by the 6-lens validation)
| Risk | Retired by |
|---|---|
| Recursion deadlock (container-per-live-node hold-and-wait) | Per-tree container-budget admission at schedule; blocking recorded as a named limit (spec §8.2). |
| Terminal-state corruption (exit-0 clobbered to dead; stop-vs-result race) | Absorbing terminal + single-writer CAS; result-vs-death disambiguation (spec §3). |
| Trace-wide read/forge via `node.*`; cross-trace escalation; cost bomb | Lineage-in-path subjects + descendants-only `>`; lineage-from-token; depth budget (spec §5). |
| k8s `backoffLimit` default re-executes subtree → double-bill + orphans | JobRunner run-once contract; retry = new session/new trace_id (spec §7). |
| "Single seam" false — in-process maps invisible/unkillable | Fetch-edges-only granularity + node-level stop channel (spec §2.2, §11). |
| Duplicate cost, undefined roll-up owner, invalid dedup key | Consume-only parents; store-side `self`-sum authority; JetStream stream-seq dedup (spec §6). |
| Reconnecting subscriber hangs (terminal not durable) | Durable terminal publish to the replay subject (spec §6.2). |
| Partitioned worker resurrects output | Heartbeat-reap fences (stop + terminal + ingress rejection) (spec §9). |
| Reaper races across web replicas | Singleton reaper (advisory lock / durable consumer) (spec §9). |
| Control plane on the hot path it claims to be off | Client consumes NATS-over-WS directly; bridge deleted (spec §4). |
| Replayable bearer token in WS query string | Short exp + `/refresh` + state-check + revocation; header/ticket, not query (spec §5). |
| `ORMStore` misused for non-secret state | scoreboard-style abstract-Base + domain Protocol (spec §2.1). |
