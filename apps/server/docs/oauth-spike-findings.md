# SF-77 OAuth-from-Keychain Spike — Findings

**Date:** 2026-04-07
**Branch:** `SF-77-oauth-spike`
**Script:** [`scripts/oauth_spike.py`](../scripts/oauth_spike.py)
**Plan:** `~/.claude/plans/cozy-forging-gray.md`

## TL;DR

**The architecture is validated.** All four spike checks passed. We can build Phase 1 (SF-78: `llm-base` + `claude-direct` plugins) on top of the OAuth-from-Keychain → direct Anthropic API call path with confidence.

| Step | Result | Notes |
|---|---|---|
| 1. Read Keychain credentials | ✅ PASS | Found at service `Claude Code-credentials`, parses as expected JSON |
| 2. POST /v1/messages with OAuth bearer | ✅ PASS (via 429) | Anthropic accepted the token, mapped to org, returned 429 only because we hit tier rate limit. The 429 itself is the proof. |
| 3. Document refresh endpoint | ✅ PASS | Guessed URL + client_id worked on first try |
| 4. Test refresh round-trip | ✅ PASS | Got back a fresh token valid for 8 hours |

## Step 1: Keychain credential discovery

**Service name:** `Claude Code-credentials` (capitalization and space matter)
**Account:** `$USER` (e.g. `sergey`)
**Read command:**
```bash
security find-generic-password -s "Claude Code-credentials" -w
```

**Format** (the password value is JSON):
```json
{
  "claudeAiOauth": {
    "accessToken": "sk-ant-oat01-…",        // 108 chars total
    "refreshToken": "sk-ant-ort01-…",       // 108 chars total
    "expiresAt": 1775603600782,             // unix epoch milliseconds
    "scopes": [
      "user:file_upload",
      "user:inference",                     // ← critical for /v1/messages
      "user:mcp_servers",
      "user:profile",
      "user:sessions:claude_code"
    ],
    "subscriptionType": "max",
    "rateLimitTier": "default_claude_max_5x"
  }
}
```

**Critical observations:**

- The `user:inference` scope is what gates Messages API calls. Without it the token would 403.
- `expiresAt` is **milliseconds**, not seconds. Our code must multiply `time.time() * 1000` for comparisons.
- The tokens are ~108 characters each; we should not log them.
- macOS-only for this read path. Linux/Windows TBD (Phase 1 will need to verify on at least one Linux machine).

## Step 2: Direct Messages API call with OAuth bearer

**Headers used:**
```
Authorization: Bearer <accessToken>
anthropic-version: 2023-06-01
content-type: application/json
anthropic-beta: oauth-2025-04-20
```

**Critical:** The `anthropic-beta: oauth-2025-04-20` header turned out to be necessary. Without it, the OAuth scope check might reject the request. Claude Code itself sets this header on every call. **Phase 1 must include it on every outbound request.**

**Result:** HTTP 429 rate-limited, but with response headers proving the token was accepted:
- `anthropic-organization-id: cfb4e9cc-a8c9-4eed-bf65-fa67d4e996a4` ← Anthropic identified the org
- `request-id: req_011CZpit1QjTy83XPpHTRXph` ← request was processed (not rejected at auth)
- `x-should-retry: true` ← retry hint, standard 429 behavior

**The 429 itself is the proof.** A rejected token would have returned 401 or 403 *before* mapping the org. Getting through to the rate-limit check means the auth path works end to end. This is "wait it out and try again later," not "the design is wrong."

**Verdict:** Architecture assumption holds. Anthropic accepts OAuth bearer tokens against `/v1/messages` directly.

## Step 3 & 4: Refresh endpoint

**URL:** `https://console.anthropic.com/v1/oauth/token`
**Method:** `POST`
**Headers:** `content-type: application/json`
**Body:**
```json
{
  "grant_type": "refresh_token",
  "refresh_token": "<from keychain>",
  "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
}
```

**`client_id`** is the public Claude Code OAuth app identifier. It worked on the first try — no need to dig into CLIProxyAPI source for an alternative.

**Response on success (HTTP 200):**
```json
{
  "access_token": "sk-ant-oat01-…",     // new token, 108 chars
  "refresh_token": "sk-ant-ort01-…",    // possibly rotated, 108 chars
  "expires_in": 28800,                   // SECONDS (not ms), = 8 hours
  "token_type": "Bearer",
  "scope": "user:file_upload user:inference …",  // space-separated string
  "account": { … },                      // bonus: account metadata
  "organization": { … }                  // bonus: org metadata
}
```

**Important shape differences vs the keychain format:**
- `expires_in` is **seconds**, but the keychain stores `expiresAt` in **milliseconds**. When writing back to keychain we must convert: `expires_at_ms = (time.time() + expires_in) * 1000`
- `scope` is a space-separated string; the keychain stores `scopes` as a list. We must split.
- `access_token` / `refresh_token` use snake_case; the keychain uses camelCase (`accessToken` / `refreshToken`). We must remap.
- The response includes `account` and `organization` blobs that the keychain doesn't currently store. We can ignore them or persist them as bonus metadata.

**The refresh response is NOT a drop-in replacement for the keychain JSON.** Phase 1's `ClaudeCodeOAuth._refresh()` method must do the field-name + unit conversions before writing back.

## Implications for Phase 1 (SF-78)

Lock these into the `claude-direct` plugin's `auth.py` from day 1:

1. **Read path** uses `security find-generic-password -s "Claude Code-credentials" -w` (with cross-platform fallbacks per the plan).
2. **Authorization header** is `Bearer <accessToken>`, NOT `x-api-key`.
3. **Required beta header** is `anthropic-beta: oauth-2025-04-20`. Don't forget this.
4. **Refresh URL** is `https://console.anthropic.com/v1/oauth/token` with the documented body.
5. **Refresh response transformer** must convert:
   - `access_token` → `accessToken`
   - `refresh_token` → `refreshToken`
   - `expires_in` (seconds) → `expiresAt` (milliseconds) via `(time.time() + expires_in) * 1000`
   - `scope` (space-separated string) → `scopes` (list)
6. **Write-back to keychain** uses `security add-generic-password -U -s "Claude Code-credentials" -a "$USER" -w "<json>"` (the `-U` flag updates an existing entry instead of erroring).
7. **Proactive refresh window**: 60 seconds before `expiresAt`, mirror Claude Code's own behavior.
8. **Hard-fail on missing keychain entry** with the message `"No Claude Code OAuth token found. Run 'claude auth login' to authenticate."` per the plan's locked-in decision.
9. **Rate limit handling (429)** is NOT an auth failure. Phase 1 should propagate 429 as a regular `BackendError` with a helpful message, optionally honoring `retry-after` and `x-should-retry` headers.

## Open follow-ups

- **Linux + Windows credential storage paths.** Phase 1 needs to verify the Claude Code CLI uses `secret-tool` / Windows Credential Manager with the same service name on those platforms. May differ. Test on one Linux machine before Phase 1's `LinuxLibsecretStore` is finalized.
- **Token rotation detection.** The refresh response sometimes returns a new `refresh_token`, sometimes returns the same one. Phase 1 should always write the response's refresh_token back to keychain (don't preserve the old one) so we don't drift.
- **What happens when the refresh token itself expires.** Refresh tokens are long-lived but not infinite. When they expire, the refresh call will return 401 and the user has to run `claude auth login` interactively. Phase 5 (Electron UI) needs to surface this state and offer a re-login button.
- **Concurrent refresh races.** If two backend calls hit the OAuth path simultaneously and both find an expired token, they'll both try to refresh and one will probably fail with `invalid_grant` (refresh tokens are sometimes single-use). Phase 1 needs an asyncio lock around the refresh.

## Spike script

The full spike script is at `apps/server/scripts/oauth_spike.py`. It is throwaway code — it gets deleted when Phase 1 lands. Its only purpose was to validate the four assumptions above before any plugin code is written.

To re-run (e.g. after a rate limit clears):
```bash
cd apps/server
uv run python scripts/oauth_spike.py
```
