# Contributing to ScreamingFace

This guide covers running the repo's services from source and the git workflow.

> The legacy desktop app and plugin server were removed in the July 2026
> re-foundation (tag `legacy-monorepo-2026-07-08`). Active apps and packages
> are self-contained and carry their own guides and CI lanes.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| uv | latest | Python toolchain/installer. `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | ≥ 3.12 | `uv` installs and pins this for you; no system Python needed. |

## Get the code

```bash
git clone https://github.com/OpenMined/screamingface.git
cd screamingface
git config core.hooksPath .githooks   # enables the pre-commit guard (blocks commits to main)
```

## Run from source

Each Python component under `apps/<name>` or `packages/<name>` is self-contained with its own
`pyproject.toml`, lockfile, package-local guides/examples, and registered gates.

```bash
# AI Gateway — provider OAuth, encrypted credential store (port 9105)
cd apps/aigateway
uv sync
uv run uvicorn aigateway.main:app --port 9105 --reload
curl -sf http://localhost:9105/healthz   # liveness check

# Scoreboard — public benchmark scoreboard + demo portal (port 9106)
cd apps/scoreboard
uv sync
uv run scoreboard

# ScreamingFace SDK — local ScreamingFace engine stack and quickstart
cd ../../packages/screamingface
uv sync --extra notebook
cd apps/screamingface-engine
./dev.sh
# In another terminal, from packages/screamingface:
uv run --extra notebook jupyter lab examples/00_quickstart.ipynb
```

The ScreamingFace SDK always uses its configured HTTP URL4 engine. The local development stack
starts that engine and AI Gateway; only engine model routes contact AI Gateway.

## Tests, lint, typecheck

Run inside the component you're changing—the same categories CI runs:

```bash
cd apps/<app>                    # or packages/<package>
uv run ruff check          # lint
uv run ruff format --check # formatting
uv run pyright             # typecheck
uv run pytest              # unit tests
```

Gateway-specific:

- `apps/aigateway` live tests (`-m live`, real provider OAuth) are skipped in
  CI. Run them locally, with backends actually connected, before asking to
  merge changes that touch the gateway request/refresh path.
- Never import `litellm-enterprise` — CI runs
  `apps/aigateway/scripts/check_no_enterprise.py` as a guard.

## Git workflow

- **Work item first.** Every unit of work is a Linear issue (`OME-N`) — see the
  `task-management` skill and the "AI SDLC" section of [`CLAUDE.md`](CLAUDE.md).
- **Branch naming:** `OME-N-<description>` (e.g. `OME-12-fix-refresh`), where
  `N` is the Linear work-item number.
- **Never commit directly to `main`.** The `.githooks/pre-commit` hook (enabled
  above) blocks it; branch protection enforces it remotely.
- **Conventional commits.** Use `feat:`, `fix:`, `docs:`, `chore:` etc. —
  release-please derives version bumps and changelogs from them (`feat:` →
  minor, `fix:` → patch; `docs:`/`chore:` don't bump). The body carries
  `Refs: OME-N`.
- **PRs:** squash-merge after review approval + green required checks. Include
  the Linear work-item link, a summary, and a test plan in the body.
- **Architecture is enforced.** DRY/SOLID/hexagonal are mandatory — see the
  "Architecture Principles" section of [`CLAUDE.md`](CLAUDE.md).

## Releases

- `apps/aigateway` — release-please manages the release PR; merging it tags
  `aigateway-v*`, which builds the GHCR image + Helm chart
  (`release-aigateway.yml`).
- `apps/scoreboard` — manual tag `scoreboard-v*` triggers
  `release-scoreboard.yml` (GHCR image + Helm chart).

## Reference

- **Gateway internals:** `apps/aigateway/README.md` (credential store, secret
  key, migrations)
- **Scoreboard internals:** `apps/scoreboard/README.md` (portal, public
  artifacts)
- **ScreamingFace SDK:** `packages/screamingface/README.md`
- **URL4 SDK examples:** `packages/url4/examples/url4_examples.ipynb`
- **Repo routing (which app, which CI, who reviews):** the
  `working-in-this-repo` skill (`.claude/skills/working-in-this-repo/`)
- **Legacy reference:** `git checkout legacy-monorepo-2026-07-08`
