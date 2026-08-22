# OME-948 — Implementation plan

- **Spec:** `docs/spec/2026-08-22-OME-948-run-stall-capacity-notice.md`
- **Linear:** https://linear.app/openmined/issue/OME-948/surface-a-generic-capacity-warning-when-a-runner-job-cannot-be
- **Branch:** `OME-948-run-stall-capacity-notice`
- **Stack:** `screamingface-engine` (`sdlc-python`)

## 1. RED — the policy proves a stuck run is warnable and warnable once

In `apps/screamingface-engine/tests/unit/test_run_stall.py`, build the policy against fakes
(an injected monotonic clock, a fake runner returning a scripted `JobStatus` per topic, a fake
`topics()` set, and a `notify` recorder):

- A topic whose status is `scheduled` from the first sweep: no warn until the elapsed time passes
  `run_stall_warn_after_s` (injected), then exactly one warn; further sweeps do not re-warn.
- A topic that transitions `scheduled` → `running`: tracking dropped, no warn ever.
- A topic that transitions to a terminal status (`failed`/`timed_out`/`succeeded`): tracking
  dropped.
- A topic that is `running` or terminal from the start: never tracked, never warned.
- `scheduled` younger than the bound: no warn; the next sweep after the bound warns (boundary
  pinned at equality: elapsed `==` `run_stall_warn_after_s` warns).
- A topic whose `status()` call raises: tolerated — no warn, tracking kept, the next sweep
  retries; other topics in the same sweep still get their turn.
- `topics()` empty: sweep is a no-op.
- Assert the emitted frame is the generic `LogEvent` (WARN) whose `data.body` contains the
  generic message and whose attributes carry no internal names.

Run against the unmodified code: these fail for lack of the module — the RED state.

## 2. GREEN — `run_stall.py` policy module

In `apps/screamingface-engine/src/screamingface_engine/run_stall.py`:

- TWO collaborator Protocols, mirroring the `RunReaper` style (`Audience`/`RunControl`): the
  runner as `async status(topic) -> JobStatus` (its only needed method), and the registry as
  `topics() -> frozenset[str]` + `notify(topic, frame)`. No FastAPI, no WS imports, no
  `run_stall`-side kubernetes anything — the module is substrate-blind and k8s-only by
  WIRING, never by code.
- TWO clock seams: monotonic `Callable[[], float]` (default `time.monotonic`) for the stall
  bound; `Callable[[], datetime]` (default `datetime.now(UTC)`) for the WARN frame's `time`.
  `_TICKS_PER_GRACE`-style derived cadence (`max(1.0, warn_after_s / 8)`).
- `RunStallWatcher` with `sweep()` returning the topics warned this sweep; per-topic
  `first_seen_stuck` and a `warned` set; `stuck_count` / `warned_total` properties for metrics;
  per-topic `status()` failure tolerated (log, keep tracking, neither warn nor forget);
  iteration over a snapshot of `topics()` so a mid-sweep registry mutation cannot raise.
- The warn frame is built with the existing `notices.warn(topic, clock, message, attributes)`.
- Module docstring documents the INVARIANTs: generic message only; symptom-based detection;
  advisory-only — a watcher failure can never affect the run itself.

## 3. GREEN — wire into the App + settings + metrics + chart

In `apps/screamingface-engine/src/screamingface_engine/ws/registry.py`:

- Add `topics() -> frozenset[str]`, a snapshot view over `_sessions` — the watch's bounded topic
  set (live audience), and the ONLY registry change.

In `apps/screamingface-engine/src/screamingface_engine/app.py`:

- Add `_install_run_stall_watch(app, registry, job_runner, settings)` modeled on
  `_install_orphan_reaper`: skip when `job_runner is None` or `settings.runner != "k8s"`;
  startup task + shutdown cancel; per-tick exceptions logged and tolerated; the watcher is
  handed the REAL registry (never the `interest` DI seam) — same invariant as the reaper.
- Register `engine_stuck_runs` gauge and `engine_stuck_warned_total` counter via a getter
  (mirror `register_reaper_metrics` in `metrics.py`).

In `apps/screamingface-engine/src/screamingface_engine/config.py`:

- `run_stall_warn_after_s: float = 60.0` with env `URL4_CLOUD_RUN_STALL_WARN_AFTER_S`.

In `apps/screamingface-engine/src/screamingface_engine/adapters/k8s.py`:

- `_schedule_blocking`: `except ApiException as exc:` → raise `RunnerScheduleUnavailable` (the
  new engine-local exception in `ports.py`) when `exc.status >= 500 or exc.status == 429`;
  re-raise unchanged otherwise. `JobRunnerAtCapacity` is NOT reused — its own docstring forbids
  cluster-backed runners from raising it.

In `apps/screamingface-engine/src/screamingface_engine/ports.py`:

- Add `class RunnerScheduleUnavailable(Exception)` — engine-local, substrate-transient, with a
  docstring noting why the url4 port type is not reused.

In `apps/screamingface-engine/src/screamingface_engine/rest/routes.py`:

- `_schedule`: `except RunnerScheduleUnavailable` → `ProblemException(503, "the runner could not
  schedule this run — retry later", headers={"Retry-After": "1"})`, mirroring the existing
  `JobRunnerAtCapacity` branch. Doc-only: add the already-real 503 to `_START_RESPONSES`.

In `.claude/scripts/check_layering.py`:

- Register `run_stall` in `CONTROL_PLANE` (and the header comment's module list) — a new
  control-plane root module; the gate fails without it.

In `apps/screamingface-engine/deploy/helm/`:

- `values.yaml` (`config.runStallWarnAfterS: 60`), `templates/configmap.yaml`
  (`URL4_CLOUD_RUN_STALL_WARN_AFTER_S`), `values.schema.json` (the new key) — the
  `orphanGraceS` pattern verbatim, so the knob is settable in the deployed topology.

## 4. Integration spine + regression

- `tests/integration/test_run_stall_spine.py` (modeled on `test_orphan_reaper_spine.py`): fake
  runner returning `scheduled`, real App via `create_app` with `Settings(runner="k8s")`, a real
  WS client attach; advance a fake clock past the bound, drive a sweep, assert the socket
  receives exactly one WARN `Log` frame with the generic body.
- `test_app.py`: the watch is absent when `settings.runner != "k8s"` (local mode untouched).
- `tests/unit/test_runners_k8s.py` (the canonical k8s-adapter suite with its shared fakes):
  `ApiException` 500/429 → `RunnerScheduleUnavailable`; the old
  `test_schedule_reraises_non_409_api_errors` characterization (500 propagated) is updated to
  the new contract — a permanent 4xx (400) still propagates unchanged.
- `metrics`: stuck gauge returns to zero after terminal; counter increments once per warned run.

## 5. Verify and deliver

- Run the focused `test_run_stall.py`, `test_run_stall_spine.py`, `test_app.py`,
  `test_runners_k8s.py` suites.
- Run `uv run .claude/scripts/run_gates.py screamingface-engine` from the repository root
  (ruff, pyright, `check_layering.py`, pytest ≥ 80%).
- Complete the ledger outcome, commit with `Refs: OME-948`, push, and open a PR.
- Add the close-discipline evidence to Linear; leave the final Done transition to merge
  automation.
