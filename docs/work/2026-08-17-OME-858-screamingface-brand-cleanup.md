---
ticket: OME-858
stack: screamingface
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-858 — ScreamingFace brand cleanup

## Intent

Remove OpenMined-derived branding from the public ScreamingFace Python package so its metadata,
documentation, models and wire vocabulary consistently use the ScreamingFace identity.

## Planned changes

- Rename `verified_by_openmined` throughout the Client to `verified_by_screamingface`.
- Replace package-local repository, documentation, attribution and test fixture references.
- Regenerate generated notebooks if affected.

## Test plan

- Strict tracked-file searches for case-insensitive `openmined` and standalone `OM`.
- Focused leaderboard parsing/model/UI tests.
- Notebook consistency and full `screamingface` gates.

## Acceptance

- No forbidden brand token remains in tracked `packages/screamingface` content or paths.
- Public models and strict wire decoding use only the ScreamingFace verification field.
- All package gates pass.

## Outcome

- **Actual files:** renamed the leaderboard field through its public models, strict decoder, UI
  adapter and tests; updated package metadata, changelog repository links, package-local research
  links and the provider-icon provenance notice.
- **Commits:** this implementation commit (`Refs: OME-858`).
- **Gates:** `run_gates.py screamingface --base origin/main --skip-append-only` — ALL GREEN
  (ruff, formatting, pyright, pytest with coverage ≥95%, notebook validation, wheel/sdist build,
  distribution validation). Focused leaderboard suite: 34 passed.
- **Deviations:** no persistent negative-brand regression test was added because such a test
  would itself retain the vocabulary this unit removes. The zero-match verification remains an
  uncommitted review command. The Scoreboard producer must rename its emitted verification field
  before this Client field is available end-to-end; no legacy Client fallback was retained.
