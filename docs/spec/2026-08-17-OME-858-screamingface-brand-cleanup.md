# OME-858 — Remove OpenMined and OM branding from the ScreamingFace Python package

Status: APPROVED — owner requested implementation on 2026-08-17.

## Goal

`packages/screamingface` must describe the product and its public contracts exclusively as
ScreamingFace. No case-insensitive `openmined` text or OpenMined-derived standalone `OM`
abbreviation may remain in tracked package files.

## Contract change

The leaderboard wire/model field is renamed from `verified_by_openmined` to
`verified_by_screamingface`. This unit intentionally provides no legacy alias or decoder fallback.
The Scoreboard producer must adopt the new field before leaderboard decoding is compatible.

## Scope

- Python source, tests, package metadata, changelog, package-local research notes and notices.
- Notebook builder and generated notebooks if matches occur there.
- Only `packages/screamingface` product files change, apart from mandatory repository SDLC
  artifacts for OME-858.

## Acceptance

- A tracked-file, case-insensitive search under `packages/screamingface` finds no `openmined`.
- No OpenMined-derived standalone `OM` remains under the package.
- Leaderboard models, decoder, UI and tests consistently use `verified_by_screamingface`.
- Generated notebooks and the full ScreamingFace package gates pass.
