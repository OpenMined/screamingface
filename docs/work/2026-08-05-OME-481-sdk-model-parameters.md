---
ticket: OME-481
stack: screamingface-sdk
status: in_progress
started: 2026-08-05
finished:
---

# OME-481 — typed model parameters and Evaluation preflight

## Intent

Make AI Gateway's authoritative parameter contract available through the ordinary Client and use
it for a narrow, free preflight of explicit user overrides before a paid Evaluation starts.

## Planned changes

- `discovery.py` — immutable summary/detail values.
- `_engine/catalog_contract.py` — strict v1 list/detail decoding.
- `_engine/catalog.py`, `models.py`, `client.py`, `__init__.py` — sync/async/default public access.
- `_evaluation/model_parameters.py`, `_evaluation/runner.py` — targeted preflight.
- New focused discovery/preflight tests and a shared fixture; existing fixtures are only tightened
  where the locked model-list contract now requires fields they omitted.

## Test plan

- Summary fields; typed detail fields; schema vocabulary; malformed wire boundaries.
- Sync/async/default `get()` parity and authentication/availability failures.
- No detail read without explicit overrides; one read per distinct model with overrides.
- Valid, missing, disabled, wrong-type, enum, and numeric-bound parameter behavior.
- No paid transport call after any preflight failure.

## Outcome (fill at the end — required before COMMIT)

- **Actual SDK code:**
  - `discovery.py` — immutable `ModelInfo`, `ModelDetails`, parameter-schema, parameter-policy,
    tool, and transport values; generic schema validation.
  - `_engine/catalog_contract.py` — strict lightweight `/v1/models` decoding.
  - `_engine/model_parameters.py` — strict profile-specific detail decoding, kept separate from
    the ordinary catalogue decoder so both modules remain small.
  - `_engine/catalog.py`, `models.py`, `client.py`, `__init__.py` — sync, async, and lazy-default
    `models.get(model_id)` access through the existing authenticated Engine seam.
  - `_evaluation/candidate.py`, `_evaluation/model.py`, `_evaluation/compilation.py`,
    `_evaluation/model_parameters.py`, and `_evaluation/runner.py` — retain explicit overrides on
    compiled operation identities, discard components the Benchmark does not link, then perform
    deduplicated preflight before the paid run transport.
- **Tests:** `tests/_model_parameter_fixtures.py`,
  `tests/test_model_parameter_discovery.py`, and `tests/test_model_parameter_preflight.py`, plus
  locked model-list fixture/public-export updates in the existing SDK tests that consume that
  contract.
- **Documentation:** README discovery/preflight guidance plus this task/spec/plan/ledger set.
- **Commits:** not committed; the user requested review before any handoff mutation.
- **Gates:**
  - Ruff check ✓; Ruff format check ✓; Pyright ✓.
  - Full behavior/coverage suite ✓ — **474 passed, 14 skipped**, **95.07%** coverage.
  - Generated-notebook consistency ✓.
  - sdist + wheel build ✓; installed-distribution check ✓.
  - The umbrella runner stops at its append-only precheck because the long-running stacked SDK
    branch already modifies twelve committed test files versus `HEAD`. The OME-481 subset changes
    locked catalogue fixtures/public exports but does not delete or weaken assertions. Every
    executable gate after that precheck was run directly and is green; the append-only exception
    remains an explicit review/Confidence-Gate item rather than a weakened gate.
- **Deviations:**
  1. The detail decoder moved to `_engine/model_parameters.py` instead of growing
     `_engine/catalog_contract.py` past the repository's 450-line guidance. This is a pure module
     seam; the public behavior is unchanged.
  2. The full gate exposed an existing generator/Ruff disagreement in the already-modified DRACO
     full notebook. Its generator cell was mechanically normalized and the notebook rebuilt so
     both checks agree; that hunk belongs to the Benchmark notebook unit, not OME-481.
  3. Candidate values remain scalar-only. Discovery mirrors the complete upstream v1 schema, but
     this unit deliberately does not add Base64 payloads or change URL4 to carry structured values.
