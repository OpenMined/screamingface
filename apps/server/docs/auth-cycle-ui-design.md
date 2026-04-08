# Electron Auth-Cycle UI — Design

**Status:** Design draft. Not implemented. Targets Phase 5 (SF-85) of the multi-backend architecture roadmap.
**Related:** [`oauth-spike-findings.md`](./oauth-spike-findings.md), `~/.claude/plans/cozy-forging-gray.md`

## What this is for

The user has filed a multi-backend roadmap that replaces the `claude -p` subprocess with direct API calls authenticated by OAuth tokens **read from the credential stores of the CLI tools that already exist on the user's machine** (Claude Code on macOS Keychain, eventually Codex / Gemini-CLI / Qwen-CLI on their respective stores).

The desktop app needs UI for this — not for **acquiring** the tokens (the CLI tools already do that), but for **observing, refreshing, and recovering from** the OAuth lifecycle once tokens exist.

This is fundamentally different from the OpenAI-key-paste flow most LLM dev tools have. The user never types a credential into our app. Our job is to surface the state of credentials that live elsewhere and tell the user how to fix them when they break.

## States the UI must show per backend

For each registered backend (Claude, Codex, Gemini, Qwen, …) the UI tracks one of these states:

| State | Meaning | Visible signal | Action button |
|---|---|---|---|
| **Not configured** | The backend plugin isn't enabled in `sf.json` | Greyed out, "Add backend" link | Add to config |
| **No CLI installed** | The plugin is enabled but the corresponding CLI binary isn't on PATH | Red dot, "CLI not found: install the corresponding CLI" | Install instructions |
| **Not authenticated** | CLI is installed but no credential entry exists in the credential store | Red dot, "Run the CLI's auth login command" | Open terminal w/ command |
| **Authenticated, fresh** | Token present, expires > 5 min from now | Green dot, "✓ Connected · expires in 4h" | None (just info) |
| **Authenticated, expiring soon** | Token expires in < 5 min | Yellow dot, "Refreshing…" | Auto-refresh fires |
| **Refreshing** | A refresh call is in flight | Yellow dot with spinner | None |
| **Authenticated, refresh transient fail** | Refresh call returned a non-401 transient error (network, 5xx) | Yellow dot, "Refresh failed, retrying" | Retry now |
| **Refresh token dead** | Refresh call returned 401 / `invalid_grant` | Red dot, "Re-authentication required" | Open terminal w/ login command |
| **Rate-limited** | Last API call returned 429 (token is fine, tier maxed) | Yellow dot, "Rate limited until 19:42" | Wait timer |
| **API error** | Last call returned 5xx or other error | Red dot, last error text | Retry |

The state machine for a single backend looks like:

```
            ┌─── Not configured ──────────────┐
            │              │                  │
            │              v                  │
            │       No CLI installed          │
            │              │                  │
            │              v                  │
            │       Not authenticated         │
            │              │                  │
            │              v                  │
            │       ┌─────────────┐           │
            │       │             │           │
            │       v             │           │
            │  Authenticated      │           │
            │       │             │           │
            │       │ <5 min from │           │
            │       │  expiry     │           │
            │       v             │           │
            │  Refreshing         │           │
            │       │             │           │
            │       ├── ok ───────┘           │
            │       │                          │
            │       └── 401 ──> Refresh token  │
            │                   dead           │
            │                                  │
            └──────── (also: API error,        │
                     rate-limited as           │
                     overlay states)           │
```

## Where it lives in the desktop app

The existing app already has four views:

- `DashboardView.tsx` — top-level overview
- `PluginView.tsx` — plugin management
- `SessionsView.tsx` — session creation/management (already lists `claude / codex / gemini` session types)
- `SettingsView.tsx` — server config

**New view:** `BackendsView.tsx` — sibling to the others, accessible from the sidebar. One row per registered backend.

**Sidebar entry:** add `Backends` to the existing `Sidebar.tsx` nav, between `Sessions` and `Settings`.

**Why a separate view, not stuffed into Settings:** auth state is dynamic and frequently checked. Settings is for static config. Conflating them buries the most-used info under the least-changed config.

### `BackendsView.tsx` layout

```
┌──────────────────────────────────────────────────────────────────┐
│  Backends                                                        │
│  ════════                                                        │
│                                                                  │
│  ● Claude Code        sk-ant…sk23 · Max tier · expires in 7h    │
│    Connected via OAuth                          [Refresh]  [↻]  │
│  ────────────────────────────────────────────────────────────── │
│  ○ Codex (GPT-5)      not authenticated                          │
│    Run codex auth login to enable                    [Open ▶]   │
│  ────────────────────────────────────────────────────────────── │
│  ⚠ Gemini CLI         token expires in 3 min · refreshing…      │
│                                                                  │
│  ────────────────────────────────────────────────────────────── │
│  ✗ Qwen Code          refresh token expired                      │
│    Re-authenticate to continue          [Re-authenticate]       │
│  ────────────────────────────────────────────────────────────── │
│                                                                  │
│  + Add backend                                                   │
└──────────────────────────────────────────────────────────────────┘
```

Each row has:

- **Status indicator** (●/○/⚠/✗ + color)
- **Backend name** + provider chip
- **Token preview** (first 8 chars of access token, last 4 of refresh token, redacted middle) — gives the user a fingerprint to verify against the CLI's `auth status` output
- **Tier / subscription type** (e.g. "Max tier", "Pro tier")
- **Expiry countdown** (live, updates every second when expiry < 1 hour)
- **Account email or org name** (from the refresh response — we have this from spike step 4)
- **Last error**, if any, with full details on click
- **Action button** appropriate to the state

### `Refresh` button

Force-refreshes the token regardless of expiry. Useful for debugging and for the "I just ran the CLI auth login again, please re-read the credential store" case. The flow:

1. UI POSTs to a new SF endpoint `POST /backends/<name>/refresh`
2. Backend invalidates its in-memory cache
3. Backend re-reads the credential store
4. If the token is still expired, backend calls the OAuth refresh endpoint
5. Backend writes the new token back to the credential store
6. Endpoint returns the new state, UI updates the row

### `Re-authenticate` button

Opens the user's terminal with the appropriate command pre-typed. Implementation uses **`execFile` (or the project's `execFileNoThrow` helper), never `exec`** — every argument goes through an array, never a shell-interpolated string. Pseudocode for the macOS path:

```ts
import { execFile } from 'node:child_process';
// or: import { execFileNoThrow } from '../utils/execFileNoThrow.js';

// Compose the AppleScript as a fixed string with NO interpolation of
// untrusted input. The CLI command name is hardcoded per backend, never
// taken from user input.
const scripts: Record<BackendName, string> = {
  claude: 'tell application "Terminal" to do script "claude auth login"',
  codex:  'tell application "Terminal" to do script "codex auth login"',
  gemini: 'tell application "Terminal" to do script "gemini auth login"',
  qwen:   'tell application "Terminal" to do script "qwen auth login"',
};

execFile('osascript', ['-e', scripts[backendName]]);
```

The hardcoded command map per backend is the security boundary: the only thing that varies between rows is which fixed string we hand to `osascript`, not anything the user types.

We **never** try to embed an OAuth web flow inside Electron. Reasons:

- The OAuth flows for these CLIs are designed around browser redirects to localhost callbacks that the CLI tool itself owns. Recreating that machinery inside Electron is fragile.
- Each CLI has its own OAuth client_id, callback port, and PKCE handshake. Implementing four of these is four bug surfaces we don't need.
- The CLI is the source of truth for credential storage. Keeping it that way means our app benefits when the user is updating, debugging, or reconfiguring their CLI separately.

The button just **delegates to the CLI** by opening a terminal with the right command. The user runs the flow there. When it completes, the credential lands in the store, and SF picks it up next time it reads.

### `Auto-detect` after re-auth

When the user clicks `Re-authenticate` we open the terminal and **start polling**. Every 2 seconds for the next 5 minutes, the UI re-checks the credential store. As soon as a new valid token appears (different `accessToken` than the cached one, or token where there was none before), the UI flips the row to "Authenticated, fresh" and stops polling.

This is the "you came back to the app and it just works" flow. No "click here to refresh after you've logged in" friction.

## Backend-side support needed

The Electron view talks to a new SF backend route surface. Spec for Phase 5:

```
GET  /backends                          → list of {name, plugin, status, token_preview, expires_at, tier, account, last_error}
GET  /backends/<name>                   → single backend status (same shape)
POST /backends/<name>/refresh           → force a refresh, return updated status
POST /backends/<name>/test              → fire a one-shot ping (a tiny Messages call) to verify everything works end-to-end
```

These routes live in the `llm-base` plugin (since it's the cross-backend infrastructure layer) and are read-only views over the in-memory `Backend` registry. They never return raw tokens — only previews and metadata.

The `llm-base` plugin gains a tiny in-process state machine per registered backend that tracks the state-table values above. The state transitions fire on:

- Plugin activation (initial read)
- Every API call attempt (success / failure / 429 / 401)
- Background timer (every 60s) that checks `expiresAt` and triggers proactive refresh
- Manual `POST /backends/<name>/refresh`

## Token-source view

When the user clicks a backend row, an expanded panel shows:

```
┌────────────────────────────────────────────────────────────────┐
│  Claude Code                                          [Close]  │
│  ─────────────                                                 │
│                                                                │
│  Status:           Connected                                   │
│  Provider:         Anthropic                                   │
│  Model default:    claude-sonnet-4-6                           │
│  Account:          sergey@openmined.org                        │
│  Organization:     OpenMined                                   │
│  Subscription:     Max tier (5x)                               │
│                                                                │
│  Credential source                                             │
│  ──────────────                                                │
│  Store:            macOS Keychain                              │
│  Service name:     Claude Code-credentials                     │
│  Account:          sergey                                      │
│  Last refreshed:   3 minutes ago                               │
│  Expires:          2026-04-08 02:13 UTC (in 7h 28m)            │
│                                                                │
│  Scopes                                                        │
│  ──────                                                        │
│    ✓ user:inference                                            │
│    ✓ user:file_upload                                          │
│    ✓ user:mcp_servers                                          │
│    ✓ user:profile                                              │
│    ✓ user:sessions:claude_code                                 │
│                                                                │
│  Token fingerprint                                             │
│  ─────────────────                                             │
│    accessToken:    sk-ant-oat01…ab3f  (108 chars)              │
│    refreshToken:   sk-ant-ort01…7e92  (108 chars)              │
│                                                                │
│  Recent activity                                               │
│  ───────────────                                               │
│    16:24:19  POST /v1/messages         429 (rate limited)      │
│    16:24:18  POST /oauth/token         200 (refresh)           │
│    11:13:02  POST /v1/messages         200                     │
│    11:08:55  Server start, token loaded from Keychain          │
│                                                                │
│  [ Test connection ]   [ Refresh now ]   [ Re-authenticate ]   │
└────────────────────────────────────────────────────────────────┘
```

The "Recent activity" log is the key debugging tool. It shows what auth-related events have happened so the user can see at a glance whether the system is healthy. Pulled from the OTEL spans the backend already emits.

## Multi-account / multi-provider considerations

When we add Codex / Gemini / Qwen in Phase 3, each one gets its own row. The same UI handles them with no structural change because the underlying `Backend` ABC and state machine are provider-agnostic.

Some providers may have **multiple accounts** authenticated on the same machine (e.g. Codex with two ChatGPT accounts, or Claude Code with personal + work). The first cut shows only the "default" / first-found credential per provider. A future iteration could let the user pick which account a session uses.

## Error and edge case handling

### Keychain locked
On macOS, the Keychain can be locked when the screen is locked. The `security` command will prompt for the user's login password to unlock it. If we hit this case from a background daemon process, the prompt won't reach the user. The UI should:
1. Detect the locked state (subprocess hangs or returns specific error)
2. Show "Keychain locked — unlock with your login password"
3. Provide a button that runs `security unlock-keychain` interactively (which prompts via the system-level dialog, not stuck in our background process)

### Concurrent refresh races
The `llm-base` plugin holds an asyncio lock per backend so only one refresh can be in flight at a time. The UI can show "Refreshing…" and other refresh requests queue up.

### Token rotated by another tool
If the user runs `claude auth login` directly while our app is running, the keychain gets a new token but our in-memory cache is stale. Two safety nets:
1. The next API call will use the cached (now stale) token, get a 401, and our retry path will re-read the keychain.
2. The background timer that fires every 60s also re-reads the keychain on each tick, so the staleness window is bounded.

### Network unavailable
The refresh call will fail. UI shows "Offline · refresh deferred" and retries when network is back. API calls themselves fail with the same network error.

### CLI logout ran externally
The credential store entry disappears. Our background timer notices on the next tick, the row flips to "Not authenticated", the user clicks `Re-authenticate`.

## Phase 5 ticket breakdown

This design fans out into four sub-tickets:

1. **SF-85a — Backend status routes in `llm-base`** — `GET /backends`, `GET /backends/<name>`, `POST /backends/<name>/refresh`, `POST /backends/<name>/test`. Plus the in-process state machine. Pure server-side.

2. **SF-85b — `BackendsView.tsx`** — the React view itself, the row layout, the live countdown timers, the polling logic. Talks to the new routes via the existing `useSessions`-style hook pattern.

3. **SF-85c — Expanded detail panel** — the per-backend deep-dive UI with credential source, scopes, recent activity log.

4. **SF-85d — Re-authentication terminal flow** — `execFile('osascript', …)` invocation on macOS with hardcoded per-backend command map, the post-login polling logic, the toast notification on success. **Security note:** all subprocess invocations in this flow MUST use `execFile` (or the project's `execFileNoThrow` helper), never `exec`. The backend-name → CLI-command mapping is a static lookup table; user input never enters the subprocess args.

Each ticket is small enough to land in a single PR. The dependency chain is `85a → 85b → 85c, 85d` (the view needs the routes, the panel and re-auth flow need the view).

## Out of scope for Phase 5

- Embedded OAuth flows (we always delegate to the CLI)
- Multi-account picker (one account per provider in v1)
- Token rotation history / audit log beyond "recent activity"
- Org switcher (use the org the CLI is logged into)
- Cost tracking display (separate Phase 6 work)
- Pre-flight rate-limit display (hard to predict accurately without a probe)
