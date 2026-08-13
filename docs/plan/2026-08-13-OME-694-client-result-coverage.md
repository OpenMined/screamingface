---
title: Implement Client result coverage and graded refusals
ticket: OME-694
status: approved
date: 2026-08-13
spec: ../spec/2026-08-13-OME-694-client-result-coverage.md
---

# Implement Client result coverage and graded refusals

1. Add red public-value and strict-decoder tests for required top-level coverage, forbidden
   `metrics.coverage`, numeric score plus failed Cases/Failures, graded refusals, and refusals whose
   later grading failed.
2. Deepen `CandidateResult` as the single public result interface: add immutable coverage,
   preserve it in portable output, allow scored results to retain failures, and keep unscored
   metrics empty.
3. Update the exact Engine decoder to require and validate coverage without deriving it from
   Cases. Remove the generic metric coverage warning path and its public warning type.
4. Update the Case outcome validator to mirror OME-807 exactly, retaining strict direct-value and
   wire validation without compatibility inference.
5. Update Report rendering to use top-level coverage, explain partial scores and zero-coverage
   results truthfully, and display graded refused Cases without hiding checks or exact refusal.
6. Migrate Client fixtures from the superseded fail-closed/refusal-zero shape and assert complete
   round trips through `to_dict()`, JSON, export, the normal evaluation path, and URL4 replay.
7. Run the complete `screamingface` gates, review the diff for Engine policy duplicated in the
   Client, document the intentional append-only exception, and keep the branch local until OME-807
   merges. Then rebase onto `origin/main` before opening a non-stacked PR.
