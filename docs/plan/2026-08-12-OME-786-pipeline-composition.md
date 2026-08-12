---
title: Implement serial Pipeline and recursive Candidate composition
ticket: OME-786
status: approved
date: 2026-08-12
spec: ../spec/2026-08-12-OME-786-pipeline-composition.md
---

# Implement serial Pipeline and recursive Candidate composition

1. Add public-interface tests for immutable, structurally equal `Pipeline` construction,
   one-or-more-stage validation, route-string normalization, naming, and exact
   `Recipe.then(...)` shorthand; implement only enough value behavior to make them pass.
2. Add compiler tests for a two-stage Model Pipeline, then generalize Candidate compilation around
   a Recipe bound to an input expression so serial dependencies are explicit and reuse remains
   input-sensitive.
3. Add recursive-composition tests for Fusions inside Pipelines, Pipelines inside Fusions, and
   Recipe synthesizers; require complete Fusions with one-or-more members and extend compilation
   around one canonical versioned Recipe descriptor.
4. Remove content/identity deduplication across graph placements and prove repeated equal or reused
   Recipes compile as distinct logical invocations under both equal and different inputs.
5. Replace prose Fusion input formatting with URL4-native canonical structured context, proving
   runtime-safe answer substitution, stable ordering, display-name independence, and consistent
   Model/Pipeline synthesizer input.
6. Remove the SDK-owned `max_tokens=4096` generation default and prove parameter-free Models emit
   no generation parameters while explicit values remain preflighted and reconstructable.
7. Add no-spend shape and preflight tests for routes, explicit parameters, cycles, sealed Recipe
   variants, structural validity, and all-before-any behavior. Keep Engine-owned compatibility and
   execution limits out of Client constructors.
8. Extend typed results, exports, URL4-to-Python reconstruction, and operation projections for a
   `pipeline` root while preserving existing Model/Fusion contracts.
9. Add the SFDS v2 Pipeline notebook card and verify its light/dark output through public
   representation tests.
10. Update the repository domain glossary and Client documentation to define Pipeline, complete
   Recipe, and recursive Fusion synthesis without embedding Benchmark protocol logic.
11. Run focused tests after every red-green slice, then the complete screamingface test suite and
   `uv run .claude/scripts/run_gates.py screamingface` from the repository root.
12. Review `origin/main...HEAD` for speculative control-flow behavior, accidental Engine coupling,
   legacy/fallback paths, altered prior tests, and only the two intentional Model/Fusion URL4
   changes: no universal generation parameters and structured Fusion context.

If the existing URL4 public AST cannot encode an input-bound serial graph, stop and split the
required `packages/url4` capability into its own landing ticket rather than adding a Client-local
protocol workaround.
