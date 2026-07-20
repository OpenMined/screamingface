---
ticket: OME-400
stack: screamingface
status: in_progress
started: 2026-07-20
finished:
---

# OME-400 — Phase 7A live local acceptance

## Intent

Make the local ScreamingFace stack safe and predictable to operate, then validate the real public
engine boundary before an owner-driven provider and GPQA quickstart run. Starting or inspecting
the stack must not attach lifecycle to a terminal, remove stored connections, contact AI Gateway
directly from the SDK, or conceal an external provider/Gateway blocker.

## Planned changes

- Update `packages/screamingface/apps/screamingface-engine/dev.sh` with explicit default/start,
  restart, down, status, and logs commands.
- Update `packages/screamingface/apps/screamingface-engine/README.md` with the exact lifecycle and
  credential-volume guarantees.
- Add `packages/screamingface/tests/test_phase7a_dev_script.py` as an append-only command-contract
  suite using a fake Docker executable.
- Record the approved Phase 7A boundary in the OME-400 architecture plan and task mirror.
- Do not modify generated or user-executed notebooks in this unit.

## Test plan

- RED: default and explicit start run detached build with Compose health waiting.
- RED: restart performs a project-scoped orphan cleanup followed by the same healthy start.
- RED: down, status, and logs map to their exact non-destructive Compose commands.
- RED: unknown arguments fail with concise usage and no Docker call.
- INVARIANT: no supported command passes `--volumes`, `-v`, or any global Docker cleanup command.
- GREEN: run the new tests, full SDK/engine suites, and authoritative ScreamingFace gate.
- LIVE: restart the existing stack, verify all three Compose services healthy, then verify engine
  `/healthz`, registry, and connection status through port 4404 without provider spend.

## Acceptance

- `./dev.sh` is idempotent, detached, and waits for health; interrupting a log view cannot stop
  services.
- `./dev.sh restart` recovers running, stopped, and partially created stacks without deleting the
  `aigateway-data` volume.
- All lifecycle commands are scoped to the `screamingface-engine-dev` Compose project.
- Live public engine health, discovery, and sanitized connection status pass.
- Actual provider authorization and the five-case GPQA run remain explicit owner-driven acceptance
  steps; failures are recorded by their real engine/Gateway category with no SDK fallback.

## Live acceptance progress

- `./dev.sh restart` rebuilt and recreated the running stack, waited for all three health checks,
  and returned successfully.
- The `screamingface-engine-dev_aigateway-data` volume retained its original
  `2026-07-20T09:34:47Z` creation identity across restart.
- Engine `/healthz`, `/.well-known/screamingface`, and `/v1/connections` returned their approved
  public/sanitized responses through port 4404. Owner-driven Gemini and Anthropic OAuth completed,
  and both connections remained active across a full Compose restart.
- A real SDK evaluation requiring Codex and Gemini raised one `connection_required` error naming
  both providers and models. Engine access logs showed only registry and connection reads and no
  `/v1` URL4 evaluation request.
- Seven append-only lifecycle tests, the authoritative ScreamingFace gate, and all 119 engine tests
  at 95.76% coverage pass.
- Codex's corrected live start returns `pending` with
  `http://localhost:1455/auth/callback`; port 1455 reaches the healthy engine listener. The probe
  connection was deleted after verification so the notebook can start a fresh authorization.
- Owner completion of the corrected Codex authorization and the GPQA quickstart remain pending.

## Codex OAuth correction

- Live owner acceptance connected Gemini and Anthropic successfully, proving the public engine
  callback bridge and persistent Gateway store work end to end.
- Codex authorization was rejected by the provider before callback because the engine requested
  `http://localhost:4404/auth/callback`; the Gateway's Codex OAuth client permits only its
  registered loopback ports `1455` and `1457`.
- The owner approved correcting the prior Phase 6B test contract. Codex will use the validated
  engine-owned callback `http://localhost:1455/auth/callback`, with Compose publishing that host
  port to the existing engine listener.
- Callback credentials must not appear in access-log request targets. Engine access logging will
  be disabled and the engine-to-Gateway completion will use the Gateway's existing JSON
  exchange-code route. No AI Gateway source change is permitted or required.
- RED additions cover the provider-specific redirect, deployment port wiring, JSON callback
  relay, invalid redirect settings, and secret-safe Uvicorn configuration before implementation.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** updated the development lifecycle script and README; added persistent,
  loopback-only Compose networking and the registered Codex callback port; made callback relay and
  access logging secret-safe through engine settings, CLI, application, and Gateway-adapter code;
  added lifecycle and Codex OAuth regression tests; and updated the current plan/task records.
- **Commits:** `feat(screamingface): polish live benchmark workflows` (this commit).
- **Gates:** authoritative SDK gate green; 527 SDK tests at 95.26% coverage; 135 engine tests at
  95.55% coverage; all seven notebooks regenerate byte-identically; fixtures and wheel/sdist build
  pass. The running Compose services are healthy, and read-only health, registry, and sanitized
  connection probes pass without model spend.
- **Deviations:** the provider rejected the original Codex callback port, so the owner approved
  the separately tested `localhost:1455` correction. Corrected Codex authorization completion and
  the five-case live GPQA quickstart remain owner-driven acceptance steps, so this ledger stays
  open.
