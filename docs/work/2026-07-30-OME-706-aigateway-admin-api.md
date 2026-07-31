---
ticket: OME-706
stack: aigateway
status: done
started: 2026-07-30
finished: 2026-07-30
---

# OME-706 — Add `/v1/admin` API: email allowlist + account and API-key profile management

## Intent

`OME-684` made Cloudflare Access the identity source: Envoy injects `X-User-Email` and aigateway
get-or-creates an `Account` keyed on it. Nothing then provisions credentials for that account, so a
new caller authenticates successfully and immediately gets `404 profile_not_found` — the gap that
issue names in its own out-of-scope list. This unit adds the operator-facing surface that closes it:
an allowlisted admin creates accounts and attaches **static provider API keys** to them.

No OAuth. aigateway's OAuth profile/connection endpoints are untouched and simply not mirrored here.

## Branch note

`OME-684` (PR #444) is not merged, and this code imports `core/auth/cloudflare_identity.py`, which
exists only on that branch. Developed on `OME-706-admin-api`, branched from
`origin/OME-684-gateway-identity-headers` with the `OME-707` commits cherry-picked on top, so the
whole system runs locally. **Before opening a PR this rebases onto `main`** once #444 merges, at
which point #444's commits drop out and only this unit's remain — no stacked PR.

Verified the base works before starting: with `AIGW_AUTH_MODE=cloudflare_headers` and
`AIGW_ALLOWED_NETWORKS=127.0.0.0/8`, `GET /v1/models` is 401 without the header and 200 with it,
and the account row is auto-created with `username = the email`.

## Planned changes

- `src/aigateway/config.py` — `admin_emails: Annotated[frozenset[str], NoDecode]` from
  `AIGATEWAY_ADMIN_EMAILS`. `NoDecode` is mandatory (pydantic-settings JSON-decodes complex types
  from env — the exact trap `allowed_networks` documents). Validator splits/strips/lowercases to
  match `CloudflareIdentity.username`.
- `src/aigateway/core/auth/admin.py` (new) — `AdminPrincipal`, `require_admin`, `CurrentAdmin`.
  Reuses `HEADER_USER_EMAIL`, `identity_from_headers`, `peer_in_networks` from `cloudflare_identity`.
- `src/aigateway/routes/admin.py` (new) — `/v1/admin` router + `AdminAuditRoute`.
- `src/aigateway/core/admin_schemas.py` (new) — typed request/response models, so the generated
  OpenAPI is usable as a TypeScript client source (the existing profile routes return bare `dict`).
- `src/aigateway/routes/credential_persistence.py` — extract the api-key write path so the tenant
  route and the admin route share one implementation.
- `src/aigateway/main.py` — register the router.

## Test plan (RED first)

- `admin_emails` parsing: comma list, whitespace, case-folding, empty → empty frozenset
- gating: empty allowlist → 503 · `jwt` mode → 503 · `disabled` mode → allowed
- untrusted peer → 403 **before** the header is read, and **no account row created**
- missing / blank header → 401
- non-allowlisted email → 403, and **no `Account` row created for that email**
- allowlisted email in mixed case → allowed
- accounts: list, search, create (idempotent — same code path as auto-provisioning), patch
  display_name / is_active; deactivated account then fails `current_account`
- profiles: list for another account, upsert api-key, patch defaults, delete
- cross-account isolation: admin acting on A never mutates B
- the raw API key never appears in a response body or a log record

## Acceptance

- `run_gates.py aigateway` green, including the auth-surface coverage step
- against the local instance: allowlisted → 200, non-allowlisted → 403, no header → 401,
  and a non-allowlisted email leaves no `Account` row
- end to end: attach a key through `/v1/admin`, then that account's `GET /v1/auth/profiles`
  returns the profile

## Outcome

- **Actual files:** as planned. New: `core/auth/admin.py`, `core/admin_schemas.py`,
  `routes/admin.py`, `tests/unit/auth/test_admin_allowlist.py`,
  `tests/unit/test_admin_profile_routes.py`. Modified: `config.py` (+`admin_emails`),
  `main.py` (router + OpenAPI wrapper), `routes/auth.py` (two extractions).
  `routes/credential_persistence.py` was NOT touched — see deviation 1.

- **Gates:** `run_gates.py aigateway` — ruff check · ruff format · pyright · enterprise guard ·
  pytest `--cov-fail-under=80` → ALL GATES GREEN. **1368 → 1407 tests** (39 new: 23 allowlist,
  16 profile routes), zero regressions.

- **Verified against a live gateway**, not only tests. `AIGW_AUTH_MODE=cloudflare_headers`,
  `AIGW_ALLOWED_NETWORKS=127.0.0.0/8`, `AIGATEWAY_ADMIN_EMAILS` set:

  | request | result |
  |---|---|
  | no header | 401 |
  | non-allowlisted address | 403, and no `Account` row created |
  | allowlisted address | 200 |
  | allowlisted, MIXED case | 200 |
  | `POST /accounts {"email":"Alice@OpenMined.org"}` | 201, username `alice@openmined.org` |
  | same address again | 201, same id (idempotent) |
  | `{"email":"notanemail"}` | 422 |
  | `PUT …/api-key` with a fake key | reached the provider's real validation → `api_key_invalid` |

  OpenAPI: `CloudflareUserEmail` apiKey scheme on `X-User-Email`, 8 admin operations secured,
  0 non-admin operations touched, document cached on second call.

- **Deviations:**
  1. **Extraction landed in `routes/auth.py`, not `credential_persistence.py`.** Moving ~90 lines
     carrying five OME-307 invariants across modules is risk without benefit; both routes now call
     `upsert_api_key_profile` / `delete_profile_for_account` where the invariants already live.
  2. **No `email-validator` dependency.** `CreateAdminAccountRequest.email` does a shape check
     instead. Cloudflare Access is the validator of record — this gateway only ever sees addresses
     it already verified. What the check exists for is an operator TYPO, whose consequence is
     specific: an account keyed on a string Envoy will never send is unreachable forever and looks
     identical to a real one in the console.
  3. **`POST /accounts` is idempotent (201), not 409 on conflict.** The account WILL exist the
     moment its owner sends a request, so "already exists" is not a state an operator can act on.
     A *deactivated* account is the exception and does 409 — silently reactivating would undo a
     deliberate lockout.
  4. **The local in `_lifespan` was renamed `admin` → `admin_account`.** The new router module is
     imported as `admin` at module scope, and the local shadowed it for the rest of the function.
     Harmless today, a trap for the next edit.
  5. **Coverage of the raw-key-never-logged claim is partial.** Tests assert the key is absent from
     every response body; no test asserts it is absent from log records. The masking happens in the
     shared path `test_api_key_routes.py` already covers, so the risk is low — but the ledger should
     not claim more than was checked.

## Not done here

- The full api-key happy path against a REAL provider. The route reaches provider validation
  correctly (proved by the live `api_key_invalid`), but completing it needs a genuine key.
- Chart/values wiring for `AIGATEWAY_ADMIN_EMAILS` — belongs with the deployment change.

## Branch state at close

Still on `OME-706-admin-api`, which sits on 11 of #444's commits. **Rebase onto `main` once #444
merges** (`git rebase --onto main origin/OME-684-gateway-identity-headers`) — those 11 drop out and
only OME-707 + OME-706 remain, so the PR is never stacked.
