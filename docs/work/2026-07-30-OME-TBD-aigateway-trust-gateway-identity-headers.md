---
ticket: OME-TBD
stack: aigateway
status: in_progress
started: 2026-07-30
finished:
---

# OME-TBD — aigateway trusts the PULSE gateway-identity headers

## Intent

Sibling of the url4-cloud half (`2026-07-29-OME-TBD-url4-cloud-identity-header-propagation.md`),
which now sends `X-User-Email` / `X-User-Id` / `X-Service-Id` / `X-Tenant` on every
`POST /v1/chat/completions`. aigateway currently ignores them and authenticates with its own JWT,
so the identity arrives and is dropped. This makes aigateway resolve the caller from those headers.

`current_account()` is the single choke point every authenticated route depends on, so the change
lands there: everything downstream (profiles, credential blobs, the request cache) keeps working
because it still receives a real `Account`.

## Planned changes

- `src/aigateway/core/auth/gateway_identity.py` (new) — parse the headers into a `GatewayIdentity`,
  derive a deterministic account id (UUIDv5) + bounded username, get-or-create the `Account`.
- `src/aigateway/core/auth/middleware.py` — `current_account` switches on the auth mode.
- `src/aigateway/config.py` — `AIGW_AUTH_MODE = jwt | gateway_headers | disabled`; the legacy
  `AIGATEWAY_AUTH_ENABLED` supplies the default so existing deployments are unchanged.
- `src/aigateway/main.py` — the loopback middleware and admin bootstrap key off the mode.

## Test plan

- A human caller (`X-User-Id` + `X-User-Email`) resolves to a stable account across requests.
- A service caller (`X-Service-Id`, no user headers) resolves to its own distinct account.
- The SAME identity yields the same `account_id` on every request (credential blobs are keyed on
  it — an unstable id orphans them).
- Different tenants with the same subject are different accounts.
- Missing/blank identity headers in `gateway_headers` mode → 401, never anonymous.
- A missing `X-Tenant` → 401 (nothing to namespace the subject under).
- A deactivated header-derived account → 401, not silently recreated.
- `jwt` mode is byte-identical to today; `disabled` mode still yields anonymous (local).
- A long email still fits `Account.username` (max_length=64).

## Acceptance

- A url4-cloud run started through Envoy is attributed to a real aigateway account.
- Local mode (`disabled`) needs no identity and keeps working.
- `run_gates.py aigateway` green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus `tests/unit/auth/test_gateway_identity.py` (25 tests) and a
  one-line change to each of `tests/unit/auth/test_middleware.py` /
  `tests/unit/test_chat_x_profile.py` (see Deviations).
- **Commits:** not committed yet.
- **Gates:** `run_gates.py aigateway --skip-append-only` → ALL GATES GREEN (ruff, ruff format,
  pyright 0 errors, check_no_enterprise, pytest 1320 passed, coverage ≥80).
- **Deviations:**
  - Two existing tests mutated `settings.auth_enabled` at runtime to get anonymous. `auth_mode` is
    now the source of truth and is resolved at construction, so they were changed to set
    `auth_mode = "disabled"`. The env→Settings path is unchanged, which `_reconcile_auth_mode` and
    `test_the_legacy_flag_alone_still_disables_auth` both pin.
  - Username is a hash (`gw:<sha256[:32]>`) rather than the readable identity: `Account.username`
    is `max_length=64` and a tenant plus a long email exceeds it. The readable form is in
    `display_name`.
  - No Linear issue filed (owner deferred it); ticket id still `OME-TBD`.

## Verified end state

In `gateway_headers` mode a chat request carrying `X-Tenant` + `X-User-Email` now passes auth and
reaches credential resolution — it returns `404 profile_not_found` for a principal with no stored
credentials, NOT `401`. That is the intended boundary of this unit.

## Not done

- **Nothing provisions credentials for a header-derived principal.** Each principal gets its own
  credential namespace (`credential_name_for(account.id, profile)`), so a new caller has no profile
  until someone configures one. Whether that is per-user OAuth, operator-managed org keys, or a
  fallback is a separate decision — deliberately not invented here.
- **`reauth_url`** in `chat_credentials.py:161` points at OAuth routes that a header-mode caller
  cannot meaningfully use.
- **The network precondition is unverified.** Header trust is only sound while aigateway is
  unreachable except through Envoy and the Runner Pods. Nothing in this change enforces or tests
  that; `templates/networkpolicy.yaml` omits `from:` when `ingressCIDRs` is empty, which fails open.
