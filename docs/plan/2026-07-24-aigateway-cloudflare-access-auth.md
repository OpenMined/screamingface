# Plan — AIGateway federated authentication via Cloudflare Access

> Spec: `docs/spec/2026-07-24-aigateway-cloudflare-access-auth-spec.md` · Epic: OME-588

Five SDLC units, strictly ordered — each is independently committable and leaves the suite
green. Units 1–2 are prerequisites for 3; 4 depends on 1; 5 wires everything on last so no
intermediate commit can half-enable the feature.

## Unit 1 — OME-589 · IdentityResolver chain

**Create**
- `core/auth/resolvers/__init__.py` — exports the port + `build_default_resolvers()`
- `core/auth/resolvers/base.py` — `IdentityResolver` Protocol
- `core/auth/resolvers/local_jwt.py` — `LocalJwtResolver` (today's logic, moved)

**Modify**
- `core/auth/middleware.py` — `current_account()` drives `app.state.identity_resolvers`
- `main.py` — build and register the chain on `app.state`

**Tests** `tests/unit/auth/test_resolver_chain.py` — order, fall-through on `None`,
short-circuit on `HTTPException`, exhausted → 401, `auth_enabled=False` bypasses the chain.

**Contract:** every existing auth test passes unmodified.

## Unit 2 — OME-590 · Account external identity

**Modify**
- `core/auth/models/account.py` — `external_idp`, `external_subject`, `email`,
  `unique_together`, nullable `password_hash`
- `routes/auth_session.py` — `login()` rejects null-hash accounts (generic 401 + server log)
- `core/auth/schemas.py` — `AccountOut` gains `email`

**Create**
- `migrations/0010_account_external_identity.py` (idiom: `0008`/`0009` — built-in Tortoise
  migrations, `ops.AddField` / `ops.AlterField`; never Aerich)

**Tests** `tests/unit/auth/test_federated_account_login.py` — null-hash login → generic 401
+ logged; duplicate `(idp, sub)` → IntegrityError; local accounts unaffected.

## Unit 3 — OME-591 · Cloudflare Access resolver

**Create**
- `core/auth/cf_access/__init__.py`
- `core/auth/cf_access/jwks.py` — `kid`-aware cache, fetch timeout, stale-on-error
- `core/auth/cf_access/verifier.py` — RS256 + `iss`/`aud`/`exp`
- `core/auth/cf_access/identity.py` — claims → `(idp, subject, email)`
- `core/auth/cf_access/provisioning.py` — `get_or_create_cf_access_account`
- `core/auth/cf_access/resolver.py` — `CfAccessResolver`

**Modify**
- `core/auth/log_filter.py` — redact CF assertions + client secrets
- `main.py` — register the resolver when enabled

**Tests** `tests/unit/auth/cf_access/` — fixed RSA keypair fixture, fake JWKS. Covers valid
IdP token, valid service token, `kid` rotation, `aud`/`iss` mismatch, expired, `alg:none`,
JWKS outage with warm cache, concurrent-provisioning race, admin allowlist.

## Unit 4 — OME-592 · Gateway API keys

**Create**
- `core/auth/models/api_key.py` — `ApiKey`
- `core/auth/api_keys.py` — generate / hash / parse (`aigw_<base62>`, SHA-256)
- `core/auth/resolvers/api_key.py` — `ApiKeyResolver`
- `routes/api_keys.py` — mint / list / revoke
- `migrations/0011_api_keys.py`

**Modify** `db.py` is unchanged (`aigateway.core.auth.models` already registered);
`main.py` includes the router and appends the resolver.

**Tests** `tests/unit/auth/test_api_keys.py` — mint→use→revoke, expiry, inactive account,
listing never leaks material, plaintext unrecoverable after creation.

## Unit 5 — OME-593 · Config, startup validation, chart

**Modify**
- `config.py` — the five `cf_access_*` / `api_keys_*` settings + validators
- `main.py` — fail-fast lifespan checks
- `charts/aigateway/values.yaml` + `templates/deployment.yaml`
- `apps/aigateway/docs/` — operator runbook (Access app setup, Service Auth policy, AUD
  retrieval, **origin-isolation requirement**)

**Tests** `tests/unit/test_cf_access_settings.py` — every invalid combination raises;
defaults preserve current behavior.

## Gates (per unit, from `.claude/sdlc.local.md`)

`uv run .claude/scripts/run_gates.py aigateway` — ruff check · ruff format --check · pyright
· `check_no_enterprise.py` · pytest with `--cov-fail-under=80`.

## Known process deviation

`.claude/sdlc.local.md` marks the `tortoise-dev` companion skill `mandatory: true` for
Tortoise work; it is **not installed** in this environment. Units 2 and 4 follow the
migration idioms observed directly in `migrations/0008` and `0009` instead (built-in
Tortoise migrations, model-per-file, abstract `Base*` model + concrete table subclass).
Flagged to the owner.
