---
ticket: OME-591
stack: aigateway
status: in_progress
started: 2026-07-24
finished:
---

# OME-591 — Cloudflare Access identity resolver with JWKS verification and JIT provisioning

## Intent

Verify Cloudflare's identity assertion at the origin and materialise the account. This is the
unit that delivers the actual product goal: a user admitted by the Access policy reaches every
authenticated route with no registration and no `/v1/auth/login`.

## Design decisions

**The origin verifies independently of the edge.** `Cf-Access-Jwt-Assertion` is an ordinary
header; trusting its presence would mean anyone able to reach the origin off-path can forge
any identity. Ingress isolation (cloudflared tunnel only) is the deployment's job; verifying
signature + `iss` + `aud` + `exp` on every request is ours, and it is the layer that survives
a future ingress change.

**`kid`-aware JWKS with stale-on-error.** Cloudflare rotates the signing key every 6 weeks and
serves current + previous with a 7-day grace. Caching a single cert breaks at every rotation.
A hard failure on fetch error would let a Cloudflare certs blip 401 the entire fleet, so a
warm cache keeps serving while a refresh is retried.

**Identity key precedence: `sub`, else `common_name`.** IdP logins carry a stable Access user
UUID in `sub`; service tokens carry an empty `sub` and the client ID in `common_name`. Email
is a label, never a key.

**Provisioning races are the normal case,** not an edge case — an SDK with a connection pool
issues several first requests at once. `get_or_create` guarded by the real unique constraint
from OME-590, with an `IntegrityError` re-read.

## Planned changes

- create `core/auth/cf_access/{__init__,jwks,verifier,identity,provisioning,resolver}.py`
- modify `core/auth/log_filter.py` — redact CF assertions and client secrets
- create `tests/unit/auth/cf_access/` (fixed RSA keypair fixture, fake JWKS)

No schema change this unit (OME-590 shipped it) → no migration.

## Test plan

- valid IdP assertion → account created, email populated, `is_admin` per allowlist
- valid service-token assertion → account created from `common_name`
- `kid` rotation: token signed by the *previous* key still verifies
- `aud` mismatch / wrong `iss` / expired / `alg: none` / HS256-signed forgery → rejected
- unknown `kid` triggers exactly one refetch, not one per request
- JWKS unreachable with a warm cache → still verifies
- JWKS unreachable with a cold cache → rejects (never fails open)
- concurrent first requests → exactly one account row
- token accepted from the header, the cookie, and `Authorization: Bearer`
- the assertion never appears in logs

## Acceptance

- With `cf_access_enabled=false` (default) nothing changes.
- No fail-open path exists on any error branch.

## Outcome

- **Actual files:** `core/auth/cf_access/{__init__,jwks,identity,provisioning,resolver}.py`,
  `core/auth/log_filter.py`; tests `tests/unit/auth/cf_access/{conftest,test_verification,
  test_provisioning,test_resolver}.py` (38 tests).
- **Commits:** NONE — blocked, see OME-589 ledger deviation 1.
- **Gates:** `run_gates.py aigateway` ALL GREEN. Auth suite 122 passed.
- **Deviations / findings:**
  1. **Design flaw caught by a test, then fixed.** `CfAccessIdentity.username` initially
     derived from `email`. Since `username` is UNIQUE, two distinct subjects that ever share
     an address collide and the second user cannot be provisioned at all — reintroducing
     email-as-identity through the back door, the exact coupling this design rejects.
     Now derived from `subject`, hashed rather than truncated past 64 chars.
  2. Merged the planned `verifier.py` and `identity.py` into one module — the verifier's only
     output is an identity and splitting them produced two ~40-line files with a circular
     concern. `jwks.py` stayed separate (it has genuinely independent caching state).
  3. Added an unplanned JWKS **refetch rate limit**: without it a forged `kid` lets an
     unauthenticated caller drive unbounded outbound requests to Cloudflare.
  4. `log_filter.py`'s single `_HEADER_NAME` became `_SENSITIVE_HEADERS`; the class name
     `RedactProvisioningTokenFilter` is now too narrow but renaming it would touch prior
     tests (append-only rule) — left for a follow-up.
