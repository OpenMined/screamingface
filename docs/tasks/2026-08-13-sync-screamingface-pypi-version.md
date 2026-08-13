---
id: OME-824
linear_url: https://linear.app/openmined/issue/OME-824/realign-screamingface-release-baseline-past-manually-published-pypi
status: in_progress
type: task
priority: 2
labels: [py-screamingface, agentic, autonomous, task]
created: 2026-08-13
closed:
---

# OME-824 — Realign screamingface release baseline past manually-published PyPI 0.1.1

`screamingface` `0.1.0` and `0.1.1` were uploaded to PyPI manually before PR #553 pushed tag
`screamingface-v0.1.0`. The resulting release run failed `publish-pypi` with PyPI's
immutability rejection (`400 File already exists`), and would fail identically on the next
run because `main` records `0.1.0` while PyPI is already at `0.1.1`.

Moves the recorded baseline to `0.1.1` (manifest, `pyproject.toml`, `CHANGELOG.md`) so
release-please proposes `0.1.2` — the first version published by the Trusted Publishing
pipeline.

Ledger: `docs/work/2026-08-13-OME-824-sync-screamingface-pypi-version.md`
