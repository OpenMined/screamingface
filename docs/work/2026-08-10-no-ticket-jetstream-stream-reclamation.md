---
ticket: none  # owner directive 2026-08-10: "No need to create new linear tickets, just spec/design/implement the fix"
stack: url4-cloud
status: done
started: 2026-08-10
finished: 2026-08-10
---

# Reclaim JetStream streams so runs stop failing with 10047

## Intent

Production fails every run with `err_code=10047 insufficient storage resources available`.
Each run creates a JetStream stream reserving 256 MiB against a 10Gi store — a hard ceiling of
40 streams — and nothing reclaims them: `max_age` expires messages but never the stream object,
and the only delete path (`DELETE /`) needs a capability token that expires after 60 s, so any
run longer than a minute can never tear its own stream down. This unit makes the runner reclaim
its stream, adds a lazy sweep so crashed runs cannot leak indefinitely, and cuts the per-stream
reservation to 50 MB (ceiling 40 → ~200).

Spec: `docs/spec/2026-08-10-url4-cloud-jetstream-stream-reclamation.md`

## Planned changes

- `apps/url4-cloud/src/url4_cloud/adapters/jetstream.py` — `DEFAULT_STREAM_MAX_BYTES` 256 MiB →
  50 MB; correct the false `max_age` invariant comment; catch `APIError` err_code 10047 in
  `ensure_stream`, sweep orphans, retry once; add `_sweep_orphans`.
- `apps/url4-cloud/src/url4_cloud/runner/main.py` — after `lifecycle.run`, wait
  `URL4_RUNNER_STREAM_GRACE_S` (default 60 s) then `delete_stream`, in a `finally`.
- `apps/url4-cloud/tests/unit/test_jetstream_reclamation.py` — new.
- `apps/url4-cloud/tests/unit/` — runner teardown coverage.

## Test plan

Failing first, in this order:

1. `ensure_stream` sweeps + retries once on 10047, succeeding when the sweep frees a stream.
2. `ensure_stream` re-raises when the sweep frees nothing (no infinite retry).
3. `ensure_stream` still swallows `BadRequestError` (stream already exists).
4. Regression: `ServerError(500, err_code=10047)` is NOT caught by the `BadRequestError` arm.
5. Orphan test — `messages == 0, last_seq > 0` swept; `last_seq == 0` (fresh) NOT swept.
6. Orphan test — last frame `ai.url4.terminated` older than grace swept; newer NOT swept.
7. Runner deletes its stream after the run, and only after the grace delay.
8. Runner still deletes on a failed/timed-out run.
9. `DEFAULT_STREAM_MAX_BYTES == 50_000_000` and reaches `add_stream`.
10. Local-mode (`InMemoryEventStream`) teardown unchanged — guards the MRO trap.

## Acceptance

- All ten tests green; every pre-existing test unmodified and still green.
- `run_gates.py url4-cloud` green (ruff, ruff format, pyright, layering, pytest ≥80% cov).
- `packages/url4` untouched — reclamation policy stays in the app layer.

## Outcome

- **Actual files:**
  - `apps/url4-cloud/src/url4_cloud/adapters/jetstream.py` — as planned, plus
    `_declare`/`_terminated_before_grace` extracted (PLR0911 return-count gate).
  - `apps/url4-cloud/src/url4_cloud/runner/main.py` — as planned; `run_and_reclaim` takes a
    `run_once` thunk so the finally-path invariant is testable without an executor fake.
  - `apps/url4-cloud/src/url4_cloud/subjects.py` — **unplanned**: added `owns_stream` /
    `topic_of`. The sweep enumerates every stream on the broker, so it needs the inverse of
    `stream_for` and an ownership test; keeping both in the naming module matches that
    module's stated purpose rather than hand-formatting the prefix at the call site.
  - `apps/url4-cloud/tests/unit/test_jetstream_reclamation.py` (11 tests) — new.
  - `apps/url4-cloud/tests/unit/test_runner_stream_reclamation.py` (7 tests) — new.
- **Commits:** `a78cab5d` — fix(url4-cloud): reclaim JetStream streams so runs stop failing
  with 10047. (This ledger's own sha lands in the follow-up doc commit; the branch squash-merges.)
- **Gates:** `run_gates.py url4-cloud` → ALL GATES GREEN (append-only check, ruff check, ruff
  format --check, pyright, check_layering, pytest with `--cov-fail-under=80`). 18 new tests
  pass; no pre-existing test modified (confirmed by the append-only gate).
- **Deviations:**
  1. `subjects.py` touched (above) — a shared leaf, additive only; layering gate green.
  2. `URL4_RUNNER_STREAM_GRACE_S` is read from the Job env but **not plumbed through the Helm
     chart**. The 60 s default is correct, so this only limits tuning; deliberately left out
     of scope. Follow-up if operators need to tune it.
  3. `packages/url4` untouched, as specified — reclamation policy stayed in the app layer and
     `delete_stream` was NOT promoted to `EventPublisher` (MRO trap, spec §3.1).

## Review round (2026-08-10)

Two independent reviewers (senior + adversarial). Findings fixed in this unit:

- **C1 — the backstop could not clear its own outage.** `messages == 0, last_seq == 0` is not
  only the FRESH state; it is the PERMANENT state of a topic whose runner never published. The
  control plane declares the stream at attach, before the Job runs, so an ImagePullBackOff or a
  world-resolution crash stranded a stream `max_age` can never reclaim. Fixed with a third
  orphan test on `StreamInfo.created` (server-side) + `consumer_count == 0`. **My spec §3.3 was
  wrong** that no timestamp existed — corrected in the spec.
- **I1 — `activeDeadlineSeconds == deadline_s`**, so k8s SIGKILLed the pod during the drain
  grace and EVERY timed-out run leaked. Grace moved to `job_env` (one writer) and the pod
  deadline widened by grace + 30 s margin.
- **I2 — concurrent sweeps.** `NotFoundError` on delete means a racing sweep already freed the
  space; not counting it made the loser re-raise 10047 and fail a client for nothing.
- **I3 — `except APIError` too narrow.** `delete_stream` connects lazily, so `NoServersError` /
  `ConnectionClosedError` / `nats.errors.TimeoutError` escaped — turning a good run into a
  Failed Job, and on the failure path *replacing* the run's exception. Widened to `Exception`.
- **I6 — `streams_info()` reads one page** (server caps at 256). Now paginated.
- Sweep logging: only when something was reclaimed, and it names the streams.

**Two prior tests changed (owner-approved — SDLC rule 5 Confidence Gate):**
1. `test_runners_k8s.py::test_schedule_builds_a_run_once_named_spec` asserted
   `activeDeadlineSeconds == 57600`, pinning the exact equality that was the defect. Owner chose
   "widen the pod deadline" over "shrink the run budget", so the run keeps its full requested
   budget and the pod outlives it by the teardown allowance.
2. `test_runner_job_env_isolation.py` hardcoded the per-run env set; extended by
   `STREAM_GRACE_S`. Intent (no deploy-time vars in `_env`) unchanged, assertion still exact.

Gates were therefore run with the documented `--skip-append-only` flag.

**Deferred, with owner agreement:**
- **I4** — spec §3.5's RFC 9457 503 mapping is still not implemented; 10047 surfacing past the
  sweep is a raw 500 on the REST path. Touches `rest/`, deliberately out of this diff.
- I5 (`_ensured` not invalidated when another process deletes a stream — a replay/attach-path
  defect, not data loss mid-run), M7 (runner-vs-control-plane clock skew on the terminated
  test; `consumer_count` would be skew-free), M8 (no SIGTERM handler, so `stop` bypasses the
  `finally` — though `DELETE /` covers that path today), M10 (two deployments sharing a broker
  sweep each other).
- Reviewer recommendation worth taking: every test runs against a hand-written `_FakeJetStream`,
  which cannot catch a wrong assumption about JetStream itself — and two of the findings above
  were exactly that. An integration test against the kind rig would close that class.

## Notes for the next iteration

- The fix is **not retroactive**: streams already stranded in production must be cleared once
  by hand (spec §6). The lazy sweep only fires once the store is exhausted again.
- Residual risk stands: a pod killed before its `finally` still leaks until the next sweep.
  The shared-stream redesign (one stream, subject per run, `max_msgs_per_subject`) removes
  the failure mode outright and remains the recommended follow-up.
