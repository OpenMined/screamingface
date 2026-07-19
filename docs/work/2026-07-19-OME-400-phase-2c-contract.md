---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Approve the Phase 2C compiler and Run contract

## Intent

Lock the user-facing and wire-level Phase 2C decisions before changing runtime code. This unit is
documentation and syntax fixtures only.

## Decisions

- Expose a canonical `fusion.url4` template and preserve it as `run.fusion_url4`.
- Compile with URL4's public builder/AST facade and certified renderer, then add one literal
  question binding per concrete case request.
- Treat member/model-reducer prompts as intent instructions; construct model-reducer question and
  labeled-panel context automatically.
- Accept either a benchmark ID or `Benchmark` in synchronous, notebook-safe `Fusion.run()`.
- Return immutable `Run`, `CaseResult`, `MemberResult`, and `RunFailure` records plus
  JSON-compatible `run.to_dict()`.
- Execute at most four cases concurrently, preserve canonical order, perform no retries, and do not
  cancel unrelated selected cases after execution begins.
- Keep `evaluate()`, grading, aggregation, persistence, tools, budgets, authentication, and public
  execution-policy controls outside Phase 2C.

## Test plan

- Parse every Phase 0 Python fixture without importing unimplemented APIs.
- Audit the plan/spec/fixtures for stale `member_answers`, 503 retries, systemic cancellation, or
  the old `"$question"` default-prompt assumption.
- Run `git diff --check` and confirm no runtime source or tests changed.

## Outcome

- **Actual files:** revised the normative public contract, architecture plan, task ledger, and
  benchmark walkthrough syntax fixture; added this work record.
- **Commits:** none; the user owns commit and push.
- **Gates:** every Phase 0 fixture imports and executes against the current Phase 2B package from
  the ScreamingFace environment; the stale-contract audit is empty; `git diff --check` passes; and
  no runtime source, tests, app, or notebook files changed.
- **Deviations:** none; runtime implementation remains the next separately reviewed unit.
