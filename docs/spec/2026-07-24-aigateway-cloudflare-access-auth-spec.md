# Spec — AIGateway federated authentication via Cloudflare Access

> Epic: [OME-588](https://linear.app/openmined/issue/OME-588). Units: OME-589 … OME-593.

## Problem

AIGateway's only authentication path is a local password login. `current_account()`
(`core/auth/middleware.py:28-52`) accepts exactly one credential shape — an HS256
`Authorization: Bearer` token minted by `POST /v1/auth/login`
(`routes/auth_session.py:22-52`) — and accounts exist only because an operator called
`POST /v1/accounts` with the static `X-Aigw-Provisioning-Token`
(`routes/accounts.py:76-94`). The single "everyone gets in" escape hatch is
`auth_enabled=False`, which collapses every caller onto `anonymous_account()` and destroys
per-account attribution.

We want to deploy AIGateway behind **Cloudflare Access**, which already enforces an admission
policy (OTP/PIN, or a corporate IdP) and only forwards requests from users that policy
admits. Those users must reach the gateway **without registering and without calling
`/v1/auth/login`** — the account should materialise from the identity Cloudflare asserts.
Some callers are humans in a browser, some are humans at a CLI, and some are programmatic SDK
clients that cannot complete an interactive flow.

## Goals

- A user admitted by Cloudflare Access reaches every authenticated route with **zero
  registration steps**, and gets an `Account` row created just-in-time on first request.
- Programmatic SDK clients authenticate **non-interactively** and remain individually
  attributable — not collapsed onto one shared machine identity.
- The existing local-login path keeps working byte-for-byte, so local dev and
  non-Cloudflare deployments are unaffected.
- No fail-open path. Every misconfiguration that could admit an unauthenticated caller is
  rejected at startup, not at request time.

## Non-goals

- Replacing or deprecating `/v1/auth/login`. Both paths coexist.
- Supporting identity providers other than Cloudflare Access in this epic. The resolver port
  makes a second federated provider additive, but none is built here.
- Cloudflare Access for SaaS / OIDC app types. This spec covers **self-hosted** Access
  applications only.

## How Cloudflare Access delivers identity

Two separable things happen, and conflating them is the classic implementation error.

**1. Edge admission.** Access evaluates the policy and decides whether the request reaches the
origin at all. It accepts, by client type:

| Client | Credential presented to the edge |
|---|---|
| Browser | `CF_Authorization` cookie (set by the login redirect) |
| Human CLI | `cf-access-token: <jwt>` (from `cloudflared access token -app=<url>`) |
| Machine | `CF-Access-Client-Id` + `CF-Access-Client-Secret` |

Service tokens require the Access policy action to be **Service Auth**; with any other action
Access redirects to an IdP login instead of honouring the token pair.

**2. Identity assertion to the origin.** On success Access injects
`Cf-Access-Jwt-Assertion: <jwt>` — RS256, JWKS at
`https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`,
`iss = https://<team>.cloudflareaccess.com`, `aud` = the per-application AUD tag. Cloudflare
rotates the signing key every 6 weeks and serves the current **and** previous key with a
7-day grace window.

Claim shape differs by admission path:

| Path | `sub` | `email` | `common_name` |
|---|---|---|---|
| IdP login | Access user UUID (stable) | present | absent |
| Service token | empty | absent | client ID |

> **Open verification item.** The service-token claim shape above is not stated on
> Cloudflare's JWT-validation docs page. It must be confirmed against a real service-token
> assertion during OME-591 before the mapping is trusted.

## Threat model — the load-bearing constraint

`Cf-Access-Jwt-Assertion` is an ordinary HTTP header. **If the origin is reachable off-path,
anyone can forge it and the entire scheme is worthless.** This is the single most important
property of the deployment, and it is an infrastructure property, not a code property:

- Ingress must be `cloudflared` tunnel only (AIGateway is already ClusterIP-only, and Envoy
  deliberately does not route to it), or the CF proxy plus Authenticated Origin Pulls.
- The gateway therefore **never** trusts the *presence* of the header. It independently
  verifies signature, `iss`, `aud`, and `exp` on every request. Edge verification and origin
  verification are separate layers, and the origin's layer is the one that survives a
  misrouted network or a future ingress change.

Second fail-open path, closed at startup: `cf_access_enabled=true` together with
`auth_enabled=false` would make `current_account()` return `anonymous_account()` for
everyone, behind a gateway the operator believes is federated. That combination raises at
startup.

## Design — two header planes, one resolver chain

Clients satisfy two independent planes. The gateway only ever reasons about the second.

- **Edge plane:** whatever Cloudflare needs (`CF-Access-Client-Id`/`-Secret`, or
  `cf-access-token`).
- **App plane:** `Authorization: Bearer <token>`, plus the header/cookie Access injects.

`current_account()` becomes a thin driver over an ordered chain of resolvers:

```python
class IdentityResolver(Protocol):
    name: str
    async def resolve(self, request: Request) -> BaseAccount | None: ...
```

- Return `None` → "not my credential", fall through to the next resolver.
- Raise `HTTPException` → "my credential, and it is invalid", short-circuit the chain.
- Chain exhausted → 401.

Registration order (`main.py`, registry-wired — core never imports adapters, per the
hexagonal rule in the root `CLAUDE.md`):

1. **`LocalJwtResolver`** — today's HS256 logic, moved verbatim.
2. **`CfAccessResolver`** — `Cf-Access-Jwt-Assertion` header → `CF_Authorization` cookie →
   `Authorization: Bearer`. Verifies, then JIT-provisions.
3. **`ApiKeyResolver`** — gateway-issued `aigw_*` keys.

The `auth_enabled=False` short-circuit stays *ahead* of the chain, unchanged.

### Just-in-time provisioning

`accounts` gains `external_idp`, `external_subject` (unique together), and `email`;
`password_hash` becomes nullable.

**Identity key is `(idp, sub)` — never email.** CF `sub` is a stable Access user UUID; email
is mutable at the IdP and can be reassigned to a different human. For service tokens the key
is `common_name`.

**INVARIANT — a federated account cannot password-login.** `login()` explicitly rejects an
account with a null `password_hash`, returning the same generic `_INVALID_CREDENTIALS` 401 as
any other failure (no enumeration oracle, matching the existing SF-335 treatment of inactive
accounts) and logging the refusal server-side. A random-bcrypt sentinel is deliberately
*rejected* as the mechanism: an explicit null plus an explicit check is auditable, whereas a
sentinel silently becomes a live password the day someone backfills the column.

**Concurrency.** Two concurrent first requests from one user is the normal case for an SDK
with a connection pool, not an edge case. Provisioning is `get_or_create` guarded by the
`(external_idp, external_subject)` unique constraint with an `IntegrityError` re-read.

**Admin bootstrap.** The first federated user is nobody's admin. `is_admin` is granted at
provisioning time from the `AIGATEWAY_CF_ACCESS_ADMIN_EMAILS` allowlist and stays
gateway-owned thereafter. Cloudflare policy decides *reachability*; AIGateway decides
*authority*.

### Programmatic clients

A Cloudflare service token identifies the **token**, not a person. Machine traffic sharing one
service token therefore collapses onto a single identity — which directly breaks usage
attribution for the in-flight `credential_mode: shared` work, where attribution comes from
`current_account()`.

Resolution: after JIT provisioning, a user mints a gateway API key
(`POST /v1/auth/api-keys` → `aigw_<base62>`). The SDK then presents **both** planes — the
service token to satisfy the edge, and `Authorization: Bearer aigw_...` to identify the human
to the gateway. This yields per-user attribution under a shared edge token, revocation
independent of Cloudflare, and gateway auth that outlives the CF session. It also degrades
cleanly: the same SDK works against a local AIGateway with no Cloudflare in front of it.

Keys are stored **hashed with SHA-256**, not bcrypt. These are high-entropy random tokens, not
user-chosen passwords, so a work factor buys no meaningful brute-force resistance and costs
real latency on every request.

## Units

| Unit | Scope |
|---|---|
| OME-589 | `IdentityResolver` port + registry + `LocalJwtResolver` (behavior-preserving) |
| OME-590 | `accounts` external-identity columns, nullable `password_hash`, migration `0010` |
| OME-591 | `CfAccessResolver`: JWKS client, verifier, JIT provisioning, log redaction |
| OME-592 | `ApiKey` model + routes + `ApiKeyResolver`, migration `0011` |
| OME-593 | Settings, fail-fast startup validation, Helm values, operator runbook |

## Acceptance

- With `cf_access_enabled=false`, behavior is unchanged and every pre-existing auth test
  passes unmodified.
- With CF enabled, a request carrying a valid Access assertion and no prior account returns
  200 and creates exactly one `accounts` row; a concurrent duplicate creates no second row.
- Forged/expired/wrong-`aud`/wrong-`iss`/`alg:none` assertions return 401.
- A JWKS outage does not 401 requests whose `kid` is already cached.
- A minted `aigw_*` key authenticates; revoking it returns 401 on the next request.
- `cf_access_enabled=true` with `auth_enabled=false` fails to start.
