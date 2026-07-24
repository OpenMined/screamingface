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
