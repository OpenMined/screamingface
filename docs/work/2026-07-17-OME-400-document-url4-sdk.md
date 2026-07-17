---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-17
finished: 2026-07-17
---

# OME-400 — Document the URL4-native SDK and runnable examples

## Intent

Make the ScreamingFace SDK understandable and runnable from the repository without implying that
deterministic model responses are production inference. Keep the main quickstart short, move wire
and architecture teaching into dedicated material, document the complete current public API in a
brand-aligned static page, and reconcile OME-400 process records with the implemented URL4-only
execution boundary.

## Planned changes

- Add a package-local static API and architecture page under `packages/screamingface/docs/`.
- Add append-only documentation contract tests covering the public API inventory, engine/data
  provenance, and the documented URL4 request/response boundary.
- Refine the three notebook generators and regenerate `00_quickstart.ipynb`,
  `sf_url4_engine.ipynb`, and `draco.ipynb` from clean kernels.
- Update `packages/screamingface/README.md` with a concise documentation map and accurate runtime
  boundary.
- Reconcile the OME-400 spec, plan, task mirror, and this ledger with the current `sf.config`,
  `Fusion`, reducer, benchmark, mock-leaf, and HTTP-engine contracts.
- Refresh the gitignored `.docs/` SDK/integration notes as local context without treating them as
  committed sources of truth.
- Preserve the user-owned `packages/url4` branch overlay and make no URL4 engine source changes.

## Test plan

- RED: add tests that require the HTML page to enumerate every exported public API name and state
  the no-direct-AI-Gateway, real-URL4-node, deterministic-leaf, and strict-HTTP invariants.
- RED: require each generated notebook to declare its teaching level and the exact engine/data
  provenance relevant to that example.
- GREEN: add/refine the documentation and notebook sources, then execute all notebooks from clean
  kernels and assert byte-deterministic regeneration.
- Run the registered ScreamingFace gate runner, notebook drift checks, package build, and HTML
  structural/link checks.

## Acceptance

- A new user can run the bare quickstart without services and cannot mistake its score for provider
  quality.
- A researcher can inspect representative decoded URL4 expressions and engine response envelopes
  without reading SDK source.
- The static API page covers every name in `screamingface.__all__`, distinguishes recipe from
  request, and explains mock-leaf replacement with a production HTTP URL4 engine.
- README, notebooks, spec, plan, task mirror, ledger, and hidden local notes agree that
  ScreamingFace never calls AI Gateway directly.
- All package gates pass and `packages/url4` remains untouched by this unit.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added `packages/screamingface/docs/index.html` and
  `packages/screamingface/tests/test_documentation.py`; refined all three notebook builders and
  regenerated their executed notebooks; updated the package/root READMEs and contributing guide;
  replaced the obsolete OME-400 spec/plan/task text with the implemented URL4-only contract;
  appended a supersession note to the historical OME-400 ledger; refreshed the gitignored SDK
  catch-up and integration roadmap.
- **Commits:** not committed in this work unit; awaiting owner review/handoff.
- **Gates:** `uv run .claude/scripts/run_gates.py screamingface` — ALL GATES GREEN, including the
  append-only test check, Ruff, format, Pyright, and 95% coverage gate. Full suite: 108 passed,
  1 skipped, 96.39% coverage. Documentation contract: 10 passed. Wheel and sdist build green.
  Clean-kernel notebook execution and byte-deterministic regeneration green at SHA-256:
  `7b5d1c318fe4ee6976f7bcc45c5e2f8a607890d8dd74da88e5e254dc61ee96f7`
  (`00_quickstart.ipynb`),
  `313ea425dd2ba724cb172bc94ddf485981e3a0ad7ae1fa20fea1828486a1403f`
  (`sf_url4_engine.ipynb`), and
  `4c37be97e6aab6ee9294ac200f0012d70d9d131b98f253a91f668db9b955094f`
  (`draco.ipynb`). `git diff --check` is clean.
- **Deviations:** the in-app browser was unavailable, so the HTML page could not receive a
  browser-level light/dark/responsive visual inspection in this session. Automated checks instead
  parse the HTML, require exact `screamingface.__all__` coverage, verify every local link, enforce
  the applicable no-gradient/no-shadow/no-rounded-corner design constraints, and require both
  theme definitions. The first package-build attempt was invoked from the repository root and
  correctly failed because it is not a Python project; rerunning from `packages/screamingface`
  succeeded. No `packages/url4` source or test file was modified by this unit.
