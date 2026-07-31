---
ticket: OME-605
status: approved
date: 2026-07-31
---

# OpenRouter connections through the SF Engine

## Outcome

A researcher can connect an OpenRouter API key from a notebook before running an
Evaluation:

```python
import screamingface as sf

sf.connect()
report = sf.evaluate(fusion, limit=1)
```

`sf.connect()` renders the existing rich provider-connections widget. The first
implementation advertises one OpenRouter row; the widget retains its general API-key
and OAuth controls so later Engine-advertised providers require no public Client change.

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

`PUT /v1/connections/openrouter` accepts only:

```json
{"api_key": "secret"}
```

and returns the sanitized connection row after AI Gateway has validated and stored
the key. `DELETE` is idempotent and returns the disconnected row.

## Engine behavior

- OpenRouter is the only advertised provider in this slice.
- The Engine maps the single public provider row onto AI Gateway's preferred
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

- General AI Gateway provider discovery.
- An OpenRouter OAuth flow.
- Hosted SF Engine/Cloudflare caller login.
- Multiple selectable connections for one provider.
- Direct Client-to-AI-Gateway requests.
