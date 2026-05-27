---
title: aigw-*-backend OAuth Authenticate button
status: proposed
asana_task: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214600798519030
asana_gid: 1214600798519030
created: 2026-05-07
---

# Superseded By SF-219

This historical spec describes an OS credential-store design for AIGateway. It is superseded by SF-219, which replaces AIGateway runtime credential storage with Tortoise-backed `ORMStore` and the `credential_blobs` table. Do not use this document to reintroduce OS credential storage under `apps/aigateway`.

# aigw-*-backend OAuth Authenticate button

## Goal

When an aigw-*-backend plugin (currently just `aigw-claude-backend`, more
later) lacks a usable token at the AI Gateway, surface an **Authenticate**
button in the SF Settings → Backend Status panel that walks the user
through the gateway-managed OAuth flow. The gateway stores the resulting
token in its credential store; the SF server never holds it.

This is the gateway equivalent of today's `claude-backend-api`
"Re-authenticate" button — same panel, same look, but the action opens a
browser instead of running a terminal command.

## Background

`apps/aigateway` already exposes the full OAuth lifecycle:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/auth/{provider}/profiles` | Create/upsert PENDING profile, return `authorize_url` |
| `GET`  | `/v1/auth/{provider}/callback` | Exchange code, mark profile AUTHENTICATED |
| `GET`  | `/v1/auth/{provider}/profiles/{name}/status` | Read profile state |
| `POST` | `/v1/auth/{provider}/profiles/{name}/refresh` | Token refresh (no PKCE) |
| `DELETE` | `/v1/auth/{provider}/profiles/{name}` | Drop profile + tokens |

The aigw-*-backend SF plugins talk to the gateway over `X-Profile`
(`auth_profile` setting, default `"default"`). They have no mechanism
today to start an OAuth cycle, observe profile state, or signal the
Electron renderer that the user must act.

The Electron `BackendStatusPanel` already renders a button when
`health.action === "reauth"`. It currently hard-codes the action to
`window.electronAPI.backends.authenticate(name)`, which spawns a terminal
running `<cli> auth login`. We need a parallel browser-OAuth path.

## Scope

In:
- New SF auth-proxy router under each aigw-*-backend's path prefix
  (e.g. `/claude/auth/start`, `/claude/auth/status`).
- `AigwBackend.health()` probes the gateway's profile status so the
  Backend Status panel knows when to show the button.
- A new field `auth_kind: "cli" | "browser"` on the `/backends/status`
  payload so the renderer picks the right action.
- New Electron main-process OAuth launcher: `POST .../auth/start` →
  `shell.openExternal(authorize_url)` → poll `.../auth/status` until
  AUTHENTICATED or timeout.
- New IPC channel `backends:authenticateOAuth`.
- Renderer wiring: `BackendStatusPanel` calls `authenticateOAuth(name)`
  when `auth_kind === "browser"`, with optimistic "Waiting for
  browser..." state and toast on completion.
- Integration test that boots a real aigateway subprocess with a fake
  upstream provider OAuth server and drives the full flow through the SF
  endpoints.

Out:
- Multi-profile management UI. The single `auth_profile` setting suffices
  for the first cut; deferred to a follow-up spec.
- Account-label autodetection. Gateway leaves it null today;
  `PATCH .../profiles/{name}` already lets the user set it.
- Token revocation / disconnect button.
- Provider-OAuth retry/error reporting beyond the broad categories
  listed in *Error paths* below.

## Architecture

```
┌─ Electron renderer (BackendStatusPanel) ─────────────┐
│  Existing button → new IPC channel                    │
└────────────┬─────────────────────────────────────────┘
             │ window.electronAPI.backends.authenticateOAuth(name)
┌────────────▼─────────────────────────────────────────┐
│ Electron main: services/oauth-launcher.ts             │
│  1. POST  http://sf/<name>/auth/start                 │
│  2. shell.openExternal(authorize_url)                 │
│  3. poll  http://sf/<name>/auth/status   (every 2s)   │
│  4. emit  'oauth:complete' | 'oauth:failed'           │
└────────────┬─────────────────────────────────────────┘
             │ HTTP
┌────────────▼─────────────────────────────────────────┐
│ SF server: aigw_base auth proxy router                │
│  POST /<prefix>/auth/start                            │
│  GET  /<prefix>/auth/status                           │
│  → both proxy to aigateway over loopback              │
└────────────┬─────────────────────────────────────────┘
             │ HTTP (with X-Profile)
┌────────────▼─────────────────────────────────────────┐
│ aigateway: existing OAuth routes                      │
│  POST /v1/auth/{provider}/profiles                    │
│  GET  /v1/auth/{provider}/profiles/{name}/status      │
│  GET  /v1/auth/{provider}/callback   ← browser hits   │
│                                         this directly  │
└──────────────────────────────────────────────────────┘
```

The browser hits the gateway's callback URL directly. The SF server is
not on the OAuth callback path; its only job is to start the flow and
report status.

## Components

### 1. `aigw_base/auth_proxy_router.py` (new)

Mounted by every aigw-*-backend at `<backend_call_path>/auth/...`. Two
routes:

- `POST /auth/start` →
  - calls aigateway `POST /v1/auth/{gateway_provider}/profiles`
    with body `{name: settings.auth_profile}`
  - returns `{authorize_url, profile_id, expires_in, state}`
  - errors: 502 if gateway unreachable; passthrough for 4xx
- `GET /auth/status` →
  - calls aigateway `GET /v1/auth/{gateway_provider}/profiles/{name}/status`
  - returns `{state, account_label, last_refreshed_at}` verbatim
  - 404 if profile not yet created (before first start)

The aigateway's `POST .../profiles` is already idempotent on
`id = "{provider}:{name}"` (see `ProfileIndexStore.upsert`). Re-clicking
Authenticate after a previous attempt PENDING-ed out simply replaces the
pending entry with a fresh PKCE state.

### 2. `AigwBackendApiPluginBase` extension

Add a class attribute `gateway_provider: str` that subclasses set, e.g.
`aigw_claude_backend` sets `gateway_provider = "anthropic"`. The base
class wires the auth-proxy router into `create_router` automatically, so
no per-plugin code change beyond the attribute.

### 3. `AigwBackend.health()` update

Today `health()` is a stub returning `authenticated=False, error="not implemented"`.
Replace with: probe gateway's
`GET /v1/auth/{provider}/profiles/{name}/status`. Map gateway profile
state → `HealthStatus`:

| Gateway state | `authenticated` | `error` |
| --- | --- | --- |
| `AUTHENTICATED` | `True` | None |
| `PENDING` | `False` | `"OAuth in progress"` |
| `ERROR` | `False` | profile error message |
| 404 (no profile) | `False` | `"Profile not yet created"` |
| Gateway unreachable | `False` | `"AI Gateway unreachable"` |

### 4. `llm_base/routes.py` `auth_kind`

Extend the `/backends/status` payload. Add `auth_kind: "cli" | "browser"`
keyed off whether the plugin participates in browser OAuth. Concrete
rule: if the plugin has a `gateway_provider` attribute,
`auth_kind = "browser"`; otherwise `"cli"`. Existing `cli_command` /
`help_text` continue to apply for `"cli"` only.

### 5. Electron main: `oauth-launcher.ts` (new)

New IPC handler `backends:authenticateOAuth(name)`. Flow:

1. `POST http://127.0.0.1:<sf-port>/<name>/auth/start`
2. `shell.openExternal(authorize_url)`
3. Poll `GET .../auth/status` every 2s, max 10 minutes
4. Emit `oauth:complete` or `oauth:failed` to the renderer

Single-flight per backend name: a launcher already in flight for `name`
returns the existing promise. On `oauth:failed`, payload carries one of
`timeout | gateway_error | provider_error | network_error` plus the raw
message for the toast.

### 6. Electron renderer

`BackendStatusPanel.tsx`: when `health.auth_kind === "browser"` the
existing button label becomes "Authenticate" (or stays
"Re-authenticate" if `health.action === "reauth"`) and `onClick` calls
`authenticateOAuth(name)`. Disable + show "Waiting for browser..." while
the launcher is in flight; clear on `oauth:complete | oauth:failed`.

## Data flow — happy path

```
1. UI loads → GET /backends/status
2. SF aigw plugin's health() → gateway returns 404 (no profile) or PENDING
3. UI renders "Authenticate" (auth_kind=browser, action=reauth)
4. User clicks → IPC backends:authenticateOAuth("claude")
   (`name` here is the panel key derived from `path.lstrip("/")`,
   matching today's `authenticate(name)` pattern.)
5. Electron main → POST http://sf/claude/auth/start
   SF server  → POST http://gateway/v1/auth/anthropic/profiles
                body {name: "default"}
   gateway    → upsert PENDING profile, return authorize_url
6. Electron main → shell.openExternal(authorize_url)
7. User completes OAuth in browser
   browser → GET http://gateway/v1/auth/anthropic/callback?code=...&state=...
   gateway → exchange code, store token in OS credential store,
             mark profile AUTHENTICATED, return "you may close" HTML
8. Electron main poll loop sees state==AUTHENTICATED
   → emit 'oauth:complete'
9. UI re-runs /backends/status → green
```

## Error paths

| Failure | Detection | UX |
| --- | --- | --- |
| Gateway unreachable from SF | step 5: 502 / connect refused | Inline error: "AI Gateway not running. Start with `make aigw-dev`." |
| Provider OAuth refused (user denied) | callback never marks AUTHENTICATED; poll times out at 10min | Toast "Authentication timed out. Try again." |
| Network blip during poll | httpx exception | Retry up to 5x with linear backoff, then `oauth:failed network_error` |
| Browser tab closed without completing | same as timeout | Same as above |
| Gateway profile transitions to ERROR | poll observes `state=="ERROR"` | Short-circuit: `oauth:failed provider_error` with the gateway's error message |
| Token previously authenticated, now expired and refresh failed | gateway returns AUTHENTICATED until `/refresh` fails — separate path; not in scope here | Existing reauth-button cycle re-runs Authenticate |

## Testing

Integration coverage is the priority.

### Layer 1 — SF auth-proxy unit tests
File: `apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py`

Use httpx `MockTransport` for the gateway. Coverage:
- `POST /auth/start` happy path → 200, body shape passes through
- `POST /auth/start` gateway 502 → SF returns 502 with structured detail
- `POST /auth/start` gateway connection refused → SF returns 502
- `GET /auth/status` happy path → 200, body passes through
- `GET /auth/status` gateway 404 → SF returns 404
- Plugin without `gateway_provider` attribute → routes not mounted

### Layer 2 — gateway-backed integration tests (the bulk)
File: `apps/server/tests/e2e/test_aigw_auth_e2e.py`

Reuses the subprocess pattern from `tests/e2e/test_aigw_claude_e2e.py`.
Boot real aigateway with:
- a fake in-memory credential store
- a fake Anthropic OAuth server via httpx `MockTransport` injected at
  `app.state.anthropic_http_factory` (already supported,
  `apps/aigateway/src/aigateway/routes/auth.py:132`)

Scenarios:
1. **Happy path full cycle**
   - `POST sf://claude/auth/start` → assert authorize_url shape +
     gateway has PENDING profile
   - simulate browser callback with code+state
   - `GET sf://claude/auth/status` → AUTHENTICATED
   - `GET sf://claude/health` → `authenticated:true`
   - assert one chat round-trip works end-to-end (uses already-tested
     proxy chain)
2. **Idempotent re-start of authenticated profile**
   - run scenario 1
   - `POST sf://claude/auth/start` again
   - assert: new authorize_url returned, gateway still has token in
     credential store (re-auth doesn't blow it away until callback succeeds with
     a new code), profile state PENDING
3. **State mismatch on callback**
   - start cycle, pass `state=wrong` to gateway callback
   - expect 400 from gateway
   - SF status still PENDING
4. **Token-exchange fails at upstream**
   - fake OAuth server returns 400 on `/v1/oauth/token`
   - callback returns 4xx; profile transitions to ERROR
   - `GET sf://claude/auth/status` reflects ERROR
5. **Gateway down at start**
   - kill gateway subprocess
   - `POST sf://claude/auth/start` → SF returns 502 with hint
6. **Profile not yet created**
   - fresh boot, before any /auth/start
   - `GET sf://claude/auth/status` → 404
   - `GET sf://claude/health` → not authenticated, action=reauth,
     auth_kind=browser

### Layer 3 — Electron oauth-launcher tests
File: `apps/desktop/src/main/services/__tests__/oauth-launcher.test.ts`

Mock `shell.openExternal` and `fetch`. Coverage:
- happy path: start → openExternal → poll → complete event
- timeout (10min) → `oauth:failed timeout`
- gateway returns ERROR mid-poll → short-circuit `oauth:failed provider_error`
- network blip retry → succeeds after one retry
- single-flight: second call while first in flight returns same promise

### Layer 4 — renderer test
File: `apps/desktop/src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx`

react-testing-library. Coverage:
- `auth_kind=browser` renders Authenticate button
- click invokes `window.electronAPI.backends.authenticateOAuth(name)`,
  not the existing `authenticate(name)`
- "Waiting for browser..." appears while in flight
- `oauth:complete` event clears in-flight state
- `auth_kind=cli` still uses the existing path (regression guard)

Total expected: ~6 unit tests, ~6 integration scenarios, ~5 launcher
tests, ~5 renderer tests.

## Build sequence

1. `aigw_base/auth_proxy_router.py` + unit tests (Layer 1)
2. `AigwBackendApiPluginBase.gateway_provider` + auto-mount in
   `aigw_claude_backend`
3. `AigwBackend.health()` rewrite + unit tests
4. `/backends/status` `auth_kind` field + small unit test
5. Integration tests (Layer 2) — should pass once 1-4 land
6. Electron main `oauth-launcher.ts` + IPC channel + tests (Layer 3)
7. `BackendStatusPanel` browser-mode wiring + tests (Layer 4)
8. Manual smoke through the desktop app against a real Anthropic OAuth

## References

- AI Gateway OAuth routes: `apps/aigateway/src/aigateway/routes/auth.py`
- Existing reauth button: `apps/desktop/src/renderer/src/components/server/BackendStatusPanel.tsx:55`
- Existing CLI authenticate IPC handler: search `electronAPI.backends.authenticate`
- Subprocess integration test pattern: `apps/server/tests/e2e/test_aigw_claude_e2e.py`
- aigw plugin shape: `apps/server/src/screamingface/plugins/aigw_claude_backend/`
