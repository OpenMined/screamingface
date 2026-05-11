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

# Apply migrations for a persistent local DB. Re-running is safe.
# If your DB URL is in .env, export it first: set -a && source .env && set +a
uv run tortoise -c aigateway.db.TORTOISE_CONFIG migrate

uv run uvicorn aigateway.main:app --port 9105 --reload

# Sanity check
curl -sf http://localhost:9105/healthz
```

On first boot, set `AIGATEWAY_ADMIN_PASSWORD` to choose the admin password.
If it is unset, the gateway generates a 24-character password and logs it once
as `Bootstrap admin password: ...`.

Authenticated endpoints require a JWT:

```bash
TOKEN=$(curl -sX POST http://localhost:9105/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<admin-password>"}' | jq -r .token)

curl http://localhost:9105/v1/models -H "Authorization: Bearer $TOKEN"
```

For local-only development, auth can be bypassed with `AIGATEWAY_AUTH_ENABLED=0`.
Protected endpoints then run as an anonymous account with ID
`00000000-0000-0000-0000-000000000000`. Auth is enabled by default; do not use
this mode for shared or hosted deployments. OAuth profiles created in this mode
are scoped to the anonymous account.

User provisioning is intentionally separate from JWT auth. Set
`AIGATEWAY_PROVISIONING_TOKEN` to enable `POST /v1/accounts`:

```bash
curl -sX POST http://localhost:9105/v1/accounts \
  -H "X-Aigw-Provisioning-Token: $AIGATEWAY_PROVISIONING_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"alicepass123","display_name":"Alice"}'
```

If you expose aigateway to the public internet, you MUST front it with
rate-limiting such as Cloudflare or `nginx limit_req`. v1 does not implement
application-level rate limiting on `/v1/auth/login`.

Multi-worker deployments (`uvicorn --workers N` or a process manager equivalent)
MUST set `AIGATEWAY_JWT_SECRET` explicitly. The generated keychain fallback is a
local/single-worker convenience only.

## Operations

### Rotate `AIGATEWAY_JWT_SECRET`

Changing the JWT secret invalidates all sessions.

For explicit-env deployments, change `AIGATEWAY_JWT_SECRET` and restart all
workers. For local generated-secret deployments, delete the keychain entry with
service `aigateway:jwt-secret` and account `default`, then restart.

### Rotate `AIGATEWAY_PROVISIONING_TOKEN`

Change the `AIGATEWAY_PROVISIONING_TOKEN` environment variable and restart the
gateway. Existing JWTs are unaffected.

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
    auth/            Account model, JWT, password, provisioning helpers
  routes/
    auth_session.py  POST /v1/auth/login and GET /v1/auth/me
    accounts.py      POST /v1/accounts provisioning endpoint
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
