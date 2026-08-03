---
title: Implement the ScreamingFace direct evaluation interface
ticket: OME-605
status: approved
date: 2026-07-29
approved: 2026-07-29
spec: ../spec/2026-07-29-OME-605-direct-evaluation.md
---

# Implement the ScreamingFace direct evaluation interface

## Outcome

Replace the mandatory public `plan(...)` → `run(...)` workflow with one canonical
`evaluate(...)` operation while retaining the same strict internal compilation and execution
behavior.

## Steps

1. Add failing public-interface and Client tests for synchronous and asynchronous
   `evaluate(...)`.
2. Consolidate compilation and execution behind `Client.evaluate(...)` and
   `AsyncClient.evaluate(...)`.
3. Remove public `Plan`, `Candidate`, `plan`, and `run` exports without compatibility aliases.
4. Keep compiled Candidate URL4s and operation projections internal; continue attaching the exact
   URL4 and operation evidence to each `CandidateResult`.
5. Update README, deterministic notebook sources, and active display copy to teach only
   `evaluate(...)`.
6. Regenerate notebooks, run the complete ScreamingFace package gates, and update the work ledger.

## Test coverage

- one Candidate and an ordered Candidate sequence;
- required Benchmark, valid and invalid limits, unique Candidate names;
- invalid event/progress options;
- compilation completes before any Candidate starts;
- ordered Result assembly and exact Candidate URL4 preservation;
- synchronous and asynchronous transport paths;
- module-level lazy Client delegation; and
- absence of superseded public names.

## Scope

Only `packages/screamingface` and its OME-605 documentation change. URL4, AI Gateway,
`url4-cloud`, and the SF Engine remain untouched.
