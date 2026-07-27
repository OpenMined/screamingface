# url4-cloud

REST + WebSocket url4 execution runner (k8s Jobs + NATS). Design: `docs/spec/2026-07-21-url4-cloud.md`
· epic OME-513.

Two apps, two images, one tree (`apps/url4-cloud/`):
- **`backend/`** (`url4-cloud`) — the stateless control-plane App (REST + WebSocket). Image:
  `ghcr.io/openmined/screamingface-url4-cloud`.
- **`runner/`** (`url4-cloud-runner`) — the one-shot Job that executes a url4 expression and
  publishes telemetry to NATS. Image: `ghcr.io/openmined/screamingface-url4-cloud-runner`.
- **`shared/`** — libraries both apps depend on: `protocol/` (CloudEvents + OTel frame contract)
  and `bus/` (the NATS JetStream Bus port + adapters).

## Dev

```sh
uv sync
uv run pytest
uv run url4-cloud   # serve on :9108
```

## Model catalog — `GET /v1/models`

Discover which models an expression can address, proxied from aigateway's own `/v1/models` and
served from a per-credential cache. Design: `docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md`
· OME-625.

**A credential is required.** Send the one you already have — behind Cloudflare Access the edge
attaches `Cf-Access-Jwt-Assertion` for you, so a browser needs no extra code:

```sh
curl -H "Authorization: Bearer $AIGATEWAY_TOKEN" http://localhost:9108/v1/models
```

url4-cloud verifies nothing and **stores no aigateway credential of its own** — it forwards yours
and aigateway decides. Consequences worth knowing:

- **The answer is per credential.** Two callers can legitimately get different catalogs, which is
  what keeps this correct under either aigateway credential mode (`byok` / `shared`). Responses are
  therefore `Cache-Control: private` and carry `Vary`.
- **Caching is per credential too** — 5 min TTL, single-flight per key, and a stale entry is served
  if a refresh fails (bounded to 1 h) rather than failing open into "no models".
- **Enabled by `URL4_CLOUD_AIGATEWAY_BASE_URL`** — the same value the chart already sets as
  `config.aigatewayBaseUrl`. Unset ⇒ the endpoint answers `503`; everything else is a code default
  (see the `models_cache_*` fields in `config.py`).
- Cache behaviour is observable at `/metrics` (`url4_cloud_catalog_*`).
