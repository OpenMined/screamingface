---
title: ScreamingFace provider connections contract
ticket: OME-400
status: approved
date: 2026-07-20
---

# ScreamingFace provider connections contract

## 1. Decision

ScreamingFace owns a small model-provider connection UX over the configured
`screamingface-engine`. The SDK never contacts AI Gateway or a model provider directly, and the
engine never becomes another credential store:

```text
ScreamingFace SDK
  -> screamingface-engine
     -> AI Gateway
        -> provider
```

AI Gateway remains responsible for provider profiles, OAuth state, encrypted credential
persistence, and provider dispatch. ScreamingFace presents stable public provider identities and
sanitized connection state without exposing Gateway profile IDs, internal provider aliases, or
credentials.

Connections are needed only by model-backed stages. Loading, inspecting, or modifying benchmark
cases is independent of model-provider authentication.

## 2. Public Python surface

The complete MVP surface is:

```python
sf.connect()
sf.connect("codex")
sf.connect("gemini", method="oauth")
sf.connect("gemini", api_key=...)
sf.disconnect("gemini")
sf.connections.list()
```

Starting OAuth returns an immutable public `sf.OAuthFlow`:

```python
flow = sf.connect("codex")
flow.authorize_url
flow.status          # "pending"
connection = flow.wait()
flow.cancel()
```

`wait()` polls only the originating engine until the attempt connects, fails, is cancelled, or
expires; it returns the resulting immutable `Connection`. `cancel()` is idempotent. An
already-connected provider returns its existing `Connection` rather than an OAuth flow.

There is no `Fusion.connect()`, `Fusion.connections()`, `connection_status()`, setup/session
object, or separate provider client. Authentication is not part of `sf.config()`; that function
continues to select one engine origin.

`sf.connect()` renders the complete model-provider panel. `sf.connect(provider)` scopes the flow
to one provider. Resolution is deterministic:

- no provider renders all providers;
- a disconnected provider with exactly one advertised authentication method starts that method;
- a provider with multiple methods renders a choice and never selects one silently;
- `method="oauth"` starts OAuth explicitly;
- `api_key=...` selects API-key authentication without a redundant method argument;
- repeating an argument-free call for an already connected provider returns its current state
  without replacing it or starting another flow; and
- passing a new API key replaces an existing API-key credential.

`sf.disconnect(provider)` is idempotent and also cancels a pending OAuth attempt.

`sf.connections.list()` returns every provider supported by the configured engine, including
providers with `not_connected` status. Each immutable public `Connection` exposes only:

```python
connection.provider
connection.display_name
connection.auth_methods
connection.status
connection.auth_method
connection.account_label
```

The public statuses are `not_connected`, `pending`, `connected`, `needs_reauth`, and `error`.
`connected` means that AI Gateway holds a credential; it does not claim that the account can use
every advertised model.

## 3. Dataset access is separate

`sf.connect()` manages model providers only. Canonical datasets continue to load through the
researcher's Python process and their source library's ordinary credential mechanisms:

```text
Researcher Python -> Hugging Face / Kaggle / S3 / custom source
```

The engine never receives a Hugging Face token, benchmark cases, or sealed references. GPQA uses
the researcher's accepted terms plus `hf auth login` or `HF_TOKEN`. Other sources keep their own
native credentials. ScreamingFace reports source failures as a dedicated, actionable dataset
access error rather than a provider connection failure.

If Hugging Face is later offered as a model provider, its public provider identity must be
unambiguous (for example, `huggingface-inference`) and remains separate from Dataset Hub access.

## 4. Discovery and provider identity

Model discovery remains connection-independent:

```python
sf.models.list()
```

lists routes the configured engine supports. A route does not disappear because its provider is
disconnected, and a connected credential does not prove model entitlement. Researchers may
compose any advertised Fusion before authenticating.

The public `GET /.well-known/screamingface` document adds provider capabilities and explicit
provider ownership on model records. Representative fields are:

```json
{
  "providers": [
    {
      "id": "codex",
      "display_name": "OpenAI Codex",
      "auth_methods": ["oauth"]
    },
    {
      "id": "gemini",
      "display_name": "Google Gemini",
      "auth_methods": ["oauth", "api_key"]
    }
  ],
  "models": [
    {
      "id": "gemini/2.5",
      "provider": "gemini",
      "supported_tools": ["web_search"]
    },
    {
      "id": "claude/sonnet-4.6",
      "provider": "anthropic",
      "supported_tools": ["web_search"]
    }
  ]
}
```

The SDK never infers provider ownership from a model route prefix. Public `gemini` may map to AI
Gateway's private `gemini-cli`, and public `anthropic` may own a `claude/...` route. Those mappings
belong to the engine profile.

Provider capabilities are public. User connection status is not.

## 5. Engine control plane

URL4 evaluation remains the transactional GET data plane:

```http
GET /v1?q=<URL-encoded URL4 expression>
```

Provider connections use a distinct JSON control plane:

```text
GET    /v1/connections
GET    /v1/connections/{provider}
POST   /v1/connections/{provider}/oauth
PUT    /v1/connections/{provider}/api-key
DELETE /v1/connections/{provider}
GET    /v1/connections/oauth/callback
```

`/v1/api` is redundant and `/v1/auth` would conflate provider connections with authentication to
the ScreamingFace service. Control-plane paths are intercepted by the application-owned ASGI
wrapper; they are not URL4 endpoints or expressions. URL4 success results remain plaintext.
Connection management responses are JSON.

Except for the callback, all connection routes are private and scoped to the current user. Only
`/healthz` and `/.well-known/screamingface` are public. The OAuth callback is unauthenticated by
necessity and protected by a short-lived, single-use state nonce.

`GET /v1/connections` returns sanitized current-user state:

```json
{
  "schema": "screamingface.connections.v1",
  "connections": [
    {
      "provider": "codex",
      "status": "connected",
      "auth_method": "oauth",
      "account_label": "user@example.com"
    },
    {
      "provider": "gemini",
      "status": "not_connected",
      "auth_method": null,
      "account_label": null
    }
  ]
}
```

There is one public connection per provider in this MVP. Gateway profile names, connection UUIDs,
access tokens, refresh tokens, and stored keys never appear in the response.

Starting OAuth returns `provider`, `pending` status, `authorize_url`, and `expires_in`. Creating or
replacing an API key returns the sanitized connection record. Deletion returns HTTP 204, including
when the provider is already disconnected.

## 6. Gateway adapter and OAuth

The engine adapts the public provider identity to the existing AI Gateway `default` profile. It
forwards API keys once in a request body over the protected engine-to-Gateway transport; neither
SDK nor engine persists them. The local Docker hop is loopback HTTP inside the shared network
namespace, while a hosted hop must use an authenticated protected transport. AI Gateway encrypts
and stores the credential using its existing credential store.

OAuth uses the engine as the visible callback boundary:

```text
SDK -> engine start route -> Gateway OAuth start
    -> provider authorization page
    -> engine callback -> Gateway completion
    -> engine status route -> SDK
```

The browser never needs a public AI Gateway origin. The engine supplies its callback URL when
starting the Gateway flow, relays `code` and `state` for completion, and returns a minimal escaped
success or failure page. Provider deployment configuration must register the engine callback
origin.

Starting a new OAuth attempt replaces a stale pending attempt for that provider. Attempts expire
after ten minutes. The SDK, not the engine, performs bounded status polling and stops on a final
state, expiry, cancellation, or widget disposal.

No AI Gateway source change is authorized by this contract. The engine consumes Gateway's
existing profile, OAuth, API-key, callback, and credential-storage contracts.

## 7. Local and hosted identity boundary

The current MVP is a local Docker workflow:

- AI Gateway authentication is disabled;
- Gateway uses its loopback-only anonymous account;
- the host publishes engine and Gateway ports only on `127.0.0.1`; and
- no `sf.login()` or hosted ScreamingFace account flow is introduced.

Gateway data, encrypted credentials, and its locally persisted master key must live on a named
Docker volume so an ordinary `./dev.sh restart` preserves connections. Removing volumes is the
explicit destructive reset.

This local anonymous configuration is not deployable. Before a hosted engine is supported, its
connection routes and model evaluation must require the user's ScreamingFace authorization, and
the engine must forward that identity to AI Gateway. The public connection API and response
contract need not change when hosted identity is added.

## 8. Stage-specific preflight

Benchmark access is independent of model-provider connections:

```python
benchmark = sf.benchmarks.load("gpqa@1")  # dataset access only
run = fusion.run(benchmark)                # members + model reducer
grades = run.grade()                       # model judge, if configured
report = grades.aggregate()                # deterministic; no connection
```

`Fusion.evaluate(...)` performs all stages, so it checks the union of member, model-reducer, and
model-judge connections before model spend. This does not prevent a researcher from loading,
inspecting, or reusing benchmark cases.

Missing connections raise one `ConnectionRequiredError` before model requests. The error exposes
structured provider, model, and role information and tells the user which `sf.connect(...)` call
to make. Execution methods never open a widget implicitly or change their return type.

A stored credential may still be rejected by the provider. If that happens after preflight, the
SDK preserves completed work, stops scheduling new work that requires the rejected connection,
records the existing URL4 failure kind with the stable authentication error code, refreshes status
to `needs_reauth`, and gives a specific reconnect action. Work that does not depend on the rejected
provider remains unrelated and is allowed to finish. Tool capability failures and dataset access
failures remain separate.

## 9. Error contract

Connection endpoints normalize Gateway failures into:

```json
{
  "schema": "screamingface.error.v1",
  "code": "auth_method_not_supported",
  "message": "Codex does not support API-key authentication.",
  "provider": "codex",
  "retryable": false
}
```

Stable MVP codes are:

```text
authentication_required
connection_required
unknown_provider
auth_method_required
auth_method_not_supported
invalid_api_key
connection_pending
connection_needs_reauth
provider_access_denied
gateway_unavailable
gateway_timeout
```

Saving a credential validates only its presence and structural plausibility; it never makes a
hidden paid model call. `connected` means securely stored. A real provider request distinguishes
an expired/rejected credential from missing model entitlement.

Public errors contain no submitted keys, provider tokens, raw credential data, or unsafe upstream
bodies. Internal diagnostics may use a request ID and sanitized details.

## 10. Notebook and script UX

`sf.connect()` returns a notebook-renderable provider panel. The panel uses one compact row per
provider, expands controls in place, has no modal or nested scroll region, and always shows the
configured engine origin so the user knows where credentials will be stored.

The visual implementation follows the ScreamingFace design system: square geometry, hairline
rules, semantic tokens, monochrome structure, mono labels, no gradients, shadows, glow, purple, or
decorative color. Status is communicated with text and accessible controls, not color alone.

API-key inputs are masked and cleared after every attempt. A targeted Python call may create the
pending OAuth attempt, but browser navigation occurs only after an explicit button press. The
panel shows a prominent provider authorization link, supports cancel/manual refresh, and polls for
at most ten minutes. Connected rows show only sanitized method and account label plus Reconnect
and Disconnect actions. Account labels are escaped before rendering.

Outside notebooks, no hidden terminal prompt is used. Ambiguous providers instruct callers to
pass `method="oauth"` or `api_key=...`. An OAuth result exposes its authorization URL and a bounded
wait operation. Committed notebooks contain no live user status or account label.

## 11. Transport and secret safety

Plain HTTP is permitted only for `localhost`, `127.0.0.1`, and `::1`. A non-loopback engine must
use HTTPS before the SDK sends private status requests, account information, or provider keys.
Insecure credential submission fails locally before any request.

API keys:

- appear only in PUT request bodies;
- are never placed in a URL, redirect, log, exception, representation, widget serialization, or
  notebook output;
- are not retained by SDK result objects or engine state;
- are never echoed by the engine; and
- are not forwarded across an HTTP redirect.

Connection operations use bounded timeouts and response-size limits. OAuth state is short-lived
and single-use. Provider labels and callback text are escaped.

## 12. Acceptance

The Phase 6 implementation is accepted when:

1. public discovery advertises providers and explicit model-provider ownership without private
   Gateway aliases;
2. protected connection reads and mutations are user-scoped, sanitized, and distinct from URL4
   evaluation;
3. API-key and OAuth operations reach AI Gateway only through the engine;
4. local encrypted credentials survive an ordinary Docker restart and disappear only after an
   explicit volume reset or disconnect;
5. `sf.connect`, `sf.disconnect`, and `sf.connections.list` implement the exact approved surface;
   OAuth starts return `sf.OAuthFlow` with bounded `wait()` and idempotent `cancel()`;
6. benchmark loading remains independent of connection state and native dataset credentials never
   reach the engine;
7. run, grade, and evaluate perform their approved stage-specific preflights without repeated
   per-case missing-credential failures;
8. model discovery remains connection-independent;
9. secrets do not appear in any tested URL, error, log, representation, widget state, or notebook;
10. non-loopback private operations require HTTPS;
11. the widget satisfies the approved accessible, compact ScreamingFace design; and
12. no runtime mock, direct SDK-to-Gateway client, URL4-core change, or parallel credential store
    is introduced.
