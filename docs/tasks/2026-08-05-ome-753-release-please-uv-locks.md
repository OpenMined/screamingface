---
id: OME-753
linear_url: https://linear.app/openmined/issue/OME-753/regenerate-uv-locks-inside-the-release-please-job
status: in_review
type: task
priority: P2
labels: [repo, autonomous, agentic, task]
created: 2026-08-05
closed:
---

# OME-753 — regenerate uv locks inside the release-please job

release-please bumps `version` in a package's `pyproject.toml` but never regenerates the uv
lockfiles that record that version. `url4-cloud-tests` runs `uv lock --check` first, so every
url4 / url4-cloud release PR fails before ruff, pyright, or pytest run — and `main` goes red
the same way once the release merges.

Seen on PR #504 (`chore(main): release url4 1.2.0`):

```
Run uv lock --check
error: The lockfile at `uv.lock` needs to be updated, but `--check` was provided.
```

`apps/url4-cloud/uv.lock` pins `url4 = 1.1.0` (editable path dependency,
`apps/url4-cloud/pyproject.toml:58`); `packages/url4/uv.lock` pins its own root entry the
same way. Third occurrence — the earlier two were patched by hand afterwards (`f2b46c06`,
`9061f40f`).

Fix: re-lock the affected uv workspaces inside the release-please job and push the amend
commit with `RELEASE_PAT` (a `GITHUB_TOKEN` push does not retrigger checks), plus add the
`uv lock --check` guard to the Python app workflows that lack it, so the drift is visible in
its own lane instead of only through a neighbour.

Rejected: relaxing or scoping off `uv lock --check` — that guard exists because a stale lock
once shipped undetected (`.github/workflows/url4-cloud-tests.yml:41`).
