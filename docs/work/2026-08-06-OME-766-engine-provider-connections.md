---
ticket: OME-766
stack: url4-cloud
status: in_progress
started: 2026-08-06
finished:
---

# OME-766 — expose provider connections through the ScreamingFace Engine

## Intent

Extract the Engine half of the first Client's provider-connection flow into one direct-from-main,
security-focused review unit.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/connections/`
- `apps/url4-cloud/src/url4_cloud/rest/connections.py`
- the production/local composition roots and OpenAPI tag
- focused URL4 Cloud tests
- this unit's specification and plan

## Test plan

- Provider discovery and disconnected/connected projections.
- API-key create/replace and explicit OAuth authentication-method changes.
- Idempotent disconnect.
- Verified identity forwarding without Authorization forwarding.
- Provider-path and connection-id validation.
- Malformed payload, caller rejection, timeout, and unavailable-upstream mappings.
- Secret absence from public values and RFC 9457 responses.
- Local loopback and explicit-upstream composition.

## Acceptance

- All four public connection operations are available through the Engine.
- The Client-visible schema contains no AI Gateway-private or credential fields.
- Invalid path material is rejected before it can enter an upstream path.
- Only the `screamingface`-designated row is projected or mutated; other labels stay private.
- Validation and upstream failures remain typed and cannot echo a submitted key.
- Production and local composition close their connection clients cleanly.
- The complete URL4 Cloud gate is green.

## Outcome

- **Actual files:** the planned connection port, AI Gateway adapter, REST surface, composition,
  OpenAPI, focused tests, README contract, and the required task/spec/plan/work artifacts.
- **Commits:** one conventional feature commit on `OME-766-engine-provider-connections`.
- **Gates:** 53 focused tests passed; complete `url4-cloud` gate green.
- **Deviations:** OAuth account identity arrives as an object rather than a label string, so the
  adapter explicitly derives `email → name → sub` and discards raw provider metadata. Local
  connection operations use the loopback Gateway by default without changing the existing local
  model-catalog behavior.
- **External state:** OME-766 was owner-approved and created in `Pick Immediately`; no comment or
  status advancement was made.
