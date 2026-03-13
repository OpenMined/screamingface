# Config Refs vs Inline DSL

## Problem

We need proxy configuration (model, system prompt, temperature, etc.) encoded in a URL for use as `ANTHROPIC_API_BASE`. Two approaches: **inline DSL** (config in the URL path) or **config refs** (URL points to external JSON).

---

## Inline DSL: Why It Breaks Down

URL path segments only allow `A-Z a-z 0-9 - _ . ~ , :` — no spaces, quotes, braces, or slashes. Every real config character must be escaped.

**Simple case** — tolerable:
```
https://proxy.local/_c.m:claude-sonnet-4-20250514,mt:4096,t:0.7/v1/messages
```

**With a system prompt** — painful:
```
https://proxy.local/_c.m:claude-sonnet-4-20250514,mt:8192,t:0.3,sp:You-_are-_a-_code-_review-_assistant.-_Follow-_these-_rules--c--n1.-_Flag-_security-_issues-_first--n2.-_Check-_for-_SQL-_injection--m-_XSS--m-_and-_SSRF--n3.-_Suggest-_fixes--m-_not-_just-_problems--n4.-_Use-_the-_format--c-_--s--s-_severity--c-_HIGH--s-_MEDIUM--s-_LOW--n--n-_Output-_JSON-_with-_keys--c-_issues--m-_summary--m-_score/v1/messages
```

347 characters of gibberish. The original prompt was 6 readable lines. A production config with API keys and style guides hits **569 characters**.

| Need | URL path provides |
|---|---|
| Readability | Escape sequences |
| Structured data | Flat key-value only |
| Multiline | `--n` escapes |
| Special chars | 6+ escape codes |
| Nesting/comments | Not possible |
| Length | 2,000-8,192 char limit |

A config format worse than every existing one, invented to fit through a keyhole.

---

## Config Refs

Reference a config that lives elsewhere:

```
https://proxy.local/ref:pastebin.com/dEfXcvs@sha256:a1b2c3.../v1/messages
```

On every request, the server fetches the URL, computes the SHA-256 of the response body, and compares it to the hash in the ref. **If the hash doesn't match, the request is rejected.** This validation happens on every fetch, not just the first — even cached content is re-verified against the hash before use.

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 8192,
  "temperature": 0.3,
  "system_prompt": "You are a code review assistant. Follow these rules:\n1. Flag security issues first\n2. Check for SQL injection, XSS, and SSRF\n3. Suggest fixes, not just problems\n4. Use the format: // severity: HIGH/MEDIUM/LOW\n\nOutput JSON with keys: issues, summary, score"
}
```

Readable, editable, validatable with standard tooling (`jq`, JSON Schema, linters). Composable (configs can reference other configs).

### Hash-Pinned Refs

The ref format is `ref:<url>@sha256:<hash>`. The hash is **mandatory**, not optional. This makes refs content-addressable: the URL is just a fetch location, the hash is the identity.

```
ref:gist.githubusercontent.com/user/abc123/raw@sha256:9f86d0...
ref:configs.mycompany.com/team-alpha.json@sha256:e3b0c4...
```

This guarantees:
- **Immutability** — if the host changes the content, the hash breaks and the ref is rejected
- **Tamper detection** — MITM or CDN corruption is caught automatically
- **Reproducibility** — same ref always produces the same config, across machines and time
- **Safe caching** — content-addressable data can be cached forever (the hash IS the cache key)

To update a config, you publish new content and produce a **new ref with a new hash**. The old ref still resolves to the old content. This is the same model as Docker image digests, Git commit SHAs, and Nix store paths.

### Hosting Options

The hash requirement means any host works — even untrusted ones — because the content is verified client-side. The host is just a dumb pipe.

| Host | Example | Notes |
|---|---|---|
| GitHub Gist | `gist.githubusercontent.com/user/id/raw` | Free, versioned; long URL but hash ensures correct content regardless of gist edits |
| Pastebin | `pastebin.com/raw/XXXX` | Short; can be deleted (availability risk, not integrity risk) |
| Self-hosted | `configs.mycompany.com/team.json` | Full control |
| SF server | `proxy.local/configs/team-alpha` | Zero latency, no external dep |
| Any CDN/S3 | `cdn.example.com/configs/abc.json` | Cheap, fast; hash protects against CDN bugs |

Notably absent: **URL shorteners (bit.ly, etc.) are unnecessary.** The ref URL doesn't need to be short for humans — it's a machine-readable locator. The hash already makes it opaque, so shortening adds a redirect hop with no benefit.

### Concerns and Mitigations

| Concern | Mitigation |
|---|---|
| **Latency** | Cache by hash (content-addressable = cache forever). First fetch is slow, everything after is instant. |
| **Availability** | Cache survives host outages. Multiple mirrors possible since content is verified by hash. Fail-closed if uncached and host is down. |
| **SSRF** | Allowlist ref domains. Block private IPs by default. |
| **Secret leakage** | Configs hold only non-secret params. API keys stay in server env vars. |
| **Circular refs** | Max depth = 1. Refs cannot contain refs. |

### Hybrid

For trivial configs, inline is fine. Rule of thumb: if it fits in one glance, inline it. Otherwise, ref it.

```
https://proxy.local/_c.m:claude-sonnet-4-20250514/v1/messages                          # inline
https://proxy.local/ref:pastebin.com/dEfXcvs@sha256:a1b2c3.../v1/messages              # ref
```

---

## Approach 3: Local Config via Electron App

The SF server runs locally — the Electron app starts it on `localhost:8000`. The user configures model, system prompt, temperature, and everything else through the app's **Settings screen**. Claude Code simply points `ANTHROPIC_API_BASE` to `localhost:8000`.

```
ANTHROPIC_API_BASE=http://localhost:8000/v1
```

That's it. No ref, no hash, no inline DSL. Requests hit the proxy → `url4_executor` dispatches to the appropriate backend (`claude-backend` or `claude-frontend`) with the locally-stored config.

### Why this sidesteps the entire problem

| Concern | Status |
|---|---|
| **Config encoding** | Not needed — config lives in the app's local storage, never touches the URL |
| **Hash verification** | Not needed — the user configured it themselves, on their own machine |
| **Trust store** | Not needed — there's no external source to trust or distrust |
| **Opacity / social engineering** | Not applicable — the Settings UI IS the config preview. The user sees exactly what they configured |
| **First-use trust** | Not applicable — the user authored the config |

### How it works

1. User opens the Electron app → Settings screen
2. Configures model, system prompt, temperature, max tokens, etc. through the UI
3. App persists config locally (e.g., `sf.json` or app database)
4. SF server reads config on startup / watches for changes
5. Claude Code sends requests to `localhost:8000` — the proxy applies the config transparently
6. The Settings screen doubles as the config viewer — what you see is what executes

### When to use refs instead

Local app config is the default for single-user, single-machine use. Refs remain the right tool for:

- **Sharing configs across a team** — everyone uses the same model/prompt setup
- **CI/CD pipelines** — no Electron app, no human to click Settings
- **Remote/headless servers** — no local UI available
- **Config-as-code** — versioned, auditable, reviewable in PRs

---

## Recommendation

**Three tiers, from simplest to most portable:**

1. **Local app config** — the default for local users. Zero trust problem, best UX. The Electron app IS the config UI; the proxy already has everything it needs.
2. **Hash-pinned refs** — for sharing configs across machines, teams, and CI. Cryptographic integrity guarantees, trust-on-first-use model, works with any host.
3. **Inline DSL** — trivial 1-2 param overrides only (model, temperature). If you need more than `key:simple_value`, use option 1 or 2.

---

## Risk Assessment

> **Scope note:** This risk assessment applies to **external config refs** (Approach 2). Local app config (Approach 3) sidesteps the entire risk model — there's no external source, no opacity, no social engineering vector, and no first-use trust problem. The config never leaves the user's machine.

### What the hash eliminates

With mandatory hash-pinning, several threats from naive ref designs disappear:

| Threat | Status | Why |
|---|---|---|
| Config changes over time (mutable refs) | **Eliminated** | Hash mismatch = rejection. To change config, you must produce a new ref with a new hash. |
| Host-side tampering | **Eliminated** | Content is verified against the hash. A compromised host can only deny service, not alter config. |
| MITM / CDN corruption | **Eliminated** | Same reason — hash verification catches any bit flip. |
| URL shortener misdirection | **Not applicable** | Shorteners are unnecessary in this design. |

### What the hash does NOT eliminate

The hash guarantees that content hasn't changed — but it says nothing about whether the content was safe to begin with.

**First-use trust is the remaining attack surface.** Someone shares a ref in a tutorial or Slack:

```
Use this as your ANTHROPIC_API_BASE:
https://proxy.local/ref:pastebin.com/dEfXcvs@sha256:9f86d0.../v1/messages
```

The hash guarantees this ref will always resolve to the same config. But the config itself could:

- **Inject a system prompt** that exfiltrates data or overrides safety instructions
- **Burn credits** via `max_tokens: 100000` or forcing an expensive model
- **Override safety-critical settings** the user would never choose

This is a social engineering problem, not a cryptographic one. The ref is safe from tampering — but was it safe to trust in the first place?

### Mitigation: Ref Trust Store

The server maintains a **trust store** — a set of SHA-256 hashes the user has explicitly approved. An unapproved ref is never executed. This is the same model as SSH `known_hosts`: trust on first use, then the fingerprint does the rest.

**The rule is simple: no hash in the trust store = no execution.**

#### How it works

1. Request arrives with a ref containing a hash
2. Server checks: is this hash in the user's trust store?
   - **Yes** → fetch config, verify hash, execute
   - **No** → fetch config, verify hash, return a **preview response** instead of executing. The request is blocked.
3. User reviews the resolved config in the preview, approves or rejects
4. If approved, hash is added to the trust store. All future requests with this hash execute immediately.

#### User Stories

**Story 1: Developer tries a ref from a teammate**

> Alex gets a Slack message: "Use this for our team config: `ref:gist.github.com/...@sha256:9f86d0...`"
>
> Alex sets it as `ANTHROPIC_API_BASE` and makes an API call. Instead of a model response, they get back:
>
> ```
> 402 Config Approval Required
>
> This ref has not been approved yet. Resolved config:
>   model:       claude-sonnet-4-20250514
>   max_tokens:  8192
>   temperature: 0.3
>   system:      "You are a code review assistant. Follow these rules:..."
>
> Approve at: https://proxy.local/refs/approve/sha256:9f86d0...
> ```
>
> Alex clicks the link, sees the full config, clicks "Approve". Every subsequent request works instantly.

**Story 2: Config update — admin publishes a new version**

> The team admin updates the system prompt and publishes a new config. The new ref has a different hash: `sha256:e3b0c4...`
>
> Alex updates their env var with the new ref. Next API call gets blocked again with a preview of the new config. Alex approves. The old hash stays in the trust store (still valid if anyone uses it), the new hash is added.

**Story 3: Malicious ref in a blog post**

> Alex finds a blog post: "Speed up your Claude workflow with this config!" with a ref.
>
> They try it. The preview shows `max_tokens: 100000` and a system prompt that starts with "Ignore all previous instructions...". Alex rejects it. The hash is not added to the trust store. Nothing was executed.

**Story 4: CI/CD — non-interactive approval**

> A CI pipeline uses refs. There's no human to click "approve" at runtime.
>
> The admin pre-approves hashes via CLI or API: `sf refs approve sha256:9f86d0...`. The trust store is populated before the pipeline runs. If a ref with an unknown hash appears in CI, it fails fast with a clear error rather than hanging for approval.

#### Preview response format

When a ref is unapproved, the server returns a structured response (not an error page — a proper API response that tooling can parse):

```json
{
  "status": "approval_required",
  "ref": "gist.github.com/user/abc123/raw",
  "hash": "sha256:9f86d0...",
  "resolved_config": {
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 8192,
    "temperature": 0.3,
    "system": "You are a code review assistant..."
  },
  "anomalies": ["max_tokens > 4096"],
  "approve_url": "https://proxy.local/refs/approve/sha256:9f86d0..."
}
```

HTTP status: **402** (payment/action required — semantically close enough, and distinct from auth errors).

#### Trust store properties

- **Per-user** — each user maintains their own approved hashes. Admin approval doesn't auto-propagate (unless org policy says otherwise).
- **Hash-only** — the store contains hashes, not URLs. If two different URLs serve the same content (same hash), approving one approves both.
- **Append-only in normal use** — approvals accumulate. Revocation is possible (`sf refs revoke sha256:...`) but rare.
- **Portable** — the trust store is a simple list of hashes. Can be checked into a repo, shared across a team, or seeded in a Docker image.

### Inline vs Ref: Irrelevant Once Resolved

Whether a value is inline or from a ref, the **resolved value** is what matters. The UI treats all sources identically — resolve everything, show the result. The user needs to see what will actually execute.
