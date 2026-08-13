---
title: Implement normalized benchmark Case outcome consumption
ticket: OME-803
status: approved
date: 2026-08-13
spec: ../spec/2026-08-13-OME-803-client-case-outcomes.md
---

# Implement normalized benchmark Case outcome consumption

1. Pin scored, refused, and failed payloads for DRACO, IFEval, and HealthBench with strict decoding
   tests, including every missing Case field, unsupported values, and exact round-trip export.
2. Extend the public Case value with stable string/integer identity, explicit status/refusal, and
   the OME-802 structural invariants. Keep direct-construction status inference separate from the
   strict wire decoder.
3. Decode nested Failure values against the exact producer field set and reject malformed or
   misplaced Case identities before a Report is constructed.
4. Preserve outcomes through Candidate Result and Report JSON/file export; add explicit `.by_id()`
   lookup so integer identity is never confused with positional indexing.
5. Render scored, refused, failed, and partial-evidence unscored Cases as distinct states. Surface
   exact refusal and Failure evidence, group repeated diagnoses, and escape untrusted text.
6. Exercise a normal evaluation vertical slice and assert the URL4 recorded in the Report is the
   exact expression submitted to the run transport.
7. Run the complete `screamingface` unit suite, Ruff check/format, Pyright, distribution/notebook
   checks, and the repository gate. Document the necessary append-only exception: inherited wire
   fixtures gain the mandatory OME-802 fields; existing boundary, serialization, presentation,
   and vertical-slice tests change where their former expectations contradict the new strict
   contract or must prove the newly required behavior. No assertion is removed to weaken coverage.
8. Re-run Standards and Spec review, fix material findings, then update the ledger and PR #574 for
   review against `main`.
