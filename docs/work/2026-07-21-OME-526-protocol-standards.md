---
ticket: OME-526
stack: url4-cloud
status: in_progress
started: 2026-07-21
finished:
---

# OME-526 — protocol standards alignment + docs/protocol.md

## Intent
Align the url4-cloud wire protocol to named, well-known standards and capture the format + the
standards-as-decisions in `apps/url4-cloud/docs/protocol.md` (ADR-style). Envelope → CloudEvents
1.0; spans → OTel GenAI; logs → OTel Logs Data Model; trace ids → W3C Trace Context; REST errors
→ RFC 9457; JWT → RFC 7519 registered claims; transports → CloudEvents WS/NATS bindings; ops →
k8s probes / OpenMetrics / k8s+OCI labels. Cost stays a custom event (no standard; prior art cited).

## Planned changes
- `apps/url4-cloud/docs/protocol.md` — the protocol reference + decisions (this unit).
- (follow-on, same ticket) `url4_cloud_protocol` models rewritten to the CloudEvents/OTel form;
  spec §7 updated; downstream units (nats/runner/ws/rest/docs) built on the aligned contract.

## Test plan
- Doc unit: no code; the model rewrite (follow-on) keeps `run_gates.py url4-cloud` green with
  updated tests (CloudEvents round-trip; gen_ai.* attribute keys; problem+json errors).

## Acceptance
- `docs/protocol.md` documents every layer with its standard + reference + rationale, and marks
  the one conscious deviation (cost). Owner can trace each field to a spec clause.

## Outcome (fill at the end — required before COMMIT)
- **Actual files:** `apps/url4-cloud/docs/protocol.md` (decision record); `url4_cloud_protocol/`
  {`envelope`,`taxonomy`,`signals`,`unions`,`__init__`}`.py` rewritten to CloudEvents 1.0 + OTel;
  `tests/unit/test_protocol.py` updated; spec §7 annotated; plan updated.
- **Commits:** see the OME-526 commit on `OME-513-url4-cloud`.
- **Gates:** quality gates GREEN (ruff · format · pyright · pytest+cov). **Append-only check
  intentionally skipped (`--skip-append-only`)** — this is a Confidence-Gate contract change:
  OME-526 supersedes the OME-515 bespoke envelope (owner-authorized: "implement it in protocol").
- **Deviations:** OME-515's protocol tests were replaced (contract superseded, not weakened — the
  invariants remain). `gen_ai.*` wire keys via `validation_alias`+`serialization_alias` (keeps
  Python field-name construction + pyright required-ness). Downstream units (nats/runner/ws/rest/
  docs) will be built on this aligned contract (workflow relaunch with updated model references).
