---
ticket: OME-626
stack: screamingface
status: in_progress
started: 2026-07-28
finished:
---

# OME-626 — Port rich catalogue and object display into the v1 Client

## Intent

Replace raw tuple output in notebooks with the approved searchable ScreamingFace catalogue
experience while preserving a small discovery interface and normal typed Python behavior outside
notebooks.

## Planned changes

- Add public immutable `ModelCatalog` and `BenchmarkCatalog` return values.
- Add private escaped HTML/widget renderers and shared brand styles.
- Adapt Model and Fusion rich displays to the clean v1 values.
- Preserve the existing discovery transport and lazy Client interfaces.
- Add focused append-only tests and update the Client documentation.

## Test plan

- Prove catalogue values remain ordered sequences and compare equal to equivalent tuples.
- Prove static HTML contains real fields, hides benchmark digests from the primary row, and
  escapes injected text.
- Prove notebook search filters only presentation without mutating the catalogue.
- Prove missing notebook dependencies retain a static representation.
- Prove Model/Fusion cards escape text and preserve ordinary typed values.
- Run the full ScreamingFace quality gate.

## Acceptance

- `sf.models.list()` and `sf.benchmarks.list()` automatically render searchable catalogues in
  Jupyter and remain normal typed Python data everywhere else.
- There is no public `.view()` duplicate.
- Applicable OME-626/OME-641 presentation is retained without legacy Client functionality.
- All ScreamingFace gates pass.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added `_display.py`, `_card_style.py`, `_card_display.py`,
  `_catalog_view.py`, and `_url4_format.py`; adapted discovery catalogue decoding, module-level
  catalogue annotations, Model/Fusion cards, README discovery guidance,
  and append-only rich-display tests.
- **Commits:** pending owner request
- **Gates:** 204 passed / 15 skipped; Ruff and Pyright green; wheel and sdist build plus
  distribution check green; new display modules have 99% aggregate coverage.
- **Deviations:** the whole-package 95% coverage gate remains at 89% because the surrounding
  uncommitted OME-620 demo modules entered this unit below the gate. The notebook-set gate is
  blocked by the user-owned `05_draco_lite_e2e-Copy1.ipynb`, and the canonical DRACO-Lite
  notebook contains execution output rather than matching its cleared deterministic build.
  Neither notebook was altered.
