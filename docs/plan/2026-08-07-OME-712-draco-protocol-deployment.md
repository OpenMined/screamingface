---
title: OME-712 — DRACO protocol and deployment implementation plan
status: completed
created: 2026-08-07
ticket: OME-712
spec: docs/spec/2026-08-07-OME-712-draco-protocol-deployment.md
---

# DRACO protocol and deployment implementation plan

## Goal

Add the first scored protocol behind the generic Engine Benchmark interface without moving
benchmark semantics into URL4, AI Gateway, or the ScreamingFace client.

## Sequence

1. Pin and prepare public Case inputs, private criteria, rubrics, retrieval policy, and revision
   inputs in a separate benchmark image.
2. Implement weight-free Judge tasks, schema-validated verdict binding, exact Case envelopes, and
   lossless Case artifacts.
3. Port the reference DRACO score arithmetic as deterministic pure functions and prove parity with
   focused vectors.
4. Build canonical, lite, and smoke URL4 protocols with exact ordered selection and stable seeded
   Judge passes.
5. Validate all selected assets and required routes when the Runner world is installed, before any
   Candidate or Judge request.
6. Add only the provider-neutral model parameters and retrieval mechanisms required by the
   declared protocols.
7. Publish the paired benchmark image and wire Runner Jobs to it without exposing rubrics to the
   control plane.
8. Verify failure integrity, privacy, artifacts, protocol rendering, Helm wiring, and the complete
   URL4 Cloud quality gate.

## Landing boundary

- Modify URL4 Cloud, its benchmark image/deployment wiring, tests, and OME-712 artifacts.
- Do not add DRACO behavior to URL4 grammar, AI Gateway, or the client.
- Keep concrete DRACO registration in deployment composition; generic Benchmark modules remain
  reusable by other Engine deployments.
- Reconstruct the final PR directly from current `main` after the generic Benchmark foundation
  lands; do not publish this dependency snapshot as a stacked PR.

## Verification

- Focused DRACO preparation, assets, tasks, verdict, envelope, aggregation, artifact, lite, and
  smoke suites.
- Runner parameter and retrieval-policy tests.
- Ruff lint and formatting, Pyright, full URL4 Cloud tests, coverage, layering, image build, and
  Helm rendering.
