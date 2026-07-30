---
ticket: OME-620
stack: screamingface
status: in_progress
started: 2026-07-28
finished:
---

# OME-620 — Expose local catalogue discovery

## Intent

Make the isolated DRACO-Lite Client demo discover its Engine's available Models and Benchmarks
through the intended typed, lazy interface without exposing AI Gateway or Provider Credentials.

## Planned changes

- Add typed catalogue values and Client catalogue adapters.
- Add module-level `sf.models` and `sf.benchmarks` facades.
- Add focused Client tests and update public-interface documentation.
- Add a loopback-only Engine credential fallback for model catalogue discovery.
- Keep the public benchmark identity unversioned (`draco-lite`) and use the manifest digest as
  the immutable reproducibility pin.

## Test plan

- Decode valid Model and Benchmark catalogues into immutable values.
- Reject malformed catalogue payloads with typed errors.
- Verify sync, async, explicit-Client, and lazy module-level forms.
- Verify local Engine discovery without a Client-side Provider Credential.

## Acceptance

- `sf.models.list()` and `sf.benchmarks.list()` work against the local demo Engine.
- Discovery and planning use the same canonical `draco-lite` identifier.
- The Client never calls AI Gateway.
- Hosted credential behavior is unchanged.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** pending
- **Commits:** pending
- **Gates:** pending
- **Deviations:** pending
