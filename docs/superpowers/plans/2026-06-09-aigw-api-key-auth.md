# AIGateway: API-Key Auth Alongside OAuth (D-AIGW-016)

**Date:** 2026-06-09
**Task:** `.agent-team-D-AIGW-016/initial_task_description.md`
**Status:** IMPLEMENTED on branch `SF-244-aigw-api-key-auth` (2026-06-09).
Deviations from plan: migration landed as `0006_connection_auth_type.py`
(0005 was taken by the secret-store work that merged meanwhile); chat dispatch
strategy resolution extracted to `_strategy_for_credential_target` to stay
within the complexity gate; ORMStore now encrypts at rest (SF-221) — no
behavior change for this feature, blobs ride the same store.
**Asana ticket:** [SF-244](https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215507593465846)

## Goal

Let AIGateway profiles authenticate to upstream providers with a user-provided
API key in addition to the existing OAuth flow. A user can create a profile
backed by a raw API key (no OAuth round-trip), make a successful
`/v1/chat/completions` call through it, and set/replace/delete the key from
the desktop app. OAuth stays the default; API key is purely additive.

---

## Verified current state (all file:line refs checked against the working tree)

| Fact | Where |
|---|---|
| Strategy port is `OAuthStrategy` ABC: `get_authorization_header / invalidate / persist_credentials / delete_credentials / refresh_credentials` | `apps/aigateway/src/aigateway/core/plugin_base.py:33-61` |
| Plugins return strategies via `ProviderPluginBase.oauth_strategy_for(profile_name, credential_store, http_client_factory)`; default `None` (no-auth, e.g. Ollama) | `core/plugin_base.py:111-119` |
| Template-method OAuth base with cache/lock/refresh; `_header_override()` escape hatch (unused) anticipated "hybrid api-key paths" | `core/oauth_base.py:105-107` |
| Chat dispatch resolves legacy JSON `Profile` first, then falls back to `OAuthConnection` by label; builds strategy and calls `get_authorization_header()`; pops `Authorization: Bearer X` into `body["api_key"]`, all other headers into `body["extra_headers"]` | `routes/chat.py:127-176`, `routes/chat.py:286-338` |
| Strategies are constructed **per request** — no cross-request in-memory state to worry about | `routes/chat.py:290`, `routes/auth.py:80-85` |
| Credential blobs: `credential_blobs` table (`service`, `account`, JSON `value`), `ORMStore` impl of `CredentialBlobStore` Protocol | `core/credential_blob/model.py`, `core/credential_blob/store.py` |
| Service keys: `aigateway:anthropic:{cred_name}` (account = settings.keychain_account), `aigateway:gemini:{cred_name}` / `aigateway:codex:{cred_name}` (account = `"default"`) | each plugin's `auth.py` |
| Migrations are **Tortoise built-in** (`tortoise.migrations`, ops-based, numbered files), NOT Aerich. Applied in deploy via Helm hook Job: `python -m tortoise -c aigateway.db.TORTOISE_CONFIG migrate`. Tests use `generate_schemas()` | `src/aigateway/migrations/0001-0004`, `db.py:16-29`, `DEPLOYMENT.md:163`. Installed `tortoise==1.1.7` ships `ops.AddField` (verified in `.venv`) |
| LiteLLM (installed 1.83.14) auto-disambiguates Anthropic keys passed as `api_key`: `sk-ant-oat…` → `Authorization: Bearer` + OAuth beta header; anything else → `x-api-key`. Verified in `litellm/llms/anthropic/common_utils.py::optionally_handle_anthropic_oauth` | `.venv` inspection |
| Gemini handler already has a full API-key request path (`_run_api_key`, `x-goog-api-key`) but it is only reachable via `GEMINI_API_KEY`/`GOOGLE_API_KEY` env vars | `plugins/gemini_provider/chat_handler.py:44`, `:302-312` |
| Codex handler **hard-rejects** `sk-`/`sk-proj-` keys: "Codex subscription models are not available via OpenAI API key fallback" — upstream is the ChatGPT subscription Responses endpoint, OAuth-only | `plugins/codex_provider/chat_handler.py:317-326` |
| Profile JSON index is a Pydantic `ProfileIndex` blob (`aigateway:index`/`default`); unknown→default fields deserialize cleanly, so adding a defaulted field is migration-free | `core/profile_index.py:22-26`, `core/profile_models.py` |
| `OAuthConnection` has abstract `BaseOAuthConnection` (tortoise-dev Rule 2 already satisfied); `Meta` first ✓ | `core/oauth/models/oauth_connection.py` |
| Desktop profile-auth IPC lives in `backend-status.ipc.ts` (`backends:listProfiles`, `backends:authenticateOAuth`, `backends:deleteProfile`…) — **not** `aigw-session.ipc.ts` (that file is gateway login/session). Task description's pointer is corrected here | `apps/desktop/src/main/ipc/backend-status.ipc.ts:66-297` |
| SF server proxies desktop → gateway: `auth_proxy_router.py` maps `/{prefix}/auth/profiles…` → `/v1/auth/{provider}/profiles…`; chat sends `X-Profile` header only — server never handles provider credentials | `apps/server/src/screamingface/plugins/aigw_base/auth_proxy_router.py:92-302`, `backend.py:157-236` |

---

## Key decisions (the "document the choice" items)

### D1. Which model path supports API keys (task note, line 34)
**Profile path (legacy JSON index) gets full end-to-end support in v1.**
The `OAuthConnection` table gets the `auth_type` column + dispatch support
(cheap, forward-compatible), but **no api-key connection creation endpoint
yet**. Rationale: desktop ProfilesSubPanel, the SF server proxy routes, the
`X-Profile` chat header, and backend health checks all run on the profile path
today — acceptance is reachable with the smallest surface. A follow-up ticket
can add `POST /v1/oauth/connections` with `auth_type=api_key` (skip
pending/callback, create `active` row) without schema changes.

### D2. Strategy architecture — sibling class, not `_header_override`
`ApiKeyStrategy` implements the strategy **port directly**; it does NOT
subclass `BaseOAuthStrategy`. Inheriting the OAuth template method would drag
in refresh/expiry contract that API keys don't have (Liskov violation — dead
contract). The port ABC in `core/plugin_base.py` is renamed
`CredentialStrategy` with a back-compat alias `OAuthStrategy =
CredentialStrategy` (zero-churn for existing plugins/tests; new code uses the
new name). `_header_override` at `oauth_base.py:105` stays untouched (it
serves env-var short-circuits, a different concern).

### D3. One generic core class, per-provider parameterization
One `ApiKeyStrategy` in core, configured by each plugin with its credential
`service`/`account` strings and a `header_builder: Callable[[str], dict[str,
str]]`. Core never imports plugins (dependency direction ✓); plugins
instantiate core's class (Open/Closed ✓ — adding a provider's api-key support
touches only that plugin).

### D4. Storage — same credential slot, discriminated content
The API key reuses the profile's existing blob slot
(`aigateway:{provider}:{account_id}:{name}` + provider's account string) with
content `{"auth_type": "api_key", "api_key": "..."}`. No `credential_blobs`
schema change. Consequences (intended): setting a key replaces any OAuth
tokens for that profile and vice-versa (a profile is exactly one auth at a
time); the existing `delete_profile` flow deletes the key with no extra code
path. OAuth blobs lack `auth_type` → treated as `"oauth"`.

### D5. Per-provider support matrix in v1
| Provider | v1 | Mechanism |
|---|---|---|
| anthropic | ✅ | `header_builder` returns `{"Authorization": f"Bearer {key}"}`; chat.py pops it into `body["api_key"]`; LiteLLM 1.83.14 routes non-`oat` keys to `x-api-key` (verified). No OAuth beta header leaks (that's added by LiteLLM only for `sk-ant-oat…`). |
| gemini | ✅ | `header_builder` returns `{"x-goog-api-key": key}` → flows via `extra_headers` to the custom handler (same conduit `ChatGPT-Account-Id` uses today); handler gains a check for `x-goog-api-key` in `headers` ahead of the env-var fallback, reusing the existing `_run_api_key` path. |
| codex | ❌ v1 | Upstream subscription endpoint is OAuth-only; handler already hard-rejects `sk-` keys (`chat_handler.py:322`). Plugin does not override `api_key_strategy_for` → set-key endpoint returns 400 `api_key_not_supported`. Follow-up option: route api-key codex profiles to the OpenAI platform Responses API (separate ticket — different base URL, payload, model availability). |
| ollama | n/a | No auth; unchanged. |

### D6. No key validation round-trip in v1
The set-key endpoint stores the key and marks the profile `AUTHENTICATED`; a
bad key surfaces as 401 on first chat (existing error path already marks the
profile `ERROR`). Optional follow-up: a cheap live probe (e.g. provider
models endpoint) behind `?validate=true`.

---

## Phase 1 — AIGateway

### M1. Core port + `ApiKeyStrategy`

**`core/plugin_base.py`**
- Rename ABC `OAuthStrategy` → `CredentialStrategy`; add module-level alias
  `OAuthStrategy = CredentialStrategy` (keeps all imports working).
- Add to `ProviderPluginBase`:

```python
def api_key_strategy_for(
    self,
    profile_name: str,
    *,
    credential_store: CredentialBlobStore | None = None,
) -> CredentialStrategy | None:
    """Return a per-profile API-key strategy, or None if unsupported."""
    return None

def credential_strategy_for(
    self,
    profile_name: str,
    *,
    auth_type: AuthType = "oauth",
    credential_store: CredentialBlobStore | None = None,
    http_client_factory: Any | None = None,
) -> CredentialStrategy | None:
    if auth_type == "api_key":
        return self.api_key_strategy_for(profile_name, credential_store=credential_store)
    return self.oauth_strategy_for(
        profile_name,
        credential_store=credential_store,
        http_client_factory=http_client_factory,
    )
```

**New `core/api_key_strategy.py`** (`AuthType = Literal["oauth", "api_key"]`
lives in `core/profile_models.py`):

```python
class ApiKeyStrategy(CredentialStrategy):
    """Per-profile DB-backed API-key credentials. No refresh semantics."""

    def __init__(self, profile_name, *, service, account, header_builder,
                 credential_store=None) -> None: ...

    async def get_authorization_header(self) -> dict[str, str]:
        # read blob → json → require {"auth_type": "api_key", "api_key": str}
        # missing blob → CredentialNotFoundError; wrong shape → AuthError
        return self._header_builder(api_key)

    async def persist_credentials(self, credentials) -> None: ...  # validate + write
    async def delete_credentials(self) -> None: ...                # store.delete
    async def refresh_credentials(self) -> None: ...               # documented no-op
    async def invalidate(self) -> None: ...                        # no-op (no cache)
```

No caching needed — strategies are constructed per request (verified above).

### M2. Models + migration

- **`core/profile_models.py`** — `Profile` gains
  `auth_type: AuthType = "oauth"`. Existing index JSON deserializes with the
  default → zero migration friction (constraint satisfied).
- **`core/oauth/models/oauth_connection.py`** — `BaseOAuthConnection` gains
  `auth_type = fields.CharField(max_length=16, default="oauth")` (in the
  fields block; `Meta` stays first — tortoise-dev Rules 2–4 hold).
- **New `migrations/0005_connection_auth_type.py`** — deps
  `("models", "0004_gemini_credential_locator")`, `ops.AddField` with default
  `"oauth"`. Prefer auto-generating via
  `python -m tortoise -c aigateway.db.TORTOISE_CONFIG makemigrations`, then
  review/rename. Applied in prod by the existing Helm hook Job.

### M3. Set/replace API-key endpoint (`routes/auth.py`)

```
PUT /v1/auth/{provider}/profiles/{name}/api-key   (CurrentAccount-protected)
body: { "api_key": str (min_length=8), "defaults": ProfileDefaults | null }
```

- Unknown provider → 404 `unknown_provider`.
- `plugin.credential_strategy_for(credential_name, auth_type="api_key", …)`
  → `None` → 400 `{"code": "api_key_not_supported", "provider": …}` (codex).
- Upsert profile: `auth_type="api_key"`, `state=AUTHENTICATED`,
  `last_refreshed_at=now`, `account_label=f"API key ····{key[-4:]}"`;
  `strategy.persist_credentials({"auth_type": "api_key", "api_key": key})`;
  `_invalidate_profile_session(...)`. Response = profile JSON — the key is
  **never** echoed back or logged.
- Generalize `_oauth_strategy_for_app` → `_credential_strategy_for_app(…,
  auth_type)`; `delete_profile` (auth.py:979) and `refresh_profile`
  (auth.py:995) pass `p.auth_type` so delete removes the key blob and refresh
  no-ops successfully for api-key profiles.
- `_mark_profile_authenticated` (OAuth callback path) explicitly sets
  `auth_type="oauth"` so re-OAuth of a former api-key profile flips the
  discriminator back, matching the overwritten blob (D4).
- `profile_status` (auth.py:937) adds `auth_type` to its response; list/get
  endpoints pick it up automatically via `model_dump`.

### M4. Chat dispatch (`routes/chat.py:286-301`)

```python
auth_type = (
    getattr(connection, "auth_type", "oauth") if connection is not None
    else (profile.auth_type if profile is not None else "oauth")
)
strategy = plugin.credential_strategy_for(
    credential_name, auth_type=auth_type,
    credential_store=request.app.state.credential_store,
    http_client_factory=getattr(request.app.state, f"{provider}_http_factory", None),
)
```

Everything downstream (header pop → `body["api_key"]`, `extra_headers` merge,
error handling) is unchanged. `reauth_url` in 401 details is harmless for
api-key profiles (re-PUT the key is the remedy; desktop UI handles it).

### M5. Provider plugins

- **`plugins/anthropic_provider/plugin.py`** — override `api_key_strategy_for`
  returning `ApiKeyStrategy(profile_name, service=credential_service_for(profile_name),
  account=self.settings.keychain_account, header_builder=lambda k:
  {"Authorization": f"Bearer {k}"}, credential_store=…)`.
- **`plugins/gemini_provider/plugin.py`** — same shape with
  `service=f"aigateway:gemini:{profile_name}"`, `account="default"`,
  `header_builder=lambda k: {"x-goog-api-key": k}`.
- **`plugins/gemini_provider/chat_handler.py`** — in `acompletion` (and the
  streaming twin if present — verify parity during impl), before the env-var
  fallback: `header_key = (headers or {}).get("x-goog-api-key")` → if set, run
  `_run_api_key(...)`. Update the 401 message to mention profile API keys.
- **`plugins/codex_provider/`** — no override (returns `None`). Add a comment
  pointing at `chat_handler.py:322` for the why.

### M6. Tests (mirror existing patterns: `conftest.py` SQLite probe + `authenticated_client`)

| Test | Covers |
|---|---|
| `tests/unit/test_api_key_strategy.py` | header building per builder; missing blob → `CredentialNotFoundError`; non-JSON/missing-key blob → `AuthError`; `refresh_credentials` no-op; `persist`/`delete` round-trip with a dict-backed fake store (no DB — strategy is unit-testable through the port, tortoise-dev Rule: mock via interface) |
| `tests/unit/test_api_key_routes.py` | PUT happy path (profile created `AUTHENTICATED`, `auth_type="api_key"`, blob content verified via `credential_blobs` probe, response/`status` include `auth_type`, key never echoed); replace key; PUT over existing OAuth profile flips type and overwrites blob; codex → 400 `api_key_not_supported`; unknown provider → 404; DELETE removes blob; refresh on api-key profile → 200 no-op; existing profiles list shows `auth_type:"oauth"` default |
| extend `tests/unit/test_chat_x_profile.py` (or sibling) | chat with anthropic api-key profile → captured LiteLLM body has `api_key == raw key` and **no** OAuth beta in `extra_headers`; gemini api-key profile → `extra_headers["x-goog-api-key"]` set |
| `tests/unit/gemini/…` handler test | `headers={"x-goog-api-key": …}` routes to `_run_api_key` (mock httpx transport), env vars unset; precedence: explicit `api_key` (OAuth) > header key > env key |
| migration sanity | fresh-DB `migrate` applies 0005 (covered implicitly if a migration-runner test exists; else verified manually + by Helm job in staging) |

Run: `uv run pytest tests/unit -q` plus repo lint hooks.

---

## Phase 2 — Desktop + SF server (after Phase 1 lands)

### Server (`apps/server/src/screamingface/plugins/aigw_base/`)
- **`auth_proxy_router.py`** — add `PUT /{prefix}/auth/profiles/{name}/api-key`
  proxying to gateway `PUT /v1/auth/{gateway_provider}/profiles/{name}/api-key`
  via the existing `AigwGatewayClient` (Bearer JWT in external mode — same as
  other routes). Profiles list/status responses are passthrough JSON, so
  `auth_type` surfaces with no further change.
- **`client.py`, `config.py`, `backend.py`** — **no changes** (verified): chat
  still sends only `X-Profile`; the gateway resolves auth internally; health
  check reads profile `state`, which api-key profiles satisfy.

### Desktop (`apps/desktop/`)
- **`src/preload/types.ts`** — `BackendProfile` gains
  `auth_type?: 'oauth' | 'api_key'`; add
  `setProfileApiKey(backend, profileName, apiKey): Promise<SetProfileApiKeyResult>`
  to the `backends` surface (+ result type).
- **`src/main/ipc/backend-status.ipc.ts`** — new `backends:setProfileApiKey`
  handler (task description said `aigw-session.ipc.ts`; corrected — that file
  is gateway session login). Pattern-match `deleteProfile`:
  `isSafeBackendName` guard, `PUT ${sfBaseUrl}/${backend}/auth/profiles/${encodeURIComponent(name)}/api-key`
  with `desktopSecretHeader()`, JSON body `{api_key}`. Never log the key.
- **`src/preload/index.ts`** — expose the new bridge method.
- **`src/renderer/src/components/server/BackendStatusPanel.tsx`** —
  ProfilesSubPanel add-profile form gains an auth-type selector (OAuth default
  / API key); API-key mode shows a masked (`type="password"`) input + Save →
  `setProfileApiKey`. `ProfileRow` shows an `API key` badge for
  `auth_type === 'api_key'`, swaps "Re-authenticate" for "Replace key"
  (re-opens masked input), keeps Delete.
- Desktop tests in `src/main/ipc/__tests__/` mirroring existing handler tests.

---

## Architecture / SOLID / tortoise-dev compliance check

- **Dependency direction** — `ApiKeyStrategy` lives in core and implements the
  core port; plugins instantiate and parameterize it. Core imports nothing
  from plugins. ✓
- **OCP** — new behavior arrives via two new overridable hooks on
  `ProviderPluginBase` with safe defaults; no provider conditionals in core. ✓
- **LSP** — `ApiKeyStrategy` is substitutable everywhere a strategy is used
  (chat dispatch, delete, refresh); it does not inherit OAuth's
  expiry/refresh template, avoiding dead contract. `refresh_credentials` as
  no-op is the one mild ISP wart — splitting the port into
  header-producer/refreshable interfaces was judged churn > value; documented. ✓
- **DRY** — Gemini reuses its existing `_run_api_key`; Anthropic reuses
  LiteLLM's built-in key handling; one generic strategy class instead of three
  per-provider copies. ✓
- **tortoise-dev rules** — model change goes on the abstract
  `BaseOAuthConnection` (Rule 2 interface preserved), `Meta` first / member
  order kept (Rules 3-4), models stay one-per-file in subpackages (Rules 0-1),
  migration via the repo's built-in-migrations convention, committed and
  reviewed; tests mock through the `CredentialBlobStore`/`CredentialStrategy`
  interfaces, no prod `generate_schemas()`. ✓
- **AIGateway guardrail** — keys live in `credential_blobs` via ORMStore
  (SQLite local / Postgres hosted); no OS keychain anywhere. Same at-rest
  trust level as existing OAuth refresh tokens. ✓

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| LiteLLM upgrade changes Anthropic key-prefix handling | Chat test pins observable behavior (raw key lands in `body["api_key"]`, request carries `x-api-key`); failure would be caught by the test, fallback is an explicit `x-api-key` header_builder + small chat.py tweak |
| Gemini streaming parity on the api-key path | Implementation-time checkbox: verify `_run_api_key` streaming twin or constrain `supports_chat_streaming` accordingly; covered by handler test |
| `tortoise.migrations` AddField shape (newer framework, less community precedent) | Auto-generate with `makemigrations`, review diff, smoke-test `migrate` on a copy of a real SQLite DB |
| Profile↔connection ambiguity (profile wins over same-label connection) | Unchanged from today; api-key support follows the existing precedence rules |
| Key leakage in logs/responses | Endpoint never echoes the key; desktop masks input; explicit test asserts absence in responses; review grep for logging of request bodies on the new route |

## Acceptance mapping

1. *Create profile authenticating via API key, no OAuth round-trip* → M3 (PUT
   endpoint, instant `AUTHENTICATED`).
2. *Successful `/v1/chat/completions` through the key* → M4 + M5 (anthropic &
   gemini verified paths).
3. *Manage (set/replace/delete) from desktop* → Phase 2 (set/replace via new
   IPC + masked UI; delete via existing flow which now removes the key blob).

## Open questions (recommendations inline)

1. **Codex v1 = unsupported (400)** — recommended; OpenAI-platform routing is
   a separate ticket. OK?
2. **Live key validation on set** — recommend skip in v1 (D6). OK?
3. **Api-key creation on the connections path** — recommend defer (D1). OK?

**Confidence: ~96%.** All integration points verified against the working
tree, the installed `litellm==1.83.14` and `tortoise==1.1.7`, and the
deployment docs. Residual 4%: gemini streaming parity, exact auto-generated
migration shape, and desktop preload bridge plumbing details — all
implementation-time verifiable without affecting the design.
