# ScreamingFace

An AI ensemble system that routes coding CLI prompts through multiple models (Claude, Gemini, Codex, Ollama) to beat SOTA benchmarks. Built by OpenMined.

> **Repo re-foundation (July 2026).** The legacy desktop app and plugin server
> were deprecated and removed; the full pre-teardown tree is preserved at the
> git tag **`legacy-monorepo-2026-07-08`**. Active services and Python packages
> now have separate toolchains and CI lanes.

## Monorepo Layout

```
apps/
  aigateway/   LiteLLM-based AI Gateway — provider OAuth + encrypted credentials (Python, uv)
  scoreboard/  Public benchmark scoreboard service + demo portal (Python, uv)
packages/
  url4/        URL4 grammar, DAG, node, client, and server library
  screamingface/ URL4-native fusion and benchmark SDK
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

Run the zero-setup SDK quickstart:

```bash
cd packages/screamingface
uv sync --extra notebook
uv run --extra notebook jupyter lab examples/00_quickstart.ipynb
```

The notebook uses a real in-process URL4 node with deterministic model-route responses. It does
not require AI Gateway, provider credentials, or a background server. See the
[`ScreamingFace SDK API and execution guide`](packages/screamingface/docs/index.html) for the full
boundary and wire contract.

Run a service:

```bash
# AI Gateway (port 9105)
cd apps/aigateway && uv sync && uv run uvicorn aigateway.main:app --port 9105 --reload

# Scoreboard (port 9106)
cd apps/scoreboard && uv sync && uv run scoreboard
```

Test a Python component:

```bash
cd apps/<app>                    # or packages/<package>
uv run ruff check && uv run pyright && uv run pytest
```

## More

- **Developing / git workflow** → [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Gateway internals** → [`apps/aigateway/README.md`](apps/aigateway/README.md)
- **Scoreboard internals** → [`apps/scoreboard/README.md`](apps/scoreboard/README.md)
- **ScreamingFace SDK** → [`packages/screamingface/README.md`](packages/screamingface/README.md)
- **ScreamingFace SDK API** → [`packages/screamingface/docs/index.html`](packages/screamingface/docs/index.html)
- **URL4 SDK examples** → [`packages/url4/examples/url4_examples.ipynb`](packages/url4/examples/url4_examples.ipynb)
- **Legacy code** (desktop app, plugin server, url4 engine, marketing site, infra) → `git checkout legacy-monorepo-2026-07-08`
