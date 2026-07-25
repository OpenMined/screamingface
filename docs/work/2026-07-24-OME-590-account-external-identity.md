---
ticket: OME-590
stack: aigateway
status: in_progress
started: 2026-07-24
finished:
---

# OME-590 — Add external-identity columns to accounts and make password_hash nullable

## Intent

`accounts` can only represent a local password user: `username` is the only identity key and
`password_hash` is NOT NULL. A Cloudflare-authenticated user has neither — they have a stable
IdP subject and (usually) an email. Give the table a federated-identity key so OME-591 can
provision accounts just-in-time, and close the door on those accounts ever password-logging-in.

## Design decisions

**Key on `(external_idp, external_subject)`, never email.** Cloudflare's `sub` is a stable
Access user UUID; email is mutable at the IdP and can be reassigned to a different human.
Email is stored as a label and for the admin allowlist, not as an identity key.

**`password_hash` becomes nullable, and `login()` explicitly rejects null.** The rejected
alternative was storing an unguessable random-bcrypt sentinel and letting
`verify_password_or_dummy` fail naturally. That is worse: it leaves a live password column on
a federated account, so the invariant survives only as long as nobody backfills it. An
explicit null plus an explicit check is auditable and greppable.

**The refusal is indistinguishable from bad credentials.** Same `_INVALID_CREDENTIALS` body
as SF-335's inactive-account handling — a distinct error would be a federation-status
enumeration oracle.

## Planned changes

- modify `core/auth/models/account.py` — `external_idp`, `external_subject`, `email`,
  `unique_together`, nullable `password_hash`
- modify `routes/auth_session.py` — reject null-hash accounts
- modify `core/auth/schemas.py` — `AccountOut.email`
- create `migrations/0010_account_external_identity.py` (S1: schema + migration same unit)
- create `tests/unit/auth/test_federated_account.py`

## Test plan

- null-hash account → `/v1/auth/login` 401, body byte-identical to a wrong-password attempt
- the refusal is logged server-side
- duplicate `(external_idp, external_subject)` → IntegrityError
- two accounts may both have NULL external identity (partial-uniqueness sanity — local
  accounts must not collide with each other)
- existing local accounts still log in; `AccountOut` exposes `email`, never `password_hash`

## Acceptance

- Migration applies clean; all prior auth tests pass unmodified.

## Outcome

- **Actual files:** `core/auth/models/account.py`, `routes/auth_session.py`,
  `core/auth/schemas.py`, `migrations/0010_account_external_identity.py`,
  `tests/unit/auth/test_federated_account.py` (8),
  `tests/unit/test_migration_external_identity.py` (2 — new module, see Deviations).
- **Commits:** NONE — blocked, see OME-589 ledger deviation 1.
- **Gates:** `run_gates.py aigateway` ALL GREEN. Auth suite 84 passed.
- **Deviations / findings:**
  1. **Security fix beyond the planned scope, in this unit's blast radius.**
     `verify_password_or_dummy` falls back to the hash of the module-level constant
     `passwords._DUMMY_PASSWORD`. That constant is public, so once `password_hash` became
     nullable, submitting it verbatim made `password_ok` **True** for any federated account.
     The NULL check therefore had to run *independently of* `password_ok`, not after it.
     Covered by `test_federated_account_rejects_the_public_dummy_password`.
  2. **Migration data loss, found and fixed.** SQLite cannot alter nullability, so Tortoise
     rebuilds the table (`schema_editor/sqlite.py::_remake_table`: CREATE / INSERT SELECT /
     `DROP TABLE accounts` / RENAME). That DROP has no FK guard, so under the default
     `PRAGMA foreign_keys=ON` it cascade-deleted every `oauth_connections` and
     `global_credential_pools` row while reporting OK. Fixed with `atomic = False` plus a
     dialect-guarded `PRAGMA foreign_keys` toggle (the pragma is a silent no-op inside a
     transaction, hence non-atomic). Caught by the pre-existing
     `test_full_chain_applies_to_populated_database`.
  3. **Two Tortoise no-op traps.** `AlterModelOptions` is state-only (no DDL) and would have
     left `unique_together` unenforced in every migrated DB; `AddField(db_index=True)` emits
     no `CREATE INDEX`. Both replaced with explicit `AddConstraint`/`AddIndex` and asserted
     against `sqlite_master`.
  4. New test lives in its own module `test_migration_external_identity.py` (reusing the
     sibling's `_migrate` helper) because the append-only gate rejects *any* edit to a prior
     test file, including a pure addition.
  5. `tortoise-dev` companion skill (`mandatory: true`) unavailable — followed the `0008`/
     `0009` in-repo idioms instead. Findings 2 and 3 are exactly the class of trap that skill
     presumably encodes; recommend installing it before OME-592's migration.
