---
ticket: OME-400
status: implemented
phase: 4a-gpqa
date: 2026-07-19
---

# Phase 4A — canonical SDK-local GPQA definition

Implemented the owner-approved GPQA-only runtime slice at the corrected data boundary. No public
SDK API, URL4 behavior, model route, AI Gateway adapter, or engine discovery shape changed.

## Implementation

- added `screamingface._benchmarks.gpqa` as the SDK-local source boundary;
- pinned `Idavidrein/gpqa`, `gpqa_diamond`, `train` at revision
  `633f5ee89ab8ad4522a9f850766b73f62147ffdd`;
- lazily loads through the researcher's Hugging Face session and caches one successful normalized
  tuple per researcher process;
- validates all 198 rows before returning any case;
- requires the pinned source fields, unique non-whitespace `Record ID` values, nonblank source
  text, and a correct answer distinct from every distractor;
- keeps source order and exact question/answer text;
- derives option order from SHA-256 of benchmark ID, source Record ID, and original option slot;
- computes the answer label from the tagged correct option after ordering; and
- maps `High-level domain` and `Subdomain` to `domain` and `subdomain` metadata.

## Live-source finding

The pinned source has 198 rows and loaded successfully. Row `recZSGUkn56v9kEp1` contains two
identical incorrect options. The publisher preserves that canonical data. It does not require all
four strings to be unique; it requires only that the correct answer not equal a distractor, which
keeps the reference unambiguous without rewriting or dropping the row.

The live verification returned 198 cases, beginning with `rec06pnAkLOr2t2mp` and ending with
`reczkBiPPNrNN49Hp`.

## Verification

- 283 repository tests passed with 97.07% ScreamingFace coverage;
- 42 dedicated engine tests passed with 97.67% engine coverage;
- the GPQA publisher module has 100% line coverage;
- Ruff lint and formatting passed;
- Pyright passed with zero errors;
- public contract fixtures constructed;
- the Phase 1 notebook regenerated without drift; and
- the ScreamingFace sdist and wheel built successfully.

The engine no longer publishes benchmark manifests or case routes and does not receive
`HF_TOKEN`. Phase 4B subsequently added the canonical DRACO source definition to the SDK catalog;
later tool and judge work determines whether the configured engine can execute it.
