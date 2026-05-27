# Superseded By SF-219

This historical spec describes an OS credential-store design for AIGateway. It is superseded by SF-219, which replaces AIGateway runtime credential storage with Tortoise-backed `ORMStore` and the `credential_blobs` table. Do not use this document to reintroduce OS credential storage under `apps/aigateway`.

# AI Gateway: profile-based OAuth design

**Date:** 2026-04-30
**Status:** Approved (brainstorming complete; writing-plans is the next step)
**Supersedes:** the auth design implicit in SF-138 / SF-139

## Problem

The first cut of `apps/aigateway/` (SF-138 / SF-139) hardcoded a single
identity per provider, read directly from Claude Code's credential store entry,
and embedded all OAuth ownership inside provider plugins. There was no
notion of multiple accounts, no editing of per-account defaults from
the UI, and no separation between "who am I" and "what do I prefer".

We need:

1. **Multiple identities per provider.** A user may have a personal and a
   work Anthropic account, plus an OpenAI account, plus an Ollama at a
   custom URL — all selectable per request.
2. **Editable per-identity defaults.** Each identity carries a small set
   of preferred LLM defaults (model, max_tokens, temperature, …) that the
   Electron app can read and edit.
3. **A clean Electron UX surface.** Electron lists profiles, kicks off
   OAuth, shows progress, and edits defaults — without ever touching
   tokens or credential store.
4. **Stable trust boundary.** Tokens never leave the gateway process in
   plaintext at rest; OS credential store holds them.
5. **Backwards-compatible bootstrap.** Existing users with a working
   Claude Code credential store entry must not have to re-authenticate.

## Topology

```
AI frontend (claude/codex/gemini/ollama)
      │
      ▼
url4 executor
      │
      ▼
backend plugin (apps/server)        ← passes X-Profile through (or "default")
      │  POST /v1/chat/completions
      │  X-Profile: <name>
      │  body: OpenAI ChatCompletions
      ▼
AI Gateway (apps/aigateway)         ← OWNS auth: index, OAuth, refresh, header injection
      │
      ▼
upstream provider (Anthropic / OpenAI / Gemini / Ollama)


Electron app  ──────────► Gateway /v1/auth/* endpoints
                          (list profiles, start OAuth, status, edit, delete)
                          Electron is OAuth user-agent ONLY; never in chat path.
```

Trust model: every gateway endpoint binds to `127.0.0.1`. Any process on
the local machine that can reach the port is implicitly trusted. The
gateway does no caller authentication.

## Data model

A **profile** is the unit of identity. Each profile is one
`(provider, name)` pair with its own credentials and per-call defaults.

Two-layer storage. **Both layers live in the OS credential store.** Nothing
persists outside the credential store.

| Layer | What | Credential store entry |
|---|---|---|
| Index | Profile names + provider + scopes + last-refreshed timestamp + defaults JSON | `aigateway:index` (single entry, JSON-encoded) |
| Tokens | access_token, refresh_token, expires_at | `aigateway:<provider>:<profile_name>` (one per profile) |

The split lets Electron list profiles and edit defaults by reading and
writing only the index entry — token entries are decrypted only by the
gateway's chat dispatch path. Both entries are encrypted-at-rest by the
OS the same way SF-139 already does.

### Profile shape (in the index)

```json
{
  "version": 1,
  "profiles": [
    {
      "id": "anthropic:default",
      "provider": "anthropic",
      "name": "default",
      "account_label": "sergey@openmined.org",
      "scopes": ["user:inference", "user:profile"],
      "last_refreshed_at": "2026-04-30T18:14:22Z",
      "state": "authenticated",
      "defaults": {
        "model": "anthropic/claude-sonnet-4-5",
        "system_prompt": null,
        "max_tokens": null,
        "temperature": null,
        "timeout_seconds": null,
        "reasoning_effort": null
      }
    }
  ]
}
```

The `state` field in the profile shape is profile lifecycle status: one of
`pending` (auth started, callback not yet received), `authenticated`, or
`error`. (Distinct from the OAuth `state` parameter used as a CSRF guard
on the authorize URL — that one is internal to the pending-auth table
and never appears in the profile.)

### Token shape (one credential store entry per profile)

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at_ms": 1735680000000,
  "token_type": "Bearer",
  "issuer_metadata": {"sub": "...", "aud": "..."}
}
```

### Concurrency

- Per-process `asyncio.Lock` around the index read-modify-write cycle.
- Per-`(provider, profile_name)` `asyncio.Lock` for token refresh
  (carried forward from SF-139's `BaseOAuthStrategy`).
- v1 assumes a single gateway process. No multi-process credential store access.

## API surface

All endpoints bind to `127.0.0.1` only.

### Auth / profile (Electron-facing)

```
GET    /v1/auth/profiles
       → 200 {profiles: [...]}                   full index, no tokens

GET    /v1/auth/{provider}/profiles
       → 200 {profiles: [...]}                   filtered to one provider

POST   /v1/auth/{provider}/profiles
       body: {name: "work", defaults?: {...}}
       → 201 {profile_id, authorize_url, state, expires_in}
       Generates PKCE verifier+state, stashes in pending-auth table
       (TTL ~10 min). Profile row reserved with state = "pending".

GET    /v1/auth/{provider}/profiles/{name}/status
       → {state, account_label?, last_refreshed_at?, error?}

GET    /v1/auth/{provider}/callback?code=...&state=...
       Redirect target for the OAuth provider. Validates state, exchanges
       code for tokens, writes tokens to credential store, flips index row.
       Returns a tiny "you can close this window" HTML page.

PATCH  /v1/auth/{provider}/profiles/{name}
       body: {defaults?: {...}, account_label?: ...}
       → 200 {profile}
       Merges into index. Tokens unaffected. Cannot rename or change provider.

POST   /v1/auth/{provider}/profiles/{name}/refresh
       → 200 {profile}                           force a token refresh now

DELETE /v1/auth/{provider}/profiles/{name}
       → 204                                     removes index row + token entry
```

### Chat (existing, lightly updated)

```
POST   /v1/chat/completions
       header X-Profile: <name>                  default "default"
       body:  standard OpenAI ChatCompletions

GET    /v1/models
       Aggregated from provider plugins. Unchanged.

GET    /healthz
       Unchanged.
```

## Where every option lives (three buckets)

### Bucket A — Gateway profile defaults

Editable from Electron via `PATCH`. Travel with the auth identity. Apply
only when the request body omits the field.

| Field | Source | Rationale |
|---|---|---|
| `model` | mirrors `BackendProfile.model` | Per-account preferred model |
| `system_prompt` | mirrors `BackendProfile.system_prompt` | Per-account persona |
| `max_tokens` | new | Per-account ceiling |
| `temperature` | new | Per-account sampling |
| `timeout_seconds` | mirrors `BackendApiSettings.timeout_seconds` | Per-account upper bound |
| `reasoning_effort` | mirrors `BackendProfile.effort` | LiteLLM-supported per provider |

### Bucket B — Per-call request body

The `apps/server/` backend plugin builds an OpenAI ChatCompletions body
from its `BackendProfile`. Whatever the body sets **wins** over the
gateway profile's defaults.

| `BackendProfile` field | OpenAI request body field |
|---|---|
| `model` | `model` |
| `system_prompt` | first message with `role: "system"` |
| `append_system_prompt` | concatenated to the system message |
| `effort` | `reasoning_effort` |
| `output_format` | `response_format` |
| `tools` / `allowed_tools` / `disallowed_tools` | `tools` (definitions only — filtered through allow/deny lists; execution stays in `apps/server/`) |
| `timeout_seconds` | `timeout` |
| `fallback_model` | `fallbacks` |
| any other provider-specific knob | `extra_body` (passthrough) |

Resolution: per Bucket-A field, the gateway picks `body[field]` if
present, else `profile.defaults[field]`. No deep merging.

### Bucket C — Dropped at the apps/server boundary

CLI-only fields the existing `*_backend_api` plugins already mark as
"silently ignored":

- `permission_mode`
- `dangerously_skip_permissions`
- `add_dirs`
- `no_session_persistence`
- `max_budget_usd`
- `mcp_config`

Recorded as OTEL span attrs in `apps/server/`, never written to the
gateway request body. MCP execution stays in `apps/server/` as an
agent-loop concern.

## OAuth lifecycle

```
Electron                                        Gateway
─────────                                       ───────
POST /v1/auth/anthropic/profiles ──────────►    1. generate code_verifier + state
   {name: "work"}                               2. stash in pending-auth (TTL 10 min)
                                                3. reserve index row state=pending
◄────────── 201 {authorize_url, state}          4. return authorize_url

open BrowserWindow(authorize_url)
   user signs in at provider…
   provider redirects to
   localhost:9105/v1/auth/anthropic/callback ─► 5. validate state (CSRF guard)
                                                6. POST code + verifier to provider
                                                7. write tokens to credential store
                                                8. flip index row state=authenticated
◄──────── 200 "you can close this" HTML

GET .../profiles/work/status ───────────────►
◄────── {state: "authenticated", account_label}
```

**Pending-auth table** is in-memory only. State token is the CSRF guard;
unknown state on callback → 400. Entries swept on read past TTL.

**Refresh** is internal to the gateway. `BaseOAuthStrategy` (carried
forward from SF-139) caches, locks, proactively refreshes. No Electron
involvement post-initial-auth.

**Revocation:** `DELETE` removes both credential store entries. Best-effort POST
to provider's revoke endpoint where one exists; Anthropic does not, so
that path is no-op for them.

## Per-call flow (concrete)

State: `aigateway-backend-api.profiles.deep-research` is configured in
`apps/server/sf.json`. Gateway has an authenticated `anthropic:default`
profile with `defaults: {max_tokens: 4096, reasoning_effort: "medium"}`.

1. **Frontend → server:** `GET /aigateway?q=(...)!Summarize&profile=deep-research`
2. **Plugin reads `BackendProfile.deep-research`:**
   `{model: "anthropic/claude-opus-4-7", effort: "high", timeout_seconds: 600}`.
3. **Plugin builds OpenAI body** (CLI-only fields dropped):
   ```json
   {
     "model": "anthropic/claude-opus-4-7",
     "messages": [{"role": "user", "content": "<intent>\n\n<sources>"}],
     "reasoning_effort": "high",
     "timeout": 600
   }
   ```
4. **Plugin POSTs to gateway** with `X-Profile: default` (from
   `aigateway-backend-api.auth_profile`).
5. **Gateway resolves auth identity** = `(anthropic, default)`. Merges
   profile defaults for omitted body fields → `max_tokens` = 4096
   added; `reasoning_effort` stays `high`.
6. **Gateway fetches token** via `BaseOAuthStrategy.get_authorization_header()`
   (refreshes inside the lock if expired).
7. **Gateway extracts bearer** from the `Authorization` header, drops it
   into `litellm.acompletion(api_key=...)`; passes the rest of the
   provider headers via `extra_headers`.
8. **Gateway returns the OpenAI ChatCompletions response** to the
   plugin, which extracts the assistant text and returns it up the
   url4 → frontend chain.

## Error handling

| Failure | Gateway response | Caller action |
|---|---|---|
| `X-Profile` missing | falls back to `"default"` | n/a |
| Profile not found | `404 {error.code: profile_not_found}` | Surface; no retry |
| Profile pending auth | `409 {error.code: profile_pending_auth}` | Surface "complete in Electron" |
| Refresh failed (revoked / expired refresh token) | `401 {error.code: auth_required, reauth_url: ...}` | Pass through; Electron prompts re-auth |
| Upstream 401 after one refresh attempt | gateway invalidates cache, retries once; if still 401 → above | Pass through |
| Upstream 5xx | same status + body forwarded | SF plugin's existing retry/fallback |
| Body malformed | `400` | Surface |
| Credential store read/write failure | `500 {error.code: credential_store_error}` | Bubble up |

## Refactor scope vs SF-138 / SF-139

| SF-138/139 today | Becomes |
|---|---|
| `AnthropicOAuth` reads `CREDENTIAL_STORE_SERVICE = "Claude Code-credentials"` directly | Reads `aigateway:anthropic:<profile_name>`; first-run import-from-CC for the `default` profile only |
| `plugin.py` instantiates a single `AnthropicOAuth` lazily | One strategy per profile, cached per `(provider, profile_name)` |
| Provider plugin has a single fixed identity | Provider plugin advertises supported model list and `OAuthStrategy` *factory*; profiles live in the index |
| `routes/chat.py` does in-route auth resolution against a single strategy | New auth-resolution pipeline keyed on `X-Profile` header → index lookup → strategy factory |
| No `/v1/auth/...` endpoints | New auth router mounted under `/v1/auth/{provider}/...` |
| `oauth_bridge.py` (already deleted) | Stays deleted |

**Bootstrap behavior (one-time, on first start):**
- If `aigateway:index` is missing AND `Claude Code-credentials` exists in
  the OS credential store, copy that entry into `aigateway:anthropic:default`
  (token shape converted from Claude Code's wrapper) and write a fresh
  index with one `anthropic:default` profile.
- The original `Claude Code-credentials` entry is left untouched so the
  Claude Code CLI keeps working. The two diverge after the first
  refresh inside the gateway.

## Testing strategy

### Unit (gateway)
- Profile index round-trip (write → read → edit → delete).
- Index concurrency (interleaved PATCHes preserve both writes' fields).
- OAuth state machine: happy path + four failure branches (bad state,
  expired pending, provider 4xx on token exchange, credential store write fail).
- Per-call merge: body wins per field; missing fields fall back; CLI-only
  fields if present in body are passed through (gateway is dumb about
  them; SF backend plugin is responsible for dropping them upstream).
- Auth resolution: `X-Profile: nonexistent` → 404; default falls
  through; pending profile → 409.

### Live e2e (gateway)
- One end-to-end OAuth flow against real Anthropic via a `--manual`
  pytest helper (skipped in CI; requires a browser). Asserts the
  resulting profile authenticates a `/v1/chat/completions` round-trip.
- The existing SF-139 anthropic live test, retargeted to the
  profile-based path with `X-Profile: default`.

### `apps/server/` backend plugin
- Mock the gateway HTTP layer; verify the plugin builds the right body
  shape from each `BackendProfile` field.
- Verify CLI-only fields never leak into the body.
- Verify `X-Profile` defaults to `"default"` and uses `settings.auth_profile`
  when set.

## Out of scope

- Multi-process / multi-user gateway. v1 is one process per machine.
- Cloud-mode gateway (running inside the Enclave). Local-only for now.
- Cost tracking / spend metering inside the gateway. Existing
  `apps/server/` Spend pipeline remains the source of truth.
- Per-profile rate limiting.
- Importing Codex / Gemini CLI credential store entries the way we import
  Claude Code's. Those will require fresh OAuth in v1.
