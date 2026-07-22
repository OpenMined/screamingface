# ScreamingFace

An AI ensemble system that routes coding CLI prompts through multiple models (Claude, Gemini,
Codex, Ollama) to beat SOTA benchmarks. Built by OpenMined — [screamingface.ai](https://screamingface.ai).

## Monorepo Layout

```
apps/
  aigateway/   LiteLLM-based AI Gateway — provider OAuth + encrypted credentials (Python, uv)
  scoreboard/  Public benchmark scoreboard service + demo portal (Python, uv)
packages/
  url4/        URL4 grammar, DAG, node, client, and server library
  screamingface/ URL4-native fusion and benchmark SDK
docs/          SDLC artifacts — spec/ plan/ tasks/ work/ diagrams/ (see docs/README.md)
```

> **Repo re-foundation (July 2026).** The legacy desktop app and plugin server were deprecated
> and removed; the full pre-teardown tree is preserved at the git tag
> **`legacy-monorepo-2026-07-08`**. New, separately-lifecycled packages (pure-Electron desktop
> app, Python CLI on PyPI) are being built — names are being finalized. The public website
> lives in the separate `screamingface-web` repo; this monorepo does not publish GitHub Pages.

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

With a compatible ScreamingFace engine available, open the bare-bones SDK quickstart:

```bash
cd packages/screamingface
uv sync --extra notebook
uv run --extra notebook jupyter lab examples/00_quickstart.ipynb
```

The SDK communicates only with its configured HTTP URL4 engine; it does not bundle or start that
service. See the [`ScreamingFace SDK guide`](packages/screamingface/README.md) for the implemented
API and engine contract.

Run a service:

```bash
# AI Gateway (port 9105)
cd apps/aigateway && uv sync && uv run uvicorn aigateway.main:app --port 9105 --reload

# Scoreboard (port 9106)
cd apps/scoreboard && uv sync && uv run scoreboard
```

Check a stack — lint, format, typecheck, tests, and coverage in one command:

```bash
uv run .claude/scripts/run_gates.py <stack>   # aigateway | scoreboard | url4 | screamingface
```

## More

- **Developing / git workflow** → [`CONTRIBUTING.md`](CONTRIBUTING.md)
- **Gateway internals** → [`apps/aigateway/README.md`](apps/aigateway/README.md)
- **Scoreboard internals** → [`apps/scoreboard/README.md`](apps/scoreboard/README.md)
- **ScreamingFace SDK** → [`packages/screamingface/README.md`](packages/screamingface/README.md)
- **URL4 SDK examples** → [`packages/url4/examples/url4_examples.ipynb`](packages/url4/examples/url4_examples.ipynb)
- **url4 SDK** → [`packages/url4/README.md`](packages/url4/README.md)
- **Repo guide** (skills, agents, cards, process) → [`.claude/README.md`](.claude/README.md)
- **Legacy code** (desktop app, plugin server, url4 engine, marketing site, infra) → `git checkout legacy-monorepo-2026-07-08`
