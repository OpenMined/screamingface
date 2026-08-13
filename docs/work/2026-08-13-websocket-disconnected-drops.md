---
ticket: none filed — investigation of OME-806
stack: screamingface, url4-cloud
status: done
started: 2026-08-13
finished: 2026-08-13
---

# Attribute and remove `websocket_disconnected` drops

## Intent

A user reported frequent `ExecutionError: SF Engine WebSocket disconnected before the Run
completed` when running a pipeline. OME-806 tracks the symptom and proposes three candidate
causes, none of which turned out to be the two that are demonstrable in the code. This unit
removes those two and makes every remaining candidate self-identifying, so the rest can be
settled with evidence instead of argument.

## Planned changes

- `packages/screamingface/src/screamingface/_engine/transport.py` — explicit `max_size`;
  re-mint the capability after `reauthenticate()`; close code + elapsed time in the error.
- `packages/screamingface/tests/test_transport_disconnect_diagnosis.py` — new, self-contained.
- `apps/url4-cloud/src/url4_cloud/logs.py` — new; log configuration for both modes.
- `apps/url4-cloud/src/url4_cloud/cli.py` — configure logging before dispatch.
- `apps/url4-cloud/src/url4_cloud/ws/bridge.py` — record how each connection ended.
- `apps/url4-cloud/src/url4_cloud/ws/endpoint.py` — record refused handshakes.
- `apps/url4-cloud/src/url4_cloud/rest/routes.py` — record run scheduled / stop requested.
- `apps/url4-cloud/tests/unit/test_ws_stream_diagnostics.py` — new, self-contained.
- `apps/url4-cloud/tests/unit/test_logs_configuration.py` — new, self-contained.

## Test plan

Failing first, in this order:

- A result body at exactly `result_cap` is delivered (sync and async).
- An Access challenge is retried with a freshly minted capability (sync and async).
- A dropped stream reports its close code and elapsed time.
- A finished stream is recorded with duration, frame count and heartbeat count.
- An attach is recorded with the cursor it resumed from.
- A refused handshake is recorded rather than silently closed.
- An INFO record from the App reaches a handler; configuring twice does not double it; a
  foreign handler does not suppress ours; the level is settable from the environment.

## Acceptance

- All of the above fail against `origin/main` and pass after the change.
- `run_gates.py screamingface` and `run_gates.py url4-cloud` both green.
- The four causes produce four distinguishable error texts.

## Outcome

- **Actual files:** as planned, plus `docs/spec/2026-08-13-websocket-disconnected-drops.md`
  and this ledger.
- **Gates:** `screamingface` — ALL GATES GREEN (8 gates, 756 tests, 95% coverage floor).
  `url4-cloud` — ALL GATES GREEN (6 gates, 1390 tests, 80% floor, layering check).
- **Verification beyond the suites:**
  - Each new test was confirmed to fail with the fix stashed and pass with it restored.
  - L1 end-to-end against real uvicorn, the real app and a real `websockets` client: a
    pre-fix client (`max_size=2**20`) refuses the capped result and the App logs
    `outcome=client close 1009 'frame exceeds limit of 1048576 bytes'`; a post-fix client
    receives the full 1,048,884 byte frame and closes 1000. Confirms both that the fix works
    through real framing and that mechanism A is attributable from the Engine alone, with no
    SDK update deployed.

## Deviations

- **No Linear issue and no `docs/tasks/` mirror.** The owner directed an exploratory pass and
  explicitly deferred filing. OME-806 already tracks the symptom; this branch references it
  without claiming to close it, since two of its candidate causes remain unresolved.
- **The append-only gate fired once, and was obeyed rather than skipped.** The first attempt
  extended the shared `packages/screamingface/tests/protocol_server.py` with two new modes.
  That edits a prior fixture, which rule 5 forbids. The work was reverted and rewritten as one
  self-contained test file with its own Engine stub — the house pattern. `--skip-append-only`
  was NOT used. The restructure also proved better: the scenarios are investigation-specific
  and do not belong in the shared fixture.
- **A defect was found while testing the fix, not before.** `logs.configure` first guarded
  idempotence with `if not logger.handlers`, which silently installs nothing whenever any other
  component attached a handler first — the exact failure it exists to prevent. Caught because
  the new tests passed alone and failed in the full suite, where `test_cli` had already
  configured the logger. Now keyed to a marker on our own handler, with a regression test.
- **The engine logging was nearly shipped inert.** Verified before recommending a deploy that
  `uvicorn.run()` leaves root without a handler and `url4_cloud` records never reach one, so
  every INFO line added here would have been discarded in production. `logs.py` was added in
  response; without it the observability half of this unit would have been a no-op.
- **Scope held.** Three adjacent defects were found and deliberately left out, each recorded
  in the spec's out-of-scope section: reconnect-after-drop, the stop fallback that cannot
  authenticate past 60 seconds, and advisory frames dropped under backpressure.
- **Two stacks in one branch.** Rule 8 would normally split a cross-cutting change into an
  epic with one sub-issue per app. Kept together here because the observability and the fixes
  were verified as one system; splitting into two PRs remains available and was recommended.
