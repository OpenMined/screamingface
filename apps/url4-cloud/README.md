# url4-cloud

REST + WebSocket url4 execution runner (k8s Jobs + NATS). Design: `docs/spec/2026-07-21-url4-cloud.md`
· epic OME-513.

Two entrypoints from one image:
- **`url4-cloud`** — the stateless control-plane App (REST + WebSocket).
- **`url4-cloud-runner`** — the k8s Job that executes a url4 expression and publishes telemetry to NATS.

## Dev

```sh
uv sync
uv run pytest
uv run url4-cloud   # serve on :9108
```
