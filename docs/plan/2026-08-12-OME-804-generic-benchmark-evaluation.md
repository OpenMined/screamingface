---
title: Implement generic benchmark evaluation capabilities
ticket: OME-804
status: approved
date: 2026-08-12
spec: ../spec/2026-08-12-OME-804-generic-benchmark-evaluation.md
---

# Implement generic benchmark evaluation capabilities

The agreed test seams are the rendered/installed Benchmark protocol and its typed Candidate
Result. Tests do not assert private helper calls or internal module layout.

1. Pin the existing rendered canonical URL4 and installed successful/refused/failed outcomes for
   DRACO, IFEval, and HealthBench with independent literals or existing official fixtures.
2. Add one failing tracer test for a shared outer Case-evaluation protocol: ordered selection,
   collected Case failure, context-carried Case evaluations, and exact aggregate selection.
3. Implement the smallest URL4 AST combinator that passes that test; migrate canonical IFEval,
   then DRACO and HealthBench, preserving each supplied per-Case evaluator node.
4. Add a failing tracer test for the shared installed runtime envelope using two genuinely
   different adapters. Extract only common Candidate Invocation, JSON, Case collection, and
   aggregate mechanics demonstrated by those adapters.
5. Migrate DRACO and HealthBench Judge-based routes, then IFEval deterministic routes, one vertical
   slice at a time. After each migration run its existing protocol and scoring fixtures.
6. Delete replaced shallow helpers and their implementation-coupled tests only after equivalent
   behavior is covered through the installed Benchmark seam.
7. Bump every Benchmark revision whose rendered URL4 or score-affecting runtime identity changes;
   keep the result and internal record schemas at their existing v1 identities.
8. Run the complete URL4 Cloud gate, inspect the final diff for Benchmark-semantic movement,
   speculative registries, DSL-like configuration, private rubric leakage, and compatibility
   paths.
