---
title: Implement linked Benchmark and Candidate expressions
ticket: OME-605
status: active
date: 2026-08-01
spec: ../spec/2026-08-01-OME-605-benchmark-protocol-contract.md
---

# Implement linked Benchmark and Candidate expressions

- [x] Pin `screamingface.benchmark.v1`, the JSON Benchmark resource, `url4`, `$candidate`, `$input`,
  and `/candidate` with contract tests and reject the superseded manifest/plan vocabulary.
- [x] Prove `/candidate` inside the real URL4 Cloud world with Model and nested Fusion expressions,
  two ordered invocations, cancellation, usage, errors, concurrency, and recursion/call limits.
- [x] Replace the YAML Benchmark detail and Candidate-specific POST with one cacheable
  `GET /v1/benchmarks/{id}?limit=N` returning metadata plus a canonical Benchmark expression.
- [x] Compile Candidate expressions in the SDK, parse both sides into URL4 ASTs, bind the Candidate
  once, and canonically render one linked URL4 per Candidate without string replacement.
- [x] Refactor DRACO's existing URL4 builder to be Candidate-independent: invoke `/candidate` once
  per Case and retain its current private rubric, fixed Judge, repeated passes, and Aggregation.
- [x] Remove the superseded planning/compilation endpoints, schemas, and SDK modules while keeping
  pre-execution failures mapped to stable public recovery classes.
- [x] Implement a two-step SciCode execution seam; prove prior extracted code reaches the next
  Candidate Invocation and sandbox grader.
- [x] Prove native HealthBench chat histories and MedXpert reasoning/commit turns cross the same
  Candidate Invocation boundary without SDK protocol dispatch.
- [x] Execute the Engine-produced DRACO expression after real SDK linkage through Candidate,
  fixed Judge, and Aggregation boundaries with deterministic provider responses.
- [ ] Validate the same small interface against complete SciCode, HealthBench, and MedXpert adapters;
   do not introduce protocol-family dispatch in the SDK.
- [ ] Measure raw and encoded full-suite URL4 sizes, enforce transport and Candidate Invocation
   budgets, and preserve Benchmark revision, operation, usage, and failure provenance in Reports.
- [ ] Run package, URL4 Cloud, distribution, notebook, DRACO live, and representative stateful
    end-to-end gates without overwriting user-edited notebooks.
