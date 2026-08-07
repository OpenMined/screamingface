---
ticket: OME-712
stack: url4-cloud
status: done
started: 2026-08-07
finished: 2026-08-07
---

# OME-712 — DRACO protocol and deployment

## Intent

Install the pinned DRACO benchmark as ordinary Engine-owned URL4, with deterministic scoring,
auditable case evidence, inexpensive lite and smoke variants, and a separate Runner image that
keeps private rubrics away from the control plane.

## Planned changes

- Add the DRACO definition, private runtime routes, preparation, scoring, verdict, and artifact
  modules under `apps/url4-cloud/src/url4_cloud/benchmarks/draco/`.
- Extend the Runner's declared model parameters and retrieval mechanisms only as required by the
  DRACO candidate and Judge calls.
- Build and publish a benchmark Runner image paired with the control-plane release; wire Helm to
  schedule that image without exposing rubric assets from REST.
- Install canonical `draco`, directional `draco/lite`, and structural `draco/smoke` resources.

## Test plan

- Prove pinned preparation, rubric privacy, exact Case and criterion selection, five independent
  seeded Judge passes, official score arithmetic, failure integrity, and lossless artifacts.
- Prove model parameters reach AI Gateway with correct types and native/Tavily retrieval remains
  route-declared and fail-closed.
- Prove missing or inconsistent assets fail installation before any model request.
- Render the Helm chart and build both deployment images in CI.
- Run URL4 Cloud formatting, lint, type, layering, full tests, and coverage gates.

## Acceptance

- Every installed DRACO expression runs as ordinary URL4 and returns a Candidate Result.
- Empty, incomplete, misbound, or under-covered grading cannot publish a numeric score.
- A resource specialized with `limit=N` binds and validates exactly N ordered Case results.
- Canonical DRACO uses five stable seeded Judge cache slots; lite and smoke use one.
- Rubrics exist only in the benchmark Runner image and are never addressable URL4 data.
- Public descriptions disclose any deliberate differences from the paper protocol.

## Outcome

- **Actual files:** the DRACO definition/runtime/scoring/artifact modules, focused tests, required
  Runner parameter and retrieval support, and the paired benchmark-image/Helm/release wiring.
- **Commits:** this unit's commit (`Refs: OME-712`).
- **Gates:** DRACO/runtime focused suites pass; Ruff, Pyright, and layering pass. The full suite is
  652 passed / 5 skipped with two expected model-catalog failures until merged AI Gateway PR #520
  is present in the branch ancestry.
- **Deviations:**
  - Public Case browsing was removed because the control plane does not carry benchmark assets;
    it remains deferred to a dedicated public-case source.
  - The public benchmark description discloses the successor Judge model, provider-default
    reasoning, mixed native/Tavily retrieval, and host-only approximate blocklist, so results are
    not presented as paper-identical.
  - The reference 95% coverage floor is preserved: a Case at exactly 95% valid Judge evidence may
    score, while lower coverage and every Candidate/Case execution failure remain unscored.
