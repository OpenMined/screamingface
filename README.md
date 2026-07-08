# ScreamingFace

An AI ensemble system that routes coding CLI prompts through multiple models (Claude, Gemini, Codex, Ollama) to beat SOTA benchmarks. Built by OpenMined.

> **Repo re-foundation (July 2026).** The legacy desktop app and plugin server
> were deprecated and removed; the full pre-teardown tree is preserved at the
> git tag **`legacy-monorepo-2026-07-08`**. New, separately-lifecycled packages
> (pure-Electron desktop app, Python CLI on PyPI, `url4` SDK) are being built —
> names are being finalized. Until they land, this repo hosts the two services
> below.

## Monorepo Layout

```
apps/
  aigateway/   LiteLLM-based AI Gateway — provider OAuth + encrypted credentials (Python, uv)
  scoreboard/  Public benchmark scoreboard service + demo portal (Python, uv)
packages/      Shared libraries (reserved — url4-python-sdk lands here first)
docs/          AI-agentic decision records (plans, specs)
```

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Python | ≥ 3.12 | `uv` installs and pins it for you |

## Quickstart

```bash
git clone https://github.com/OpenMined/screamingface.git
cd screamingface
git config core.hooksPath .githooks     # pre-commit guard (blocks commits to main)
```

Run an app:

```bash
# AI Gateway (port 9105)
cd apps/aigateway && uv sync && uv run uvicorn aigateway.main:app --port 9105 --reload

# Scoreboard (port 9106)
cd apps/scoreboard && uv sync && uv run scoreboard
```

Test an app (same pattern for both):

```bash
cd apps/<app>
uv run ruff check && uv run pyright && uv run pytest
```

## More

- **Developing / git workflow** → [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Gateway internals** → [`apps/aigateway/README.md`](apps/aigateway/README.md)
- **Scoreboard internals** → [`apps/scoreboard/README.md`](apps/scoreboard/README.md)
- **Legacy code** (desktop app, plugin server, url4 engine, marketing site, infra) → `git checkout legacy-monorepo-2026-07-08`
