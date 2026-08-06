---
ticket: OME-605
status: approved
date: 2026-07-31
---

# Provider connections through the SF Engine

## Outcome

A researcher can connect credentials for an AI Gateway-enabled provider from a
notebook before running an Evaluation:

```python
import screamingface as sf

sf.connect()
report = sf.evaluate(fusion, benchmark="draco", limit=1)
```

`sf.connect()` renders the provider-connections widget. The Engine derives its safe
provider catalogue from AI Gateway and advertises the authentication methods supported
by each enabled provider. The same Client surface handles API keys and bounded OAuth
authorization without provider-specific behavior.

## Seam

```text
Notebook → ScreamingFace Client → SF Engine → AI Gateway credential store
```

The Client never contacts AI Gateway, stores a provider secret, or receives AI Gateway
account IDs, connection IDs, credential locators, or access tokens.

These are ordinary SF Engine control-plane routes, not URL4 routes:

```text
GET    /v1/connections
PUT    /v1/connections/{provider}
POST   /v1/connections/{provider}/oauth
DELETE /v1/connections/{provider}
```

The list follows the existing catalogue envelope:

```json
{
  "object": "list",
  "data": [
    {
      "object": "connection",
      "provider": "openrouter",
      "display_name": "OpenRouter",
      "auth_methods": ["api_key"],
      "status": "not_connected",
      "auth_method": null,
      "account_label": null
    }
  ]
}
```

`PUT /v1/connections/{provider}` accepts only:

```json
{"api_key": "secret"}
```

and returns the sanitized connection row after AI Gateway has validated and stored
the key. The route is available only when that provider advertises `api_key`.

`POST /v1/connections/{provider}/oauth` starts authorization only when that provider
advertises `oauth`. It returns the provider, an absolute HTTPS authorization URL, and a
bounded expiry; AI Gateway connection IDs and OAuth state never cross the Engine
boundary. `DELETE` is idempotent and returns the disconnected row for either method.

## Engine behavior

- The Engine advertises each enabled AI Gateway provider and only its declared
  authentication methods.
- The Engine maps the public provider catalogue onto AI Gateway's preferred
  connection endpoints.
- Caller identity is forwarded using the same verified identity headers as model
  discovery and execution.
- API keys are represented as secret values, never logged, returned, or included in
  error details.
- Upstream authentication failures, invalid keys, conflicts, malformed responses,
  and timeouts become sanitized RFC 9457 problems.
- Local AI Gateway auth-disabled mode uses its anonymous account; hosted mode uses
  the mesh-injected caller identity.

## Client behavior

The synchronous interface is:

```python
sf.connect()
sf.connect("openrouter", api_key="...")
flow = sf.connect("codex", method="oauth")
flow.authorize_url
connection = flow.wait()  # or flow.cancel()
sf.connections.list()
sf.connections.get("openrouter")
sf.disconnect("openrouter")
```

Explicit `Client` values expose the same operations. `AsyncClient` exposes async
provider operations for a Tauri sidecar.

The widget preserves the previous UI and behavior:

- provider rows and status;
- method chooser;
- password input;
- save, cancel, refresh, authorize, and disconnect controls;
- inline sanitized errors;
- submitted keys cleared from widget memory;
- static HTML fallback outside an interactive notebook;
- bounded OAuth polling code retained but dormant until advertised.

## Non-goals

- Provider-specific authentication behavior not advertised by AI Gateway.
- Hosted SF Engine/Cloudflare caller login.
- Multiple selectable connections for one provider.
- Direct Client-to-AI-Gateway requests.
