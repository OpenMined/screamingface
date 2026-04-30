# aigateway

LiteLLM-compatible AI gateway. Exposes an OpenAI-shape `/v1/chat/completions`
endpoint and dispatches to upstream providers (Anthropic, OpenAI, Gemini,
Ollama, …) via [LiteLLM](https://github.com/BerriAI/litellm). Provider
concerns — OAuth tokens, refresh, response shaping — live in self-contained
plugins under `src/aigateway/plugins/`.

## Quick start

```bash
cd apps/aigateway
uv sync
uv run uvicorn aigateway.main:app --port 9105 --reload

# Sanity check
curl -sf http://localhost:9105/healthz
```

## Layout

```
src/aigateway/
  main.py            FastAPI app + plugin loader + uvicorn entry
  config.py          Settings (port, plugin discovery)
  cli.py             `aigateway` console-script entry point
  core/
    plugin_base.py   ProviderPluginBase contract
    registry.py      ProviderRegistry (custom_llm_provider → plugin)
    loader.py        Discovers plugins under aigateway.plugins.*
    oauth_bridge.py  litellm pre_call_hook → injects auth headers
  routes/
    chat.py          POST /v1/chat/completions (stream + non-stream)
    models.py        GET /v1/models (aggregated from plugins)
    health.py        GET /healthz
  plugins/           Provider plugins land here in follow-up PRs
tests/
  unit/
```

## Licensing note (LiteLLM)

We depend only on the MIT-licensed core `litellm` PyPI package. We must
**never** install `litellm-enterprise` or import from `litellm.enterprise.*` /
`litellm_enterprise.*` — those are governed by BerriAI's proprietary
Enterprise License. A CI guard in `scripts/check_no_enterprise.py` enforces
this.
