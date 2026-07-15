---
ticket: OME-465
stack: url4
status: in_progress
started: 2026-07-15
finished:
---

# OME-465 — url4 SDK PyPI release CI/CD

## Intent

Give `packages/url4` a production-grade PyPI publish lane so the SDK can ship to PyPI
under the repo's release conventions. release-please already registers url4 (config +
manifest) and cuts `url4-v*` tags, and `url4-tests.yml` gates PRs — but there is **no
workflow that reacts to the tag and publishes**, and the package lacks the metadata a
clean PyPI release needs (README, LICENSE, `py.typed`, classifiers/urls). This unit adds
the missing publish workflow (Trusted Publishing / OIDC), the packaging metadata, a
packaging-validation gate, and Dependabot coverage. No package is published — it lands as
a PR; the PyPI-side trust + GitHub Environment are owner actions.

## Planned changes

- `packages/url4/pyproject.toml` — add `readme`, SPDX `license` + `license-files`,
  `authors`, `keywords`, `classifiers` (incl. `Typing :: Typed`), `[project.urls]`.
- `packages/url4/README.md` (new) — PyPI long description.
- `packages/url4/LICENSE` (new) — Apache-2.0 copy (so the dist carries its license).
- `packages/url4/src/url4/py.typed` (new) — ship type information (PEP 561).
- `.github/workflows/release-url4.yml` (new) — `on: push tags url4-v*` + `workflow_dispatch`;
  verify → build-once → publish to PyPI via Trusted Publishing under a `pypi` Environment.
- `.github/workflows/url4-tests.yml` — add 3.13 to the matrix (honestly test claimed
  versions) + a `build` job (`uv build` + `twine check --strict`) as a packaging gate.
- `.github/dependabot.yml` — add the `uv` ecosystem for `/packages/url4`.

## Test plan

CI/packaging work — validated by exercising the pipeline locally, not new unit tests:

- `uv build` produces a valid sdist + wheel; wheel contains `url4/py.typed`.
- `uvx twine check --strict dist/*` passes (valid metadata + long description).
- url4 gates stay green after the pyproject change: `ruff check`, `ruff format --check`,
  `pyright`, `pytest --cov=url4 --cov-fail-under=95`.
- `release-please-config.json` / manifest / `dependabot.yml` remain valid (JSON/YAML parse).
- `actionlint` clean on the new/changed workflows (if available).

## Acceptance

- [ ] `release-url4.yml`: OIDC Trusted Publishing, `pypi` environment, build-once/promote,
      no stored PyPI token, PEP 740 attestations on.
- [ ] Package builds a valid sdist+wheel; `twine check --strict` passes; `py.typed` shipped.
- [ ] `url4-tests.yml` runs matrix 3.12/3.13 + packaging gate.
- [ ] Dependabot `uv` entry for `/packages/url4`.
- [ ] Conventional commits `Refs: OME-465`; nothing pushed to `main`; delivered as a PR.

## Outcome

- **Actual files:** as planned. New: `.github/workflows/release-url4.yml`,
  `packages/url4/{README.md,LICENSE}`, `packages/url4/src/url4/py.typed`, docs
  spec/plan/tasks/work. Modified: `packages/url4/pyproject.toml`,
  `.github/workflows/url4-tests.yml`, `.github/dependabot.yml`. Incidental:
  `packages/url4/uv.lock` — `uv sync` corrected a stale project-entry version
  (`0.2.0` → `0.1.0`) to match `pyproject.toml`/manifest/`__version__`.
- **Commits:** see PR (`ci(url4)` + `feat(url4)` + `docs(OME-465)`), body `Refs: OME-465`.
- **Gates:** ruff check ✓, ruff format --check ✓ (52 files), pyright 0 errors,
  pytest 704 passed / coverage 97.06% (gate 95). Packaging: `uv build` sdist+wheel,
  `twine check --strict` PASSED (both); wheel ships `url4/py.typed` + LICENSE; metadata
  `License-Expression: Apache-2.0`, `Typing :: Typed`, project URLs. `actionlint` clean on
  new/changed lines (the one finding — `job.check_run_id` in the pre-existing `cost` job —
  is inherited unchanged from `aigateway-tests.yml`). JSON/YAML parse OK.
- **Deviations:** (1) also hardened the existing `url4-tests.yml` (3.13 matrix + packaging
  gate) beyond the literal "release workflow" ask, as best-practice for a release lane.
  (2) `uv.lock` version correction noted above. (3) Ticket filed via `linear-cli` at owner
  direction (card default is Linear-MCP-only).
- **Follow-up (not blocking):** `src/url4/__init__.py` hardcodes `__version__ = "0.1.0"`
  independently of `pyproject.toml`; release-please's python strategy updates `__init__`
  `__version__` by default, so they should stay in sync — worth confirming on the next bump.
