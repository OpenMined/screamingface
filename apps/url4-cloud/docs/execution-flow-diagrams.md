# url4-cloud — execution-flow diagrams

Static reference for the execution flow through the url4-cloud codebase and the
purpose of each source file. Companion to `docs/request-workflow.md` (the
narrative) and `docs/protocol.md` (the wire contract).

---

## 1. End-to-end execution flow (backend + runner)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CLIENT (browser / CLI)                                                      │
└──────┬──────────────────────────────────────────────────────────────────────┘
       │  ① POST /token                          ② WS /ws?ticket=<jwt>
       ▼                                          ▼
┌────────────────────────────── BACKEND (url4_cloud) ──────────────────────────┐
│                                                                              │
│  rest/routes.py ──mint_token──► auth/jwt.py  ──sign──► {token}               │
│                                                                              │
│  ws/endpoint.py ──verify ticket──► ws/registry.py .add(topic)  ◄── 428 GATE  │
│                  └─► ws/bridge.py  (Bus → WebSocket, single-writer)          │
│                                          ▲                                   │
│  rest/routes.py  GET /?q=                 │ same JetStream stream            │
│   ├─ _require_q            (400)          │   (sync scanner + WS bridge are  │
│   ├─ rest/interest.py      (428 if no WS) │    independent consumers)        │
│   ├─ trace.parse_traceparent (drop bad)   │                                   │
│   ├─ _forwarded_credential (CF→Bearer)    │                                   │
│   ├─ _schedule ─► jobs/port.py            │                                   │
│   │      └─ exists? (409) else schedule   │                                   │
│   │            ┌─────────────┴─────────────┴── ADAPTER ──┐                    │
│   │            ▼                                           ▼                   │
│   │   jobs/k8s.py (prod)                        jobs/inprocess.py (local)     │
│   │   batch/v1 Job + per-run                    asyncio.Task =               │
│   │   credential Secret                         publish.run(...)             │
│   │            │                                           │                   │
│   └─ _run_sync (sync) OR _accepted (202)        │            │               │
└──────────────────────────────────────────────────┼────────────┼───────────────┘
                                                   │            │
                                                   ▼            ▼
┌──────────────────────────── RUNNER (url4_cloud_runner) ──────────────────────┐
│                                                                               │
│  __main__.py  ◄── entrypoint (url4-cloud-runner)                              │
│   ├─ params_from_env   ──► RunnerParams(topic,url4,nats)                      │
│   └─ build_executor    ──► AIGATEWAY_TOKEN?                                   │
│         ├─ yes ► aigateway_connector.build_aigateway_world ─► Url4Executor    │
│         └─ no  ► url4_executor.deny_by_default_world      ─► Url4Executor    │
│                                                                               │
│  publish.run(bus, executor, topic, url4, traceparent)   ◄── THE ORCHESTRATOR │
│   │  trace.py.parse_traceparent → run-root trace context                      │
│   │  Started → (telemetry…) → CostUsage{subtree} → Result → Terminated        │
│   │            │                                                               │
│   │            ▼ async for step in executor.execute(url4, trace=…)            │
│   │  ┌──────────────────────────────────────────────────────────────────┐     │
│   │  │ url4_executor.Url4Executor                                         │     │
│   │  │   _Bridge  (sync Observer ─► async generator, priority-drop)      │     │
│   │  │   _RunState (engine events ─► Traced Span/Cost/Log + subtree)     │     │
│   │  │   drives url4.dag.run(io = aigateway Url4Node world) ─────────┐   │     │
│   │  └──────────────────────────────────────────────────────────────│───┘     │
│   │                                                                 ▼         │
│   │              aigateway_connector ── POST /v1/chat/completions ──► aigateway│
│   │                              └─ optional Tavily web_search/web_fetch loop │
│   └─► bus.publish(topic, CloudEvent)  ── one per frame, monotonic sequence    │
└──────────────────────────────────────────────────┬────────────────────────────┘
                                                  │
                                                  ▼  NATS JetStream (shared append-log)
                          ┌───────────────────────┐
                          │  Bus port (url4_cloud │
                          │  _nats: bus / nats_bus│
                          │  / memory)            │
                          └───────────┬───────────┘
                                      │ frames flow back up
                                      ▼
   ws/bridge.py ──► WS frames to client   AND   rest/routes.py._run_sync (inline 200)
```

---

## 2. Runner package — execution flow (`url4_cloud_runner/`)

```
                         ┌─────────────────────────────────────┐
   entrypoint ──────────►│  __main__.py                        │
   url4-cloud-runner     │   params_from_env() → topic/url4    │
                         │   build_executor()  ────────────┐   │
                         └────────────────────────────────┬──┘
                                                          │
                         ┌────────────────────────────────┘
                         ▼
                    ┌──────────────────────────────┐     no token
                    │  aigateway_connector.py      │◄─────────────┐
                    │  build_aigateway_world()     │             │
                    │  → Url4Node world (routes →  │   deny_by_default_world()
                    │     POST /v1/chat/completions│             │
                    │     [+ Tavily tools])        │             │
                    └──────────────┬───────────────┘             │
                                   │  io=world.node              │
                                   ▼                             │
                    ┌──────────────────────────────┐             │
                    │  url4_executor.py            │◄────────────┘
                    │  Url4Executor.execute()      │
                    │   ├─ _Bridge  (sync Observer │
                    │   │   ─► async generator)    │
                    │   ├─ _RunState (engine evt → │
                    │   │   Traced Span/Cost/Log)  │
                    │   └─ drives url4.dag.run(io) │
                    └──────────────┬───────────────┘
                                   │ async yield ExecStep
                                   ▼
                    ┌──────────────────────────────┐
   orchestrator ◄───│  publish.py  run()           │
                    │   establish root trace       │◄─── trace.py
                    │   Started → telemetry… →     │     parse_traceparent()
                    │   CostUsage{subtree} →       │
                    │   Result → Terminated        │
                    └──────────────┬───────────────┘
                                   │ bus.publish(CloudEvent)
                                   ▼
                                NATS Bus  ──► backend ──► client

   ┌─────────────────────────────────────────────────────────────┐
   │  executor.py   the PORT — Executor Protocol, ExecStep,      │
   │                Traced, Completed, Telemetry, TraceContext   │
   │                (publish + url4_executor both depend on it)  │
   └─────────────────────────────────────────────────────────────┘
```

### Runner call sequence (one run)

```
__main__.main()
 │
 │  ① params_from_env(env) ───────────────────► trace.py (not here; pure env parse)
 │
 │  ② build_executor(env)
 │        │  AIGATEWAY_TOKEN?
 │        ├─ yes ─► aigateway_connector.build_aigateway_world()
 │        │              └─► GET /v1/models → routes → Url4Node  (+ Tavily client)
 │        │           Url4Executor(world.node, world_aclose=world.aclose)
 │        └─ no  ─► Url4Executor(deny_by_default_world())
 │
 │  ③ publish.run(bus, executor, topic, url4, traceparent)
 │        │
 │        │  trace.parse_traceparent(traceparent) → trace_id (or mint fresh)
 │        │  TraceContext + _Sequencer ;  bus.ensure_stream(topic)
 │        │  publish StartedEvent
 │        │
 │        │  async for step in executor.execute(url4, trace=ctx):   ◄── ④
 │        │     │
 │        │     │  ┌── inside Url4Executor.execute() ──────────────┐
 │        │     │  │ url4.dag.run(io=Url4Node, observer=_Bridge)   │
 │        │     │  │   engine → aigateway_connector route →        │
 │        │     │  │     POST /v1/chat/completions (± Tavily loop) │
 │        │     │  │   engine calls _Bridge.on_event() INLINE/sync │
 │        │     │  │ _RunState.map() → Traced(Span/Cost/Log)       │
 │        │     │  │ finally: cancel task, _aclose_world()         │
 │        │     │  └───────────────────────────────────────────────┘
 │        │     │
 │        │     ├─ Telemetry/Traced → _trace_fields + _wrap_telemetry → publish
 │        │     └─ Completed         → break
 │        │
 │        │  publish CostUsage{subtree} → ResultEvent → TerminatedEvent{succeeded}
 │        └─ except ─► publish TerminatedEvent{failed} + ErrorInfo
 │
 └─  asyncio.run(_main())
```

---

## 3. File purpose — one line each

### Runner (`runner/src/url4_cloud_runner/`)

```
┌─ entrypoint ──────────────────────────────────────────────────┐
│ __main__.py   env → NatsBus + executor → publish.run()        │
├─ orchestrator ────────────────────────────────────────────────┤
│ publish.py    drives executor, wraps frames as CloudEvents,   │
│               publishes the Started…Terminated lifecycle      │
├─ adapter (the only url4 importer) ────────────────────────────┤
│ url4_executor.py   Url4Executor: _Bridge (sync→async),        │
│                    _RunState (events→Traced), drives the DAG  │
├─ world builder ───────────────────────────────────────────────┤
│ aigateway_connector.py   credential → Url4Node route-per-     │
│                          model (+ optional Tavily web tools)  │
├─ port (the contract) ─────────────────────────────────────────┤
│ executor.py   Executor Protocol, ExecStep, Traced, Completed, │
│               Telemetry, TraceContext — the seam              │
├─ shared helper ───────────────────────────────────────────────┤
│ trace.py      parse_traceparent() — strict W3C validation     │
├─ package hub ─────────────────────────────────────────────────┤
│ __init__.py   re-exports the public runner API                │
└───────────────────────────────────────────────────────────────┘
```

| File | Purpose |
|---|---|
| `__main__.py` | Job entrypoint: read env → wire `NatsBus` + executor → call `publish.run` |
| `publish.py` | `run()` orchestrator — drives the executor, publishes the CloudEvents lifecycle |
| `url4_executor.py` | The **only** url4-engine adapter (`_Bridge` sync→async, `_RunState`, `Url4Executor`) |
| `aigateway_connector.py` | Builds the `Url4Node` "world" of routes → aigateway chat (+ optional Tavily tools) |
| `executor.py` | The `Executor` **port** — the seam (stream `Telemetry`/`Traced` → one `Completed`) |
| `trace.py` | Shared W3C `traceparent` strict validation (used by runner + backend) |
| `__init__.py` | Public re-export hub |

### Backend (`backend/src/url4_cloud/`)

| File | Purpose |
|---|---|
| `app.py` | FastAPI factory — `create_app` (DI) / `create_app_from_env` (prod) / `make_local_app` (in-process) |
| `config.py` | `Settings` + replay-window TTL validation |
| `rest/routes.py` | REST control plane — `POST /token`, `GET /?q=` (sync/async), `DELETE /` |
| `rest/interest.py` | `SubscriberGate` **port** behind the 428 gate |
| `ws/endpoint.py` | `GET /ws` — verify ticket, register interest, start bridge |
| `ws/bridge.py` | `Bridge` — Bus→WS streaming, single-writer, `Attach`/`Stop`, heartbeats, nacks |
| `ws/registry.py` | `ConnectionRegistry` — live-WS counts per topic (the real 428 source) |
| `jobs/port.py` | `JobRunner` **port** + `job_name(topic)` (the stateless 409 identity) |
| `jobs/k8s.py` | Prod adapter — batch/v1 Job + per-run credential Secret (refs, never literals) |
| `jobs/inprocess.py` | Local adapter — spawns `publish.run` as an `asyncio.Task` |
| `jobs/factory.py` | Composition root — `URL4_CLOUD_RUNNER` → k8s adapter or `None` |
| `auth/*` | `JwtCodec`, RFC 9457 `Problem` handlers, FastAPI `VerifiedClaims` dependency |
| `schemas/*` | OpenAPI/AsyncAPI/CloudEvents Pydantic models (`type` `oneOf`) |
| `metrics.py`, `ops.py` | OpenMetrics `/metrics`, `/livez` `/readyz` probes |
| `testing/mock_runner.py` | Test executor/runner doubles |

### Shared (`shared/`)

| Package | Purpose |
|---|---|
| `url4_cloud_nats` | `Bus` port + `NatsBus` / `InMemoryBus` adapters + codec |
| `url4_streaming_protocol` | The wire contract: CloudEvents envelope, `taxonomy`, `signals`, `unions` |

---

## 4. Key invariants

- The **runner produces** the CloudEvents lifecycle; the **backend only bridges/schedules** — it never re-shapes a frame.
- The two packages talk through exactly **two shared contracts**: the **`Bus`** (NATS) and the **`url4_streaming_protocol`** wire models.
- Within the runner, `publish.py` ↔ `url4_executor.py` talk **only** through the `executor.py` port (`Executor` Protocol); `publish` never imports `url4`.
- Only `aigateway_connector.py` + `__main__` construct a `Url4Executor`; everything else treats it as an opaque `Executor`.
- The runner is a 4-layer pipeline: **entrypoint → orchestrator → adapter → (url4 engine + aigateway world)**, all typed by one `executor.py` port, with `trace.py` as a shared leaf helper.
