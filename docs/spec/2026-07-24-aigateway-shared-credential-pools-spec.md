# Spec — AIGateway shared (global) credential pools

> Linear filing deferred by owner for this unit — see `docs/work/2026-07-24-aigateway-shared-credential-pools.md`.

## Problem

Today every LLM credential in AIGateway is hard-scoped to a single `Account`:
`OAuthConnection.unique_together` includes `account_id`
(`core/oauth/models/oauth_connection.py:36-52`), every credential lookup is keyed by
`credential_key_for(account_id, connection_id)` (`core/oauth/store.py:18-30`), and
`current_account()` (`core/auth/middleware.py:13-55`) resolves exactly one `Account` per
request from the JWT. There is no way to give a group of users a shared provider key while
keeping auth on — the only "everyone shares" path is `auth_enabled=False`, which collapses
every caller onto `anonymous_account()` and loses per-user attribution entirely.

We want admins able to provision one credential per provider that all authenticated accounts
use, while every request stays attributable to the real calling account (usage/audit
isolation unaffected by which credential backs the call).

## Goals

- A gateway-wide **shared-keys mode**, opt-in via config, alongside the current per-account
  **BYOK mode** — one instance runs in exactly one mode at a time.
- Admin-managed **global credential pools**: one active credential per provider, stored
  through the existing `ORMStore`/`credential_blobs` path (no new secret backend — hard
  guardrail in `apps/aigateway/CLAUDE.md`).
- Per-account usage/audit attribution (logs, `RequestCacheEntry.account_id`) is unchanged in
  shared mode — credential resolution and request attribution are already separate layers;
  this design keeps them separate.
- Minimal `Account.is_admin` flag to gate pool management endpoints.

## Non-goals

- Per-account fallback logic (try personal key, fall back to pool). Rejected explicitly —
  the owner wants two distinct, non-overlapping deployment modes, not per-request resolution
  branching.
- Per-provider mode granularity (e.g. `openai` shared, `anthropic` BYOK on the same
  instance). `credential_mode` is a single instance-wide setting for this iteration; the
  branch point is already provider-scoped so this is a straightforward later extension, not
  a redesign.
- Multiple pools per provider / key rotation-with-overlap / round-robin. The `label` field
  on `GlobalCredentialPool` exists so this is additive later, not blocked.
- Per-user quota or rate-limiting on top of a shared key. Usage stays *visible* per account
  (existing logging/cache indexing); nothing throttles one account from exhausting a shared
  key. Separate feature if ever needed.

## Design

### Config — the mode switch

`config.py` `Settings` gains, mirroring `secret_provider` (`config.py:48`):

```python
credential_mode: Literal["byok", "shared"] = Field(
    default="byok", validation_alias="AIGATEWAY_CREDENTIAL_MODE"
)
```

Loaded once at `main.py:221` into `app.state.settings`, same lifecycle as `auth_enabled` /
`secret_provider`. Default `"byok"` — existing deployments are unaffected until an admin
opts in.

### Data model

New package `core/credential_pool/` (mirrors `core/oauth/` layout):

```
core/credential_pool/
  models/global_credential_pool.py   # GlobalCredentialPool
  store.py                           # global_pool_credential_locator_for()
  routes.py                          # admin CRUD
```

**`GlobalCredentialPool`**:

| field | type | notes |
|---|---|---|
| `id` | UUID pk | |
| `provider` | str | matches `ProviderRegistry` key (`core/registry.py:6-26`) |
| `auth_type` | str | `"api_key"` \| `"oauth"` — reuse existing `AuthType` |
| `label` | str, default `"default"` | forward-compat for multi-pool-per-provider; this iteration only resolves `"default"` |
| `is_active` | bool, default True | soft-disable without deleting |
| `created_by` | FK → `Account`, `on_delete=RESTRICT` | audit trail of provisioning admin |
| `created_at` / `updated_at` | datetime | |

`Meta.unique_together = (("provider", "label"),)`.

Migration `NNNN_global_credential_pools.py`, modeled on `migrations/0002_oauth_connections.py`.
Register `aigateway.core.credential_pool.models` in `db.py:20-26`'s
`apps.models.models` list.

**Secret storage** — no new table for the secret. Reuse `CredentialBlobStore`/`ORMStore` via
a locator parallel to `credential_key_for`/`credential_locator_for`
(`core/oauth/store.py:18-30`):

```python
def global_pool_credential_key_for(pool_id: str | UUID) -> str:
    return f"pool:{pool_id}"

def global_pool_credential_locator_for(provider: str, pool_id: str | UUID) -> dict[str, str]:
    return {
        "service": f"aigateway:{provider}:{global_pool_credential_key_for(pool_id)}",
        "account": DEFAULT_CREDENTIAL_ACCOUNT,
    }
```

This is the same shape `ApiKeyStrategy` (`core/api_key_strategy.py:31-96`) and the OAuth
strategy already consume — no change needed to either. The `profile_name` fed into
`credential_strategy_from` becomes `pool:{pool_id}` instead of `{account_id}:{connection_id}`.

**`Account.is_admin`**: add `is_admin: bool = fields.BooleanField(default=False)` to
`BaseAccount` (`core/auth/models/account.py:9-25`) via a small migration. Gates the
pool-management routes only.

### Resolution — the one seam that changes request behavior

`_credential_target_for_chat` (`routes/chat_credentials.py:115-164`) is where a request today
resolves which connection to use: Profile lookup first, else
`_active_oauth_connection_for_profile` (`chat_credentials.py:70-112`) filtered by
`account_id` + `provider` + label.

Branch at the top of `_credential_target_for_chat` on
`request.app.state.settings.credential_mode`:

- **`"byok"`**: existing logic, unchanged.
- **`"shared"`**: skip `ProfileIndexStore` and `_active_oauth_connection_for_profile`
  entirely — `account_id` is not consulted for credential resolution. New
  `_active_global_pool_for_provider(request, provider)`:
  - `GlobalCredentialPool.filter(provider=provider, label="default", is_active=True).first()`
  - 404 with an actionable message
    (`"no shared credential configured for provider={provider}; contact an admin"`) if none
    exists — consistent with the actionable-API-key-validation work already shipped
    (`66deae0a`).
  - Returns the same target shape `_credential_target_for_chat` already returns today, with
    `profile_name = global_pool_credential_key_for(pool.id)` and `auth_type = pool.auth_type`.
    *(Implementer: read the exact current return type before writing this — match it, don't
    guess.)*

**Usage isolation requires no new code.** `current_account(request)`
(`core/auth/middleware.py:13-55`) still resolves the real per-request account from the JWT
regardless of credential mode; `chat.py:88`'s `account_id = str(current.id)` and
`RequestCacheEntry.account_id` (`core/request_cache/models/request_cache_entry.py:32-36`)
are untouched. Credential mode only changes which secret backs the outbound call — it never
touches request attribution, because those are already separate layers in the current code.

### Admin API

Admin-gated (`current.is_admin`) routes mirroring the existing personal-connection CRUD
pattern in `routes/oauth_connections.py` (exemplar; implementer reads it and its test file
`tests/unit/test_oauth_connections_routes.py` before writing — don't reinvent the
request/response shapes):

- `POST /admin/credential-pools` — `{provider, auth_type, credentials}` → creates the
  `GlobalCredentialPool` row + writes the secret via
  `ORMStore.write(*global_pool_credential_locator_for(...))`.
- `GET /admin/credential-pools` — list, secret material redacted (same discipline as OAuth
  connection listing).
- `PATCH /admin/credential-pools/{id}` — toggle `is_active`, rotate the secret.
- `DELETE /admin/credential-pools/{id}` — deletes row + `credential_blobs` entry.

## Security & failure story

- **No new secret backend.** Pool secrets go through the identical `ORMStore` →
  `credential_blobs` → `SecretStoreMixin` (AES-256-GCM) path as every other credential in
  the gateway — satisfies the mandatory guardrail.
- **Admin surface is minimal and additive.** `is_admin` gates only the four pool-management
  routes; no other endpoint's authorization changes.
- **Failure mode when misconfigured:** shared mode with no pool row for a provider fails
  closed with a 404 naming the provider — never silently falls back to BYOK or to an
  anonymous/no-auth path.
- **Blast radius of a compromised shared key:** identical to today's blast radius of a
  compromised personal key (same storage, same encryption, same revocation path — disable
  or delete the pool row) — this design does not introduce a new class of credential
  exposure, it changes cardinality (one key, many accounts) not mechanism.

## Trade-offs

- Instance-wide mode, not per-provider — simpler now, extensible later (branch point is
  already provider-scoped).
- Single active pool per provider — no rotation-with-overlap or load balancing yet; `label`
  field leaves room.
- No per-user quota on a shared key — usage is visible, not throttled, per account.
