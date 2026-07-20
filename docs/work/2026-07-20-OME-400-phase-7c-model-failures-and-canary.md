---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 7C typed model failures and evaluation canary

## Intent

Make live Fusion failures actionable without leaking provider secrets or spending the full case
budget after a clearly systemic error. The ScreamingFace engine will preserve a small safe error
contract from AI Gateway, and the SDK will use one first case as a canary before scheduling the
remaining cases concurrently.

## Planned changes

- Extend `packages/screamingface/apps/screamingface-engine` model execution errors with safe
  provider/model/code/retryable metadata decoded from AI Gateway responses.
- Preserve that metadata through URL4's plaintext error boundary without exposing raw upstream
  payloads, headers, credentials, or tokens.
- Update `packages/screamingface/src/screamingface/_execution.py` so the first selected case runs
  alone; permanent model/auth/configuration failures stop later cases immediately, while a
  transient canary gets one retry before repeated failure stops later cases.
- Add new append-only engine and SDK tests for safe propagation, malformed upstream errors,
  permanent canary failure, transient canary failure, and one-case evaluation.

## Test plan

- RED: a safe AI Gateway error becomes a typed engine failure with provider, model, stable code,
  and retryability; unsafe or malformed payloads fall back to a generic sanitized failure.
- RED: a permanent canary failure makes exactly one engine call and marks every later selected case
  as skipped with the same stable cause.
- RED: one transient canary failure is retried and can recover; two transient failures stop the
  remaining work without pretending that unexecuted cases ran.
- RED: successful and one-case evaluations retain their existing result order and semantics.

## Acceptance

- Researchers can distinguish authentication/configuration/model availability from retryable
  upstream failures without seeing secrets or raw provider payloads.
- No later case is submitted after a permanent canary failure.
- A transient first-case failure does not incorrectly classify the entire benchmark as permanent.
- Existing public Fusion, Run, Report, URL4 plaintext, and AI Gateway boundaries remain intact.
- All ScreamingFace format, lint, typecheck, test, and 95% coverage gates pass.

## Approved contract replacement

The owner approved replacing the prior four-wide first batch after reviewing the exact behavior.
The first case is now an isolated canary, so the earlier Phase 6C assertion that four authentication
failures may already be in flight must change to one call. The URL4 error envelope is not expanded:
its existing exact `{error: {code, message}}` shape remains the transport contract.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** `apps/screamingface-engine/src/screamingface_engine/gateway.py`, engine
  Gateway/judge/app tests, `src/screamingface/_execution.py`, the new Phase 7C canary tests, and
  owner-approved prior assertions whose behavior this phase replaces.
- **Commits:** `feat(screamingface): polish live benchmark workflows` (this commit).
- **Gates:** authoritative SDK gate green; 527 SDK tests at 95.26% coverage; 135 engine tests at
  95.55% coverage; all seven notebooks regenerate byte-identically; fixtures and wheel/sdist build
  pass.
- **Deviations:** URL4's exact `{error: {code, message}}` envelope was deliberately left unchanged;
  retryability is represented by stable permanent/transient error-code semantics instead of new
  wire fields. No AI Gateway or url4 package changes were required.
