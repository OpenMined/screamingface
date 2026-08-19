---
ticket: OME-890
stack: screamingface-engine
status: planned   # planned | in_progress | done | blocked
started: 2026-08-19
finished:
---

# OME-890 — Stop Engine runs that keep spending after their client dies

## Intent

An Engine run's lifetime is tied to nothing. The 428 gate
(`rest/routes.py::_require_subscriber`) proves an audience exists when the run starts, and
then the Engine never asks again. A client that dies before it can send `ai.url4.stop` —
`kill -9`, a Jupyter kernel restart, laptop sleep, a network partition, or a
single-candidate run with no `DELETE /` fallback — leaves the run alive. The run keeps
issuing paid model calls until `job_deadline_s` (57600 s = 16 h). It also holds one of
`local_max_concurrent_runs` slots and keeps saturating the gateway's per-provider slots.

This unit ties a run's lifetime to its audience. When a topic's last WebSocket subscriber
disconnects, a grace window opens. If no subscriber returns before the window closes, the
Engine stops the run through the same idempotent `JobRunner.stop` the explicit paths use.
The run terminates as a clean `Terminated(stopped)`.

## Planned changes

Source:

- `src/screamingface_engine/ws/registry.py` — add the `AudienceListener` protocol, a
  `listen()` composition-root seam, and the 0→1 / 1→0 transition calls in `add`/`remove`.
- `src/screamingface_engine/reaper.py` — NEW. `RunReaper`: arm/disarm, `sweep()`, and the
  owned background loop (`start` / `aclose`).
- `src/screamingface_engine/app.py` — build and wire the reaper in `create_app`; register
  `on_startup` / `on_shutdown`.
- `src/screamingface_engine/config.py` — add `orphan_grace_s: float = 120.0` (`ge=0`;
  0 disables).
- `src/screamingface_engine/metrics.py` — reaped-runs counter and armed-topics gauge.
- `.claude/scripts/check_layering.py` — add `reaper` to `CONTROL_PLANE`.
- `deploy/helm/values.yaml` + `templates/configmap.yaml` — expose `config.orphanGraceS`.
- `cli.py` — comment that uvicorn's WS ping defaults are load-bearing (see Acceptance).

Tests:

- `tests/unit/test_ws_registry_audience.py` — NEW (batch 1).
- `tests/unit/test_reaper.py` — NEW (batch 2).
- `tests/unit/test_reaper_wiring.py` — NEW (batch 3).
- `tests/integration/test_orphan_reaper_spine.py` — NEW (batch 4).

## Test plan

Written RED first, in four batches. No test uses a sleep: the clock is injected and
`sweep()` is called directly.

Batch 1 — registry transitions (the arm/disarm signal):

- `audience_arrived` fires only on 0→1; `audience_left` only on 1→0.
- Two subscribers, one leaves → no `audience_left` (audience is not empty).
- `add_notifier` creates a session at 0 subscribers → the next `add` still reads as 0→1.
- `remove` on an absent session is a no-op and fires nothing (no double-fire).

Batch 2 — reaper policy:

- Arm, advance the clock past the window, sweep → `stop` called exactly once.
- Audience returns before expiry → no stop, nothing armed.
- At expiry the registry reports a subscriber → no stop (claim-then-verify).
- `exists()` is False → no stop (already terminal, or never started).
- Flap (leave/arrive × N) → exactly one armed entry, last arm wins.
- Sweep before expiry → nothing happens.
- `stop()` raises → the topic is re-armed and the next sweep retries.
- Second sweep after a reap → no second stop (idempotent).
- A topic that never started a run → no stop, no error, entry dropped.
- INVARIANT, over a scripted sequence of add/remove/sweep/clock steps: an armed topic
  never has a subscriber, and the deadline map never grows without bound.

Batch 3 — lifecycle and wiring:

- THE TRAP: `create_app(interest=FixedGate(False))` plus a real subscriber in the
  registry → zero stops. Pins the mistake that would reap the whole fleet.
- `orphan_grace_s=0` → no reaper is built. `runner="none"` → no reaper is built.
- `aclose()` cancels and awaits the loop; no "task was destroyed" warning.
- `start()` twice → one task.
- The loop survives a sweep that raises and keeps ticking.

Batch 4 — integration, on the local spine:

- Abrupt WS close (1006), no reconnect → the run terminates `stopped`, and the executor
  issues no further calls after the stop.
- Close, then reattach with `from_sequence` inside the window → the run stays alive and
  frames resume.
- In-band `ai.url4.stop` and `DELETE /` behave exactly as today; no double stop.
- Capacity: saturated slots are released after a reap, so a schedule that returned 503
  now succeeds.

## Acceptance

- A run whose WS subscriber disappears abnormally and never returns is stopped within the
  grace window. No further gateway calls are issued after the stop.
- A subscriber that reconnects inside the window resumes untouched.
- Clean in-band stop and `DELETE /` behaviour are unchanged.
- The grace period is operator-configurable. Reap events are logged with topic + reason.
- All card gates green: `uv run .claude/scripts/run_gates.py screamingface-engine`.
- Load-bearing assumption recorded: uvicorn's `ws_ping_interval`/`ws_ping_timeout`
  defaults (20 s / 20 s, verified on uvicorn 0.52.1) are what close a partitioned peer's
  socket and therefore what make subscriber-zero a prompt signal. Disabling them would
  silently regress the partition path.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** <sha — message>
- **Gates:** <run_gates.py result line / counts>
- **Deviations:** <anything that differed from the plan, or "none">
