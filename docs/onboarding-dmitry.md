# Dmitry Onboarding: AI Gateway Track

This page is the short path for Dmitry's first ScreamingFace workstream:
`apps/aigateway` now, scoreboard/portal work later. For broader collaboration
rules, read `docs/team-development.md` first.

## Repo Layout

`apps/aigateway` is the LiteLLM-compatible FastAPI gateway Dmitry owns. It
exposes OpenAI-shape routes such as `POST /v1/chat/completions` and
`GET /v1/models`.

`apps/server` is the local ScreamingFace plugin server. Sergey owns most of this
area; read it only when aigateway integration needs a server-side consumer.

`apps/desktop` is the Electron app. Dmitry may touch UI integration points, but
desktop runtime and packaging stay Sergey-owned.

`web/public` is the deployed static GitHub Pages site. There is no active
`apps/scoreboard` directory in this checkout yet; confirm branch/repo target
before starting scoreboard implementation.

## Run Aigateway Locally

```bash
cd apps/aigateway
uv sync
uv run uvicorn aigateway.main:app --port 9105 --reload
```

In another shell, run:

```bash
curl -sf http://localhost:9105/healthz
uv run pytest -m "not live"
```

Expected health response is `{"status":"ok"}`. Current `main` has gateway
scaffolding only; provider plugins are landing through follow-up PRs.

## Local Checks

Run these before opening an aigateway PR:

```bash
cd apps/aigateway
uv run pytest -m "not live"
uv run ruff check .
uv run pyright
uv run python scripts/check_no_enterprise.py
```

Live tests are separate. Use `AIGW_LIVE=1 uv run pytest tests/live/ -v` only when
the relevant provider credentials exist locally.

If Ruff or Pyright fails on unchanged `main`, treat it as a baseline issue to
confirm or fix before the first gateway code PR, not as a local setup failure.

## Credential Files

Provider live tests and OAuth flows read credentials from the provider CLI's
normal local storage.

Claude/Anthropic uses `~/.claude/credentials` once the Anthropic provider PR is
merged or checked out.

Codex provider work is expected to use `~/.codex/auth.json`.

Gemini provider work is expected to use `~/.gemini/oauth_creds.json`.

Never commit credential files, tokens, copied headers, or local `.env` material.

## Branch And Commit Flow

Use an Asana-backed branch: `SF-{n}-{description}`. If no ticket exists, create
one first and set the Asana `SF` custom field.

Run `git config core.hooksPath .githooks` once after cloning. The pre-commit hook
blocks commits made directly on `main`.

Commit subjects should follow the existing repo style when possible, but strict
Conventional Commits are not required. Include the Asana permalink in the commit
body.

Open a PR with the Asana link, summary, test plan, and screenshots or recordings
for UI changes. Sergey reviews Dmitry PRs during the initial onboarding period.

## LiteLLM License Guard

Use only the MIT-licensed core `litellm` package. Do not install
`litellm-enterprise` and do not import `litellm.enterprise.*` or
`litellm_enterprise.*`.

The guard lives at `apps/aigateway/scripts/check_no_enterprise.py` and is also
covered by `apps/aigateway/tests/test_no_enterprise.py`. Run it before PRs that
touch gateway code or dependencies.

## Aigateway Mental Model

The gateway is a small FastAPI app wrapping LiteLLM's OpenAI-compatible chat
completion interface.

Provider plugins are direct subpackages under `src/aigateway/plugins/`. Each
plugin exports `PLUGIN` from `plugin.py`, contributes model entries, optionally
mounts auth routes, and owns its OAuth strategy.

The current `main` branch has no provider packages. PR `#123` / `SF-139` adds the
Anthropic provider and should become the first concrete reference once merged or
checked out for pairing.

## First Code Reading Path

Start with these files in order:

```text
apps/aigateway/src/aigateway/main.py
apps/aigateway/src/aigateway/routes/chat.py
apps/aigateway/src/aigateway/routes/models.py
apps/aigateway/src/aigateway/core/plugin_base.py
apps/aigateway/src/aigateway/core/loader.py
apps/aigateway/src/aigateway/core/registry.py
```

When the Anthropic provider branch is available, also read its `auth.py`,
`plugin.py`, live test, and any chat-route changes before writing `D-AIGW-002`.

## Where To Ask

Use `docs/team-development.md` for repo workflow and escalation rules. Ask Sergey
directly for architecture, ownership, credentials, and cross-service contract
questions.

Use Asana comments for scope/status decisions and GitHub PR comments for code
review. Link the PR back to the Asana ticket.
