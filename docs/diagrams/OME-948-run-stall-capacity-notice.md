# OME-948 — Run-stall capacity warning: mechanism diagrams

Mermaid views of how the Engine detects a Runner Job that can never start and surfaces a
generic capacity warning to the attached client, plus the schedule-time 503 hardening.

- **Linear:** https://linear.app/openmined/issue/OME-948/surface-a-generic-capacity-warning-when-a-runner-job-cannot-be
- **Spec:** `docs/spec/2026-08-22-OME-948-run-stall-capacity-notice.md`
- **Plan:** `docs/plan/2026-08-22-OME-948-run-stall-capacity-notice.md`

## 1. Component map — where the mechanism lives

```mermaid
flowchart TD
    SDK["Researcher / SDK<br/>(packages/screamingface · Client)<br/>~8 candidate runs in flight"]

    subgraph ENGINE["screamingface-engine — control plane (FastAPI App)"]
        REST["REST run lifecycle<br/>POST /token · GET /?q=… · DELETE /"]
        WSB["WS bridge (/ws)<br/>attach · heartbeat · outbound frames"]
        REG["ConnectionRegistry<br/>topics() snapshot · notify()"]
        WATCH["RunStallWatcher (policy)<br/>sweep() every tick<br/>tick = max(1s, warnAfter / 8)"]
        WIRING["_install_run_stall_watch<br/>wired ONLY when runner='k8s'"]
        K8["K8sJobRunner<br/>create / status / delete Job"]
        MET["/metrics<br/>run_stalls_stuck · run_stalls_warned_total"]
    end

    subgraph CLUSTER["Kubernetes — sf-fusion namespace"]
        QUOTA["ResourceQuota 'ns-ceiling'<br/>4 CPU / 6 GiB — already 100% used"]
        JOB["Runner Job url4-…<br/>status.active = 0<br/>→ reports 'scheduled'"]
        POD["Runner Pod 500m / 1Gi<br/>NEVER created — FailedCreate"]
    end

    SDK -->|"1· mint token"| REST
    SDK -->|"2· attach WS (subscriber)"| WSB
    SDK -->|"3· start run — 202"| REST
    REST -->|"4· schedule()"| K8
    K8 -->|"5· create Job"| JOB
    JOB -.->|"6· pod refused by quota"| QUOTA
    QUOTA -.->|"status stays 'scheduled'"| JOB

    WIRING -->|"wires the sweep loop"| WATCH
    WATCH -->|"7· status(topic) per live topic"| K8
    K8 -->|"read Job"| JOB
    WATCH -->|"8· stuck past bound → notice"| REG
    REG -->|"9· deliver to attached sockets"| WSB
    WSB -->|"10· Log frame → console"| SDK
    WATCH -->|"counters"| MET
    MET -. "gauge shows live stuck" .-> OPS["operator / dashboard"]

    style WATCH fill:#fff3bf,stroke:#f08c00
    style JOB fill:#ffe8e8,stroke:#e03131
```

**The one-sentence story:** the SDK drives a run; Kubernetes refuses the pod (quota), leaving
the Job stuck at `scheduled`; the RunStallWatcher notices the stall and pushes a generic WARN
through the App's only voice — the notice channel — instead of the client staring at silence
for up to 16 h.

## 2. Sequence — the two paths that matter

```mermaid
sequenceDiagram
    autonumber
    participant S as SDK Client
    participant A as Engine REST
    participant W as WS Bridge
    participant R as RunStallWatcher
    participant J as K8sAdapter
    participant K as Kubernetes (sf)
    participant U as User

    Note over S,A: path 1 — the stall becomes visible
    S->>A: POST /token (capability)
    S->>W: connect /ws?ticket=…
    W->>W: registry.add(topic) — subscriber gate opens
    S->>A: GET /?q=… Prefer: respond-async
    A->>J: schedule(topic, expr, deadline)
    J->>K: create Job url-…
    A-->>S: 202 Accepted + Location
    Note over K: quota at 100% CPU — pod refused (FailedCreate), status.active=0
    loop every tick (max(1s, warnAfter/8))
        R->>J: status(topic) for each live topic
        J-->>R: "scheduled"
    end
    Note over R: "scheduled" persisted ≥ warnAfter (60s)<br/>and not yet warned this episode
    R->>W: registry.notify(topic, WARN LogEvent)
    W-->>S: ai.url4.log · severity=WARN<br/>"the runner service is at capacity…"
    S->>U: Log event → console line + evaluation feed
    U->>A: DELETE / (user stops the run)

    Note over S,A: path 2 — refused at schedule time
    S->>A: GET /?q=… (another run)
    A->>J: schedule()
    J->>K: create Job
    K-->>J: ApiException 500/429 (transient)
    J->>J: raise RunnerScheduleUnavailable (engine-local)
    A-->>S: 503 problem + Retry-After: 1<br/>"the runner could not schedule this run — retry later"
    Note over A,J: a 4xx would propagate unchanged — that is an engine manifest bug, not capacity
```

## 3. The watcher's decision logic (per sweep, per topic)

```mermaid
flowchart TD
    SW["sweep() — every tick<br/>tick = max(1s, warnAfter_s/8)"] --> SNAP["live = registry.topics()<br/>(snapshot)"]
    SNAP --> LOOP{"for each topic"}
    LOOP --> PROBE["status = runner.status(topic)"]
    PROBE -->|"probe raised ⚠"| TOL["log · skip this tick<br/>tracking KEPT —<br/>never warn on a broken probe"]
    PROBE -->|"= 'scheduled'"| FIRST{"first_seen exists?"}
    FIRST -->|no| SET["first_seen[topic] = now"]
    FIRST -->|yes| BOUND{"now − first_seen<br/>≥ warnAfter?"}
    SET --> BOUND
    BOUND -->|"no — still young"| NEXT["next tick"]
    BOUND -->|"yes"| ONCE{"warned this episode?"}
    ONCE -->|"no"| WARN["notify(topic, WARN LogEvent)<br/>generic body — no internals"]
    WARN --> MARK["warned = add(topic)<br/>warned_total += 1"]
    ONCE -->|"yes"| SILENT["stay silent"]
    PROBE -->|"anything else<br/>(running · failed ·<br/>succeeded · timed_out · not_found)"| DROP["drop tracking<br/>pop first_seen · discard warned"]
    DROP --> PRUNE
    MARK --> PRUNE["after loop: prune topics no longer in snapshot<br/>(reconnect restarts the stall clock)"]
    SILENT --> PRUNE
    PRUNE --> MET["metrics:<br/>stuck_count gauge · warned_total counter"]

    style PROBE fill:#ffe8e8,stroke:#e03131
    style WARN fill:#d3f9d8,stroke:#2f9e44
```

**Invariants the diagram encodes:**

- Warn **at most once per stall episode** — a run healed is forgotten instantly (no stale clock).
- A probe failure **costs at most a late warning**, never a crash or a corrupted decision.
- A topic whose client detached is **pruned**, so a reconnect starts a fresh stall clock instead
  of warning instantly against an old one.
- The message is **generic** — symptom-based detection ("scheduled" persisting), never
  cause-based — so the same notice covers quota refusals, node pressure, and any future
  scheduling failure. It carries no internals (no "quota", namespace, or Pod names).

## Accuracy notes

- The notice reaches the client through the SDK's existing `Log` rendering (console line +
  evaluation feed). Rendering *generic* log bodies in the rich TUI panel is the documented
  client-side follow-up and is not shown here.
- The 60 s bound, the `max(1, bound/8)` cadence, and the `"scheduled"` predicate match
  `run_stall.py` / `app.py` verbatim; the knob is `URL4_CLOUD_RUN_STALL_WARN_AFTER_S`
  (chart: `config.runStallWarnAfterS`).
- Advisory-only by design: the watch never stops, reschedules, or otherwise touches a run.
