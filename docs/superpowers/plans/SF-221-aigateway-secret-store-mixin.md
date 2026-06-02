# SF-221 — Encrypt aigateway secrets at rest via abstract SecretStore mixin

**Asana:** https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215130136024389
**Assignee:** Dmitry Stebukov
**Due:** 2026-07-31
**Branch:** `SF-221-aigateway-secret-store-mixin`
**Depends on:** SF-219 (ORMStore must land first).
**Confidence:** ~93% (open question: one-shot re-encryption migration vs. lazy re-encrypt on next write — defer to implementation).

## Goal

After SF-219, aigateway stores OAuth tokens and the JWT secret as **plaintext JSON** in the `credential_blobs` table. SF-221 adds an envelope-encryption layer behind an **abstract `SecretStoreMixin`** so future cloud-managed key providers (AWS KMS, GCP KMS, HashiCorp Vault, cloud HSM) can plug in without touching call sites. Local dev keeps a self-contained AES-GCM implementation driven by a single env var.

## Non-goals

- Actual KMS provider implementation (interface stub + factory dispatch only).
- Encrypting non-secret columns (`oauth_connections.identity_email`, etc.) — separate ticket if needed.
- Key rotation tooling (column + format support shipped; rotation script deferred).
- Changing aigateway's deployment story beyond one new env var.

## Design

### 1. Module layout

```
core/secrets/
├── __init__.py
├── mixin.py     # SecretStoreMixin ABC
├── local.py     # LocalSecretStore (AES-GCM, env-var key)
├── kms.py       # KMSSecretStore stub — interface example, raises NotImplementedError
└── factory.py   # get_secret_store() — env-driven dispatch
```

### 2. `SecretStoreMixin` (the extension seam)

```python
from abc import ABC, abstractmethod


class SecretStoreMixin(ABC):
    """Encode/decode secret values for at-rest storage.

    Implementations stay symmetric: encrypt(plaintext) must round-trip through
    the same provider's decrypt. Cross-provider rotation is handled at the
    storage layer via the `ciphertext_version` column, not here.
    """

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        """Return a versioned, base64-encoded ciphertext blob.

        Format: 'v<N>:<provider-specific-payload>'. The leading 'v<N>' tag
        lets the storage layer route decryption to the right provider during
        rotation without parsing the payload.
        """

    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        """Reverse encrypt(). Raise SecretDecryptionError on tamper or
        wrong-key — never return partial plaintext."""

    @property
    @abstractmethod
    def version(self) -> str:
        """The 'v<N>' tag this provider produces (e.g. 'v1', 'kms-v1')."""
```

### 3. `LocalSecretStore` (default, prod-acceptable for single-tenant)

- Algorithm: AES-256-GCM via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- Key: 32 raw bytes, supplied as base64 in env `AIGATEWAY_SECRET_KEY`.
- Ciphertext format: `v1:<nonce-b64>:<ciphertext-b64>` (96-bit nonce, GCM tag included in ciphertext).
- `version = "v1"`.
- Required in prod (raise on missing). Local dev: auto-generate + persist to a `system_secrets` table (single row, account `aigateway-master-key`); same logic as today's JWT secret bootstrap.

### 4. `KMSSecretStore` (stub)

```python
class KMSSecretStore(SecretStoreMixin):
    """Stub showing the extension shape for cloud KMS providers.

    Implementations: AWS KMS (boto3 Encrypt/Decrypt API), GCP KMS
    (cryptoKeyVersion), Vault Transit. All return ciphertext format
    'kms-v1:<provider-payload>' so the storage layer can route during
    rotation. Implementation deferred to a follow-up ticket.
    """

    version = "kms-v1"

    def encrypt(self, plaintext: str) -> str:
        raise NotImplementedError("KMSSecretStore is a stub — see SF-221")

    def decrypt(self, ciphertext: str) -> str:
        raise NotImplementedError("KMSSecretStore is a stub — see SF-221")
```

Ship the stub so the factory's dispatch is exercised end-to-end and the extension shape is documented in code, not prose.

### 5. Factory

```python
def get_secret_store() -> SecretStoreMixin:
    provider = os.environ.get("AIGATEWAY_SECRET_PROVIDER", "local").lower()
    if provider == "local":
        return LocalSecretStore.from_env()
    if provider == "kms":
        return KMSSecretStore()
    raise RuntimeError(f"Unknown AIGATEWAY_SECRET_PROVIDER={provider!r}")
```

### 6. ORMStore integration

`core/credential_blob/store.py` (added in SF-219) gains a `SecretStoreMixin` dependency:

```python
class ORMStore(CredentialStore):
    def __init__(self, secret_store: SecretStoreMixin | None = None) -> None:
        self._secret = secret_store or get_secret_store()

    async def write(self, service, account, value):
        ciphertext = self._secret.encrypt(value)
        await CredentialBlob.update_or_create(
            service=service, account=account,
            defaults={"value": ciphertext, "ciphertext_version": self._secret.version},
        )

    async def read(self, service, account):
        row = await CredentialBlob.get_or_none(service=service, account=account)
        if row is None:
            return None
        return self._secret.decrypt(row.value)
```

Call sites in plugin auth modules / profile_index / jwt_secret stay unchanged — the encoding layer is invisible to them.

### 7. Schema change

Aerich migration `0004_credential_blob_ciphertext_version`:
- Add `ciphertext_version VARCHAR(16) NOT NULL DEFAULT 'v1'` to `credential_blobs`.
- Optional: a `system_secrets` table for the local auto-generated master key (single row).

The default `'v1'` means existing rows (written under SF-219 as plaintext) are wrong — see "Migration of existing data" below.

### 8. Migration of existing data

Two viable approaches; pick during implementation:

**(a) One-shot encrypt-in-place script.** Run once at deploy: read every row, encrypt its plaintext value, write back. Risk: must run before the new code starts serving, otherwise reads fail.

**(b) Lazy re-encrypt + dual-read.** Add a `ciphertext_version = 'v0'` sentinel meaning "plaintext" during a transition window. `ORMStore.read` checks the version: `v0` → return raw value; `v1` → decrypt. Next `write` upgrades the row. Drop `v0` support in a follow-up ticket. Lower risk; bounded transition window.

Recommendation: **(b)**. Lower-risk for the small number of in-flight credential rows.

### 9. Env / config

| Env var | Required | Default | Notes |
|---|---|---|---|
| `AIGATEWAY_SECRET_KEY` | prod (local) | auto-gen + persist | base64-encoded 32 raw bytes |
| `AIGATEWAY_SECRET_PROVIDER` | no | `local` | `local`, `kms` (stub), future providers |

`config.py` (pydantic-settings) gains both fields with validation.

### 10. Tests

- `test_local_secret_store.py` — encrypt/decrypt round-trip; tamper detection (mutate one byte of ciphertext → `SecretDecryptionError`); missing-key error; key-too-short error.
- `test_factory.py` — dispatch on env; unknown provider error.
- `test_ormstore_with_secret_store.py` — full path: `write("svc","acc","value")` then read; verify `value` column is **not** equal to `"value"`; verify decrypt returns `"value"`.
- `test_migration_v0_v1.py` — seed a `v0` row directly, read returns plaintext, next write upgrades to `v1`.
- `test_kms_store_stub.py` — raises NotImplementedError; factory still returns it when provider=kms.

### 11. Docs

- `apps/aigateway/README.md`: new "Secrets at rest" section. Explain `AIGATEWAY_SECRET_KEY` (how to generate: `python -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())'`), `AIGATEWAY_SECRET_PROVIDER`, and the v0→v1 transition.
- `apps/aigateway/CLAUDE.md`: extend storage policy:
  ```
  Secrets at rest are encrypted via SecretStoreMixin. Never write plaintext
  secrets to credential_blobs — always go through ORMStore. To add a new
  provider (KMS, Vault, HSM), implement SecretStoreMixin and register it in
  get_secret_store().
  ```

## Build sequence

1. **Branch + scaffolding.** Create `SF-221-aigateway-secret-store-mixin`. Add `cryptography` to pyproject. Scaffold `core/secrets/`.
2. **`SecretStoreMixin` + `LocalSecretStore`.** Implement, unit-test in isolation (no ORM yet). Tamper detection is critical — GCM enforces it but explicit test required.
3. **`KMSSecretStore` stub + factory.** Wire dispatch, document extension contract in module docstrings.
4. **Schema migration.** Aerich `0004` adds `ciphertext_version` column with default `'v1'` and a temporary `'v0'` value allowed.
5. **ORMStore integration.** Inject `SecretStoreMixin`; encrypt on write, decrypt on read. Add the v0 dual-read branch with a deprecation log warning.
6. **Master-key bootstrap.** In `main.py` lifespan, if `AIGATEWAY_SECRET_KEY` unset and `AIGATEWAY_SECRET_PROVIDER=local`, generate + persist via `system_secrets` table; log warning matching the JWT-secret bootstrap pattern.
7. **Tests** for every layer.
8. **Docs + guardrail update.**
9. **Manual verification.** Fresh checkout, OAuth flow for one provider, inspect `credential_blobs.value` in SQLite (`sqlite3 aigateway.sqlite3 'select * from credential_blobs;'`) — confirm values are `v1:...` ciphertext, never plaintext token strings.

## Risks

- **Lost master key = lost credentials.** All OAuth tokens become unrecoverable. Mitigation: document this prominently in README + CLAUDE.md; auto-gen path in local writes the key to a known DB location so a wiped `.env` doesn't immediately brick the dev environment.
- **Key-rotation complexity.** v0→v1 transition window must complete before introducing v2 (KMS). Document the "one rotation at a time" constraint in CLAUDE.md.
- **Performance.** AES-GCM is fast (≪1 ms per blob), but every cache miss now decrypts. The `BaseOAuthStrategy` in-memory cache from SF-219 already absorbs this — no further change needed.
- **`cryptography` library size.** Adds ~3 MB to the image. Acceptable.

## Verification (must pass before merge)

- `cd apps/aigateway && uv run pytest` — green.
- `sqlite3 aigateway.sqlite3 'select value from credential_blobs;'` after a fresh OAuth flow → every row begins with `v1:`.
- Tamper test: manually edit one byte of a ciphertext column → next read raises `SecretDecryptionError` (not a silent garbage decode).
- Restart with `AIGATEWAY_SECRET_KEY` unset (prod profile) → service refuses to start.
- Restart with `AIGATEWAY_SECRET_PROVIDER=kms` → service starts; any read/write attempt raises `NotImplementedError` from the stub (proves dispatch wiring).
- Full SF e2e suite (per `feedback_full_e2e_before_merge`).
