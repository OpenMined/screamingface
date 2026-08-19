---
ticket: OME-890
stack: screamingface-engine
status: done   # planned | in_progress | done | blocked
started: 2026-08-19
finished: 2026-08-19
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

## Outcome

- **Actual files:** as planned, plus two the plan did not foresee:
  - `deploy/helm/values.schema.json` — the chart validates `config` with
    `additionalProperties: false`, so `helm template` refused `orphanGraceS` until the
    schema declared it. Caught by rendering the chart, not by any Python gate.
  - `src/screamingface_engine/reaper.py` grew a second protocol, `RunControl` (see
    Deviations).
  - Not needed after all: no change to `metrics.py`'s existing collectors, and no new
    dependency (the invariant test is a scripted sequence, not `hypothesis`).

  Full set (19 files, +2849/-7): `ws/registry.py`, `ws/__init__.py`, `reaper.py` (new),
  `app.py`, `config.py`, `metrics.py`, `cli.py`, `.claude/scripts/check_layering.py`,
  `deploy/helm/{values.yaml,values.schema.json,templates/configmap.yaml}`, four new test
  files, four `docs/` artifacts.

- **Commits:**
  - `4c8274ef` — docs(work): add OME-890 spec, plan, ledger and task mirror
  - `96585d83` — feat(screamingface-engine): announce WS audience arrive/leave transitions
  - `db18912d` — feat(screamingface-engine): add the orphan-run reaper policy
  - `b622f868` — feat(screamingface-engine): stop runs whose audience never comes back
  - `6ebeaffa` — test(screamingface-engine): prove the orphan reaper end to end
  - `c6bc2ad4` — refactor(screamingface-engine): narrow the reaper's runner dependency

- **Gates:** `ALL GATES GREEN` on the final clean run (append-only check active) —
  ruff check · ruff format · pyright · check_layering · pytest.
  **1796 passed, 5 skipped**; coverage **93%** against the 80% floor.
  `reaper.py` and `ws/registry.py` are both at 100%. 40 tests added across four files.

- **Deviations:**
  1. **`create_app` hit ruff's `max-statements = 26`** (27 > 26) when the wiring call and the
     metrics registration were both added. Fixed the code rather than the gate: the
     metrics registration moved inside `_install_orphan_reaper`, which is where it belongs
     anyway — one function now owns everything about the reaper's presence in the App.
     Note for the next change: `create_app` now sits exactly at the 26-statement ceiling.
  2. **`RunControl` protocol added** during the wisdom review. `RunReaper` had declared the
     whole `JobRunner` ABC while calling two of its five methods, which also forced four
     `# type: ignore[arg-type]` escapes onto the tests' fakes — a Python-stack red flag.
     Narrowing to a two-method protocol removed all four.
  3. **Prior tests were edited** (comment/annotation only) to remove those escapes, which
     tripped the append-only gate. Raised as a Confidence-Gate decision and **approved by
     the owner**; that one gate run used `--skip-append-only`, and the final run passes the
     check naturally. No assertion, test name, or coverage was changed.
  4. **The uvicorn WS-ping assumption was verified, not assumed.** `ws_ping_interval=20` /
     `ws_ping_timeout=20` on uvicorn 0.52.1, with no override in `cli.py`. This is what
     makes subscriber-zero prompt (~40 s) for the sleep/partition cases rather than
     dependent on TCP retransmission (~15–30 min). Recorded as an `INVARIANT:` comment at
     both `uvicorn.run` call sites.
  5. **Non-vacuity of the headline test was proved directly.** Running the same spine with
     the reaper disabled shows the abandoned run *keeps* spending; with it enabled the run
     is reaped and the executor's call count stops moving. So the committed test fails
     without the feature.

- **Residual risk carried forward** (documented in the spec, not fixed here): multi-replica
  liveness needs a shared `SubscriberGate` before `replicaCount` can exceed 1 — the reaper
  logs that assumption at startup; a control-plane restart in k8s mode leaves an unreapable
  orphan bounded by `job_deadline_s`; and in-flight gateway calls still bill (OME-886).
