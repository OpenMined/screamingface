---
ticket: OME-400
stack: python
status: in_progress
started: 2026-07-13
finished:
---

# OME-400 — Ship 00_quickstart + the `screamingface` SDK surface it needs

## Intent

Create the production `screamingface` Python SDK (`packages/screamingface`, import
`screamingface as sf`) by porting the quickstart slice of the `screamingface-contract`
prototype (screamingface-brand/product-demos), and ship `00_quickstart.ipynb` executed
green against it. The notebook is App Iteration 1's SDK-side mirror and the de-facto spec
of connect → compose → run → compare. The simulated backend sits behind a hexagonal
`EngineBackend` port so the real engine (OME-296) and real url4 grammar (OME-408) swap in
later without changing the public API. Approved plan: `.claude` plan session
(compiled-wandering-lantern); owner decisions Q1–Q4 recorded in `docs/plan/`.

## Planned changes

- `packages/screamingface/pyproject.toml`, `pyrightconfig.json`, `uv.lock`, `README.md`
- `packages/screamingface/src/screamingface/`: `__init__.py` (facade, `__all__`,
  `__version__`), `engine.py` (`EngineBackend` port + `SimulatedBackend` adapter),
  `catalog.py`/`models.py` (catalog service), `fusion.py`, `run.py`, `reduce.py`,
  `datasets.py` + `_data/gpqa.json`, `session.py`, `share.py` (flat `url4://` emit only),
  `widgets.py` (mock/static path only)
- `packages/screamingface/tests/` (+ `conftest.py` with fake engine adapter)
- `packages/screamingface/examples/00_quickstart.ipynb` (executed, outputs committed)
- `.github/workflows/screamingface-tests.yml`; `.github/CODEOWNERS` and
  `.github/dependabot.yml` entries
- `docs/spec/2026-07-13-screamingface-sdk-quickstart-spec.md`,
  `docs/plan/2026-07-13-screamingface-sdk-quickstart.md`

## Test plan

- RED-first per sdlc-python: catalog list/filter/sort (`max_price`, `search`, `sort`);
  `Fusion` construction incl. `judge=` member validation; `fusion.url` flat-format shape;
  reduce strategies (`majority_vote`, `weighted_avg`, `best_of_n`, `merge`); evaluate
  determinism (same seed → same score) and `first=` sampling; `run.score/baseline/gain`
  arithmetic + repr; `EngineBackend` structural conformance of `SimulatedBackend`;
  session connect flag (env-var key pickup, no key logging); mock-widget render smoke.

## Acceptance

- `uv run pytest` / `ruff check` / `pyright` green in `packages/screamingface`; repo gates green.
- `00_quickstart.ipynb` executes end-to-end (nbconvert), gain read-out visible, outputs
  committed; two executions produce identical score/gain.
- CI lane `screamingface-tests.yml` triggers on the PR and passes.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:**
