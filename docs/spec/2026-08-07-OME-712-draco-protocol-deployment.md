---
title: OME-712 — DRACO protocol and deployment
status: accepted
created: 2026-08-07
ticket: OME-712
---

# DRACO protocol and deployment

## Purpose

Install DRACO on the generic Engine Benchmark seam as ordinary URL4. The Engine owns Case
selection, private rubrics, Judge calls, deterministic aggregation, and auditable result
artifacts. The client supplies only a Candidate expression and never receives rubric content.

## Installed resources

- `draco` is the canonical 100-Case protocol with five independently seeded Judge passes per
  criterion.
- `draco/lite` selects two pinned Cases and ten axis-balanced criteria per Case with one Judge
  pass. It is directional and not comparable with canonical DRACO.
- `draco/smoke` selects one pinned Case and one criterion with one Judge pass. It proves wiring,
  not model quality.
- An explicit `limit=N` binds exactly the first `N` ordered Cases into the rendered URL4 and the
  reducer validates that exact selection. Limits are never inferred from surviving rows.

## Protocol invariants

- Candidate answers run through the shared Candidate Invocation adapter with the Benchmark's
  retrieval policy and exclusion list.
- The Judge sees one weight-free criterion at a time, never sibling criteria or rubric weights.
- Canonical Judge passes use stable seeds `1..5`, creating independent reusable cache slots;
  lite and smoke use seed `1`.
- Every Case is scored independently for each Judge pass and pass-level scores are averaged using
  the reference DRACO arithmetic.
- Missing, malformed, duplicated, misbound, under-covered, or failed Case evidence cannot publish
  a numeric Candidate score.
- A Case at the reference 95% valid-evidence threshold may score; lower coverage is unscored.
- Case artifacts retain input, output, finish reason, Check metadata, accepted evidence, and
  rejected raw Judge output.

## Asset and privacy contract

- `cases.json`, per-Case criteria, and per-Case rubrics are generated from a pinned dataset
  revision during benchmark-image construction.
- The Runner validates complete ordered Case/criteria/rubric alignment before registering any
  DRACO route or issuing a paid request.
- Rubrics and weights exist only in the benchmark Runner image. Control-plane discovery exposes
  metadata and executable URL4, never private grading assets.
- The benchmark image is version-coupled to the URL4 Cloud release and selected independently in
  the Runner Job template.

## Fidelity disclosure

The public canonical description must state that this reproduction is not paper-identical. It
uses the successor Judge model, provider-default reasoning, mixed native/Tavily retrieval, and a
host-only approximation of the reference blocklist. These deviations are hashed into the
Benchmark revision where they affect the executable protocol or prepared assets.

## Ownership

- `url4_cloud.benchmarks.draco` owns DRACO preparation, protocol construction, private runtime
  routes, deterministic scoring, and artifacts.
- The generic `url4_cloud.benchmarks` modules remain protocol-neutral.
- A dedicated composition module selects the concrete Benchmarks installed by this deployment.
- Runner retrieval and model-parameter extensions remain provider-neutral and contain no DRACO
  scoring rule.

## Acceptance

- Canonical, lite, and smoke render and execute as ordinary URL4 Candidate Result producers.
- Exact Case and criterion selections are deterministic and validated twice: at installation and
  reduction.
- Broken assets, missing Judge routes, and unavailable retrieval fail before model spend.
- Reference score, pass-rate, accuracy, axis, coverage, and sample-deviation metrics match the
  pinned reference implementation.
- The complete URL4 Cloud quality gate and benchmark-image/Helm rendering checks pass from the
  final non-stacked branch.
