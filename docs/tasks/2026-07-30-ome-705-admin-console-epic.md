---
id: OME-705
linear_url: https://linear.app/openmined/issue/OME-705/admin-console-for-gateway-accounts-and-api-key-credentials
status: backlog
type: epic
priority: P1
labels: [aigateway, autonomous, agentic]
created: 2026-07-30
closed:
---

# OME-705 — Admin console for gateway accounts and API-key credentials (epic)

Closes the credential-provisioning gap `OME-684` leaves open, with an operator-managed admin
console: a hardcoded allowlist of admin emails manages accounts and attaches **static provider
API keys** to them, so a caller's first request finds a profile instead of a `404`.

**No OAuth anywhere in this work.** The existing OAuth profile/connection endpoints are untouched
and simply not surfaced in the console.

## Why now

`OME-684` (PR #444) made Cloudflare Access the identity source — the edge authenticates with OTP,
Envoy re-verifies the assertion against Cloudflare's JWKS, strips any client-supplied copy, and
injects `X-User-Email`. That issue names this gap in its own out-of-scope list: *"Nothing
provisions credentials for a header-derived principal — a new caller authenticates and then gets
`404 profile_not_found`. Per-user OAuth vs operator-managed org keys is a separate decision."*
This epic is the operator-managed answer.

## Locked decisions

| Decision | Value |
|---|---|
| Admin identity | `X-User-Email`, gated on a new `AIGATEWAY_ADMIN_EMAILS` allowlist |
| Allowlist authority | aigateway only — the UI holds no copy |
| Admin ≠ Account | Admins are header identities in an env var, never a DB row |
| Tenant | The existing `Account` row — no new table, no new scoping axis |
| Profile | The existing blob `Profile`, `auth_type="api_key"` only |
| Call path | BFF: browser → Next.js server → aigateway |
| Trust gate | Network trust, reusing `peer_in_networks` (TCP peer, never `X-Forwarded-For`) |
| Shipping | Own app, own image, own chart, own CI lane. Port 9107 |

## Sub-issues

| Issue | Landing | Blocked by |
|---|---|---|
| `OME-706` — `/v1/admin` API | `aigateway` | `OME-684` |
| `OME-707` — repo registration | `repo` | — |
| `OME-708` — Next.js console | `aigateway-ui` (label pending) | `OME-706`, `OME-707` |

## Acceptance

A caller whose email has no credentials gets `404 profile_not_found` on `/v1/chat/completions`.
After an admin attaches a provider key through the console, the same request reaches the provider.

## Owner actions

1. Create the `aigateway-ui` landing label (parent `app`) in the Linear UI, apply it to `OME-708`,
   and register its UUID in `.claude/task-board.local.md` in the same change.
2. Merge PR #444 before `OME-706` starts.
3. Confirm the admin email list that seeds `AIGATEWAY_ADMIN_EMAILS`.
