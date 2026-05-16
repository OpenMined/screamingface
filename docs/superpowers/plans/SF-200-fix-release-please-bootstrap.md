# SF-200: Fix Release Please CI — anchor desktop+server with bootstrap-sha

> **For agentic workers:** Single-file JSON edit. No tests to run; verification is observing the next Release Please CI run on main.

**Goal:** Stop the `Release Please` GitHub Action from failing on every push to `main` with `release-please failed: Server Error`.

**Asana:** [SF-200](https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214854003907795)

---

## Context

The `Release Please` workflow has been failing on every merge to `main` since at least 2026-05-14 (SF-152 merge). Failure is not visible in PR checks (the workflow only runs on `push` to `main`), so it slips under the radar — but every merge ships with one red workflow.

Server Tests, pre-commit, and WIP all pass; this is purely an issue with the auto-release-PR generator. Non-blocking for development, but worth fixing for release hygiene.

### Root cause

`release-please-config.json` declares three packages — `apps/desktop`, `apps/server`, `apps/aigateway` — and `.release-please-manifest.json` claims versions for all three. But only one matching git tag exists in the repo:

| Package | Manifest version | Tag exists? |
|---|---|---|
| apps/desktop | 0.1.0 | ❌ `desktop-v0.1.0` missing |
| apps/server | 0.1.0 | ❌ `server-v0.1.0` missing |
| apps/aigateway | 0.2.0 | ✅ `aigateway-v0.2.0` present |

Without anchor tags for `desktop` and `server`, `googleapis/release-please-action@v4` walks the full main history searching for one. The repo has 200+ merge commits; the action eventually hits a 5xx from GitHub's GraphQL API and aborts:

```
❯ Fetching merge commits on branch main with cursor: ... 199
##[error]release-please failed: Server Error
```

## Fix

Add `bootstrap-sha` to `apps/desktop` and `apps/server` in `release-please-config.json`, pointing at the most recent main commit (`080dd8c`, the SF-199 squash merge). `bootstrap-sha` tells release-please "ignore everything before this commit for this package," eliminating the backfill.

Leave `apps/aigateway` alone — its tag already anchors it.

### Edit

In `release-please-config.json`:

```json
    "apps/desktop": {
      "release-type": "node",
      "package-name": "screamingface-desktop",
      "component": "desktop",
      "tag-separator": "-",
      "include-component-in-tag": true,
      "bootstrap-sha": "080dd8c59b0b2c4b4c97f48a17c2b5435df9fa68"
    },
    "apps/server": {
      "release-type": "python",
      "package-name": "screamingface",
      "component": "server",
      "tag-separator": "-",
      "include-component-in-tag": true,
      "version-file": "apps/server/pyproject.toml",
      "bootstrap-sha": "080dd8c59b0b2c4b4c97f48a17c2b5435df9fa68"
    },
```

(`apps/aigateway` is unchanged.)

### Commit

```bash
git add release-please-config.json
git commit -m "ci: anchor release-please for desktop+server with bootstrap-sha (SF-200)"
```

### Verify

`release-please-action@v4` only runs on `push: branches: [main]`. So:
1. Open PR, get review.
2. After merge, observe the next workflow run on main:
   `gh run list --branch main --workflow "Release Please" --limit 1`
3. Expected: `success` instead of `failure`. If the action now decides to open a release PR, that's the desired side-effect — the auto-release pipeline is working again.

## Out of scope

- Creating retroactive `desktop-v0.1.0` / `server-v0.1.0` tags. `bootstrap-sha` makes those unnecessary; future release PRs will create tags going forward.
- Resolving the orphaned `v0.1.0-alpha.1` tag in the repo. It doesn't match any current package's tag scheme; ignore unless someone confirms its origin.
- Anything else release-related (changelogs, version bumps, publication).
