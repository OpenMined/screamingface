---
ticket: none (Linear filing deferred by owner for this unit)
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-24
---

# AIGateway shared (global) credential pools

## Intent

Let an AIGateway admin provision a shared/global provider credential that all authenticated
accounts use, as an alternative deployment mode (`AIGATEWAY_CREDENTIAL_MODE=shared`) to
today's per-account BYOK credentials — while keeping per-account usage/audit attribution
intact. Design in `docs/spec/2026-07-24-aigateway-shared-credential-pools-spec.md`;
implementation executed in this same unit on owner's explicit "Execute the implementation
changes" instruction (no separate `docs/plan/` artifact — see Deviations).

## Planned changes

Per the spec: config mode switch, `GlobalCredentialPool` model + migration, `Account.is_admin`
+ migration, admin CRUD routes, the resolution branch in `chat_credentials.py`.

## Test plan

- Admin gating: unauthenticated → 401; authenticated non-admin → 403 `admin_required`.
- Admin CRUD: create (201, key never echoed) → conflict on a second active pool for the same
  provider (409) → list → deactivate (PATCH) → delete → 404 after delete.
- Shared-mode chat with no pool configured → 404 `credential_pool_not_configured`.
- Shared-mode chat with a pool configured, exercised by two distinct accounts → both dispatch
  through the same injected key, and both remain individually attributable (distinct
  `account_id`s), proving usage isolation is unaffected by credential mode.

## Acceptance

- All planned test-plan cases pass (5/5 new tests green).
- Full gate suite green: `ruff check`, `ruff format --check`, `pyright` (0 errors),
  `scripts/check_no_enterprise.py`, `pytest --cov=aigateway --cov-fail-under=80` (1303 passed,
  40 skipped, 90% coverage).

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `docs/spec/2026-07-24-aigateway-shared-credential-pools-spec.md`,
    `docs/work/2026-07-24-aigateway-shared-credential-pools.md`
  - `src/aigateway/config.py` — `credential_mode` setting + validator
  - `src/aigateway/core/auth/models/account.py` — `Account.is_admin`
  - `src/aigateway/core/auth/bootstrap_admin.py` — bootstrap "admin" account gets
    `is_admin=True` (create + self-heal on existing rows)
  - `src/aigateway/core/auth/middleware.py` — `current_admin_account`/`CurrentAdminAccount`
  - `src/aigateway/core/credential_pool/` (new package) — `models/global_credential_pool.py`,
    `store.py`, `schemas.py`
  - `src/aigateway/migrations/0008_account_is_admin.py`,
    `0009_global_credential_pools.py`
  - `src/aigateway/db.py` — registered `core.credential_pool.models`
  - `src/aigateway/routes/credential_pools.py` (new) — admin CRUD; registered in `main.py`
  - `src/aigateway/routes/chat_credentials.py` — shared-mode branch in
    `_credential_target_for_chat` + new `_inject_shared_pool_credentials`
  - `tests/unit/test_credential_pool_shared_mode.py` (new, 5 tests)
- **Commits:** none — awaiting explicit commit instruction (CLAUDE.md: only commit when
  asked).
- **Gates:** `ruff check` clean; `ruff format --check` clean; `pyright` 0 errors/0 warnings;
  `check_no_enterprise.py` OK; `pytest --cov=aigateway --cov-fail-under=80 -q` → 1303 passed,
  40 skipped, 90% coverage (required 80%).
- **Deviations:**
  - No Linear ticket filed — owner explicitly instructed not to ("PS: DO not create linear
    ticket"). Retroactively fileable (`OME-N`) if the owner later wants Linear tracking.
  - No separate `docs/plan/` artifact — owner said "Execute the implementation changes"
    directly against the approved spec; the spec's Design section was detailed enough
    (files, signatures, exact seams) to implement from directly.
  - **Scope cut vs. spec: pools are api-key auth only for this iteration** (spec's
    `GlobalCredentialPool.auth_type` field allows `"oauth"` in principle, but
    `CreateGlobalCredentialPoolRequest`/`PatchGlobalCredentialPoolRequest` only accept
    `api_key`). Building an admin-driven OAuth authorization flow for a pool (no per-user
    browser session to anchor it to) was judged materially larger scope than the spec's
    core ask; api-key covers the common shared-key case (OpenAI/Anthropic/HF-style keys).
    Follow-up if OAuth-backed pools are needed.
  - **Pool credential errors never mark the pool row.** Unlike BYOK connections (which flip
    to `status="error"` on a bad credential), a shared-mode 401 just raises
    `shared_credential_invalid` per-request — there is no per-account row to mark, and
    reconciling a bad shared key is an admin action via `/v1/admin/credential-pools`, not
    something a single user's failed chat request should mutate. Documented in
    `_inject_shared_pool_credentials`'s docstring.
