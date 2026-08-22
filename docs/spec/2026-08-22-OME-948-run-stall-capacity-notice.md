# OME-948 — Surface a generic capacity warning when a Runner Job cannot be scheduled

- **Linear:** https://linear.app/openmined/issue/OME-948/surface-a-generic-capacity-warning-when-a-runner-job-cannot-be
- **Landing:** `apps/screamingface-engine`
- **Related discovery:** `OME-947` (`sf-fusion` `ns-ceiling` quota blocks Runner Job pods — the
  failure this unit makes visible); `OME-908` (fair-scheduling — the deeper admission fix, out of
  scope here)

## Problem

When a Runner Job is accepted but its Pod can never be created — e.g. the `sf-fusion` namespace
is at its `ns-ceiling` ResourceQuota (OME-947) — the run stalls silently:

- The engine returns HTTP 202 (`_schedule` → `K8sJobRunner.schedule` succeeds; quota applies to
  *pods*, not to the Job object).
- Kubernetes retries Pod creation (`FailedCreate`), `Job.status.active` stays 0, and
  `_map_status` reports the honest state: **`scheduled`** (Job exists, no active Pod, no
  terminal condition).
- Nothing publishes to the run's stream — the Runner process never starts, and the App's
  `EventConsumer` is read-only ("the App never publishes to the broker"). The WS bridge keeps
  heartbeating (`ws_heartbeat_s=15s`), so the client's 120s receive-timeout never fires.
- The user waits with no information until `activeDeadlineSeconds` (16h) eventually fires
  `DeadlineExceeded` — and even then nothing consumes the `timed_out` state.

A run that was accepted and never executes is exactly the case the notice channel exists for:
"something the caller was promised was dropped … indistinguishable from a bug in the gateway"
(module docstring, `screamingface_engine/notices.py`).

## Required behavior

1. The engine MUST detect a run whose Job is stuck in `scheduled` for at least a grace window
   (`run_stall_warn_after_s`, default 60s; warn at elapsed `>=` the bound).
2. On detection, the engine MUST send **one generic `warn` notice per run** to the run's attached
   client via the existing notice channel (`notices.warn` → `ConnectionRegistry.notify` → WS
   bridge → `Log` frame → SDK `_evaluation/progress.py::_message` renders "ScreamingFace ·
   <body>").
3. The message MUST be generic — "the runner service is at capacity", no quota names, no
   internal detail — because the detection is symptom-based (Pod never starts), not cause-based
   (quota), so the same notice covers node pressure and any other scheduling refusal.
4. Detection MUST NOT false-positive on normal Pod-creation latency or image pulls: a Pending
   Pod counts toward `Job.status.active`, so `scheduled` with `active == 0` persisting past the
   grace window genuinely means "no Pod has ever been created".
5. The watch is Kubernetes-only. Local mode (`InProcessJobRunner`) cannot stall silently — it
   runs immediately or fails fast at accept time (`JobRunnerAtCapacity` → 503) — so the watch is
   wired only when `settings.runner == "k8s"`.
6. Schedule-time transient substrate failures MUST surface as a generic retryable **503** problem.
   The translation is honest about the port contract: `JobRunnerAtCapacity`'s own docstring says a
   cluster-backed runner NEVER raises it ("lets the scheduler absorb the load"), so it is NOT
   reused. Instead `ports.py` — the module `rest/routes.py` and `adapters/k8s.py` already share —
   gains one engine-local exception, `RunnerScheduleUnavailable`. `K8sJobRunner._schedule_blocking`
   maps `ApiException` with `status >= 500 or status == 429` to it; `rest/routes.py::_schedule`
   catches it → `503 + Retry-After: 1` with the generic detail "the runner could not schedule
   this run — retry later". A 4xx `ApiException` is an engine manifest bug and keeps today's
   behavior (surfaces as 500). The REST layer gains NO kubernetes import — `kubernetes` stays
   confined to `adapters/`, and `url4.streaming` gains no new type.
7. A per-topic `status()` failure during a sweep MUST be tolerated: log, skip that topic for
   this tick, keep its tracking state (neither warn nor forget) — the reaper's "a failed stop
   re-arms, never gives up" philosophy. A failed probe can cost a missing or late warning, and
   nothing else: the watch is advisory-only and MUST NOT affect the run itself.
8. Known limitation (accepted for v1): the notice is delivered to sockets attached at warn time;
   a client that RECONNECTS mid-stall does not see it. Fixing that needs re-warn-on-arrival, and
   `ConnectionRegistry.listen()` holds exactly one `AudienceListener` (the reaper's) —
   multi-listener registry surgery is out of scope. Tripwire: if reconnect-during-stall proves
   common in practice, revisit.

## Design

A new policy module `screamingface_engine/run_stall.py`, shaped exactly like the existing
`RunReaper` (policy-only, no FastAPI/WS imports, `sweep()` split from the loop so tests drive the
policy with fakes and an injected clock).

- **Collaborators (narrow structural Protocols, satisfied structurally — TWO collaborators, not
  three):**
  - the runner: `status(topic) -> JobStatus` — the ONE method the watch needs (`not_found`
    already covers "the Job is gone"; simpler than the reaper's two-method `RunControl`). The
    real `K8sJobRunner.status` satisfies it.
  - the registry: `topics() -> frozenset[str]` + `notify(topic, frame)` — both live on the REAL
    `ConnectionRegistry` (never the `interest` DI seam — the same invariant as the reaper).
    `topics()` is a NEW ~4-line snapshot view over `_sessions` and is the only registry change.
- **Clock seams (two, deliberately):** a monotonic `Callable[[], float]` (default
  `time.monotonic`) for the stall bound — the reaper's NTP-jump invariant, verbatim — and a
  `Callable[[], datetime]` (default `datetime.now(UTC)`) for the WARN frame's `time`, the same
  seam `_converge_cache` feeds from `app.state.clock`. Elapsed time and frame time are different
  questions; one clock cannot honestly answer both.
- **Policy state:** per-topic `first_seen_stuck` (monotonic) and a `warned` set. `sweep()` reads
  `status(topic)` per live topic; `scheduled` persists → track; once elapsed >= grace and not yet
  warned → `notify(warn)` once; any other status → drop tracking (a run that started, succeeded,
  or went terminal is none of the watcher's business). Iteration takes a snapshot of `topics()`
  so a registry mutated mid-sweep (a socket closing) cannot raise during iteration — a topic
  that vanished reads `not_found` next tick and is dropped.
- **Message:** `"the runner could not schedule compute for this run (the runner service is at
  capacity). The run has not started — stop it and retry later."` — generic, no internals.
- **Wiring:** `app.py::create_app` installs the sweep loop like `_install_orphan_reaper`
  (startup task, shutdown cancel, per-tick exception tolerated) gated on `settings.runner ==
  "k8s"` and `job_runner is not None`; registers two metrics via getter — `engine_stuck_runs`
  (gauge, returns to zero) and `engine_stuck_warned_total` (counter) — mirroring
  `register_reaper_metrics`.
- **New knob:** `Settings.run_stall_warn_after_s: float = 60.0` (env
  `URL4_CLOUD_RUN_STALL_WARN_AFTER_S`). One knob; the sweep cadence derives from it like
  `_TICKS_PER_GRACE` in the reaper (default `warn_after_s / 8`, min 1s). The knob is
  chart-exposed like every deploy knob (`values.yaml: config.runStallWarnAfterS` →
  `configmap.yaml` env entry → `values.schema.json`) — without the chart entries it could not
  be set in the deployed topology, the only topology with the bug.
- **Load bound (envelope):** one `read_namespaced_job` per live topic per tick. At the local
  ceiling (32 topics) and the derived ~15s tick that is ≈ 2 API reads/s worst case, each a
  `to_thread` call with the adapter's existing 10s request timeout — bounded and trivial.
- **Schedule-time hardening (honest about the port contract):** `ports.py` gains one
  engine-local exception, `RunnerScheduleUnavailable` — `JobRunnerAtCapacity` is NOT reused
  because its own docstring forbids cluster-backed runners from raising it. `K8sJobRunner
  ._schedule_blocking` adds one `except ApiException` — `status >= 500 or status == 429` →
  raise `RunnerScheduleUnavailable` from it; re-raise anything else unchanged. `rest/routes.py
  ::_schedule` adds the matching `except RunnerScheduleUnavailable` → `503 + Retry-After: 1`
  ("the runner could not schedule this run — retry later"), mirroring the `JobRunnerAtCapacity`
  branch. The REST layer gains no kubernetes import; `url4.streaming` gains no new type.
  (Doc-only: add the already-real 503 to `_START_RESPONSES`.)

### Explicitly not changing

- The wire protocol (`url4.streaming`), terminal-frame semantics, or the App's read-only broker
  posture — the notice channel is the only voice the App has, by design.
- The `screamingface` SDK transport — the existing `Log` rendering already surfaces the message.
  (Client-side TUI rendering of generic warnings beyond the plain `Log` path is a separate
  client-side nicety, not this unit.)
- Admission/backpressure policy (OME-908) and the quota/request-size fixes (OME-947 options 1–2).
- Warn-then-auto-stop of the stalled run (follow-up ticket).

## Acceptance criteria

1. A spine integration test (modeled on `test_orphan_reaper_spine.py`) proves a fake stuck
   runner yields exactly one `Log` WARN frame on the attached WebSocket with the generic body.
2. Unit tests of the policy with an injected clock: warn only once the elapsed monotonic time is
   `>= run_stall_warn_after_s` (boundary pinned at equality); warn at most once per run; no warn
   while status is `running`/`succeeded`/`failed`/`timed_out` or for `scheduled` younger than the
   bound; tracking state cleaned up on any non-stuck status; a per-topic `status()` failure is
   tolerated without warning or forgetting.
3. `test_app.py` proves the watch is absent when `settings.runner != "k8s"`.
4. `K8sJobRunner` maps `ApiException` (`status >= 500 or 429`) to the engine-local
   `RunnerScheduleUnavailable` (defined in `ports.py`), and `rest/routes.py::_schedule` maps it to
   a generic `503 + Retry-After: 1`; 409 (`JobAlreadyExists`) and permanent 4xx behavior
   unchanged; the REST layer gains no kubernetes import and `url4.streaming` gains no new type.
5. Metrics `engine_stuck_runs` returns to zero and `engine_stuck_warned_total` increments once
   per warned run.
6. The message body contains no internals (no "quota", "ns-ceiling", namespace or Pod names).
7. The full `screamingface-engine` gate passes — ruff, pyright, `check_layering.py` (with
   `run_stall` registered as a control-plane module), and pytest coverage ≥ 80% for
   `screamingface_engine`.
