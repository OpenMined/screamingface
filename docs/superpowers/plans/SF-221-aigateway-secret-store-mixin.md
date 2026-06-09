# SF-221 — Encrypt aigateway secrets at rest via abstract SecretStore mixin

**Asana:** https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215130136024389
**Assignee:** Dmitry Stebukov
**Due:** 2026-07-31
**Branch:** `SF-221-aigateway-secret-store-mixin`
**Depends on:** SF-219 (ORMStore landed — `core/credential_blob/store.py` + `credential_blobs` table).
**Confidence:** ~96%.

> **Revision note (2026-06-08, codebase-validated).** This plan was re-validated against the
> *current* `apps/aigateway` tree, the installed `tortoise-orm==1.1.7`, and an isolated
> `cryptography==48.0.0` install. Eight corrections vs. the prior draft are listed in
> **Appendix A**. The three previously-open design forks (async vs sync mixin; legacy-row
> handling; missing-key behavior) are now **decided** — see each section.

---

## Goal

After SF-219, aigateway stores OAuth tokens and the JWT secret as **plaintext JSON** in the
`credential_blobs` table (`value TEXT`). SF-221 inserts an **envelope-encryption layer** behind
an abstract `SecretStoreMixin` **port**, so future cloud-managed key providers (AWS KMS, GCP KMS,
HashiCorp Vault, cloud HSM) plug in without touching call sites. Local dev keeps a self-contained
AES-256-GCM provider driven by one env var.

**Layering (per the ticket):** `ORMStore` is the **storage** layer (it owns the row); the
`SecretStoreMixin` provider is the **encoding** layer (it owns the ciphertext format). `ORMStore`
writes ciphertext and decrypts on read; every existing call site keeps calling
`store.read / write / delete` unchanged.

## Non-goals

- Actual KMS/Vault/HSM provider implementation (interface stub + factory dispatch only).
- Encrypting non-secret columns (`oauth_connections.identity_email`, etc.) — separate ticket.
- Key-rotation **tooling** (the `ciphertext_version` column + versioned format ship; the
  dual-read/re-encrypt rotation script is documented but deferred).
- A one-shot re-encryption of existing rows (handled by lazy upgrade-on-write — see §8).
- Per-row AAD binding of ciphertext to `(service, account)` (noted as future hardening in §12).
- Any new "is this prod?" deployment-mode detection mechanism.

---

## Design

### 1. Module layout

Follows the `tortoise-dev` convention used by `core/auth/models` and `core/oauth/models`
(models in a `models/` subpackage, one model per file, abstract `Base*`, `Meta` first).

```
src/aigateway/core/secrets/
├── __init__.py          # curated public surface (re-exports); NO __models__ here
├── mixin.py             # SecretStoreMixin (ABC) + SecretStoreError / SecretDecryptionError
├── local.py             # LocalSecretStore (AES-256-GCM, 32-byte key)
├── kms.py               # KMSSecretStore stub — extension shape, raises NotImplementedError
├── factory.py           # build_secret_store() dispatch + active-store singleton accessor
├── master_key.py        # get_or_create_master_key() async bootstrap (env or sibling table)
└── models/
    ├── __init__.py      # re-exports BaseSecretMasterKey, SecretMasterKey; __models__
    └── master_key.py    # BaseSecretMasterKey (abstract) + SecretMasterKey (table)
```

### 2. `SecretStoreMixin` — the extension seam (**ASYNC** — decided)

The port is **async**. Rationale: `ORMStore.read/write` are already `async`, and the entire
reason this ticket exists is to let network-backed providers (KMS/Vault = remote I/O) drop in
without changing call sites. A sync port would force a future KMS provider to block-in-thread,
defeating Open/Closed + Liskov. The local AES-GCM provider is CPU-bound and simply *does not
await* inside its async methods — that is legal and cheap. (We deliberately do **not** use
`asyncio.to_thread` for local AES-GCM: it is microsecond-scale; offloading would only add
overhead.)

```python
# core/secrets/mixin.py
from __future__ import annotations

from abc import ABC, abstractmethod


class SecretStoreError(Exception):
    """Base class for secret-store failures."""


class SecretDecryptionError(SecretStoreError):
    """Raised when ciphertext fails authentication (tamper / wrong key / corrupt)."""


class SecretStoreMixin(ABC):
    """Port: encode/decode secret values for at-rest storage.

    Async so network-backed providers (KMS/Vault/HSM) plug in without changing
    call sites. encrypt(plaintext) must round-trip through the SAME provider's
    decrypt. Cross-provider rotation is bookkept at the storage layer via the
    `ciphertext_version` column, never here.
    """

    @property
    @abstractmethod
    def version(self) -> str:
        """The version tag this provider stamps (e.g. 'v1', 'kms-v1')."""

    @abstractmethod
    async def encrypt(self, plaintext: str) -> str:
        """Return a versioned, self-describing ciphertext string.

        Format owned by the provider; local uses 'v1:<nonce-b64>:<ct-b64>'.
        """

    @abstractmethod
    async def decrypt(self, ciphertext: str) -> str:
        """Reverse encrypt(). Raise SecretDecryptionError on tamper/wrong-key.
        Never return partial/garbage plaintext."""
```

### 3. `LocalSecretStore` (default provider)

- **Algorithm:** AES-256-GCM via `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
  (verified: `cryptography==48.0.0`; 32-byte key; `encrypt` returns ciphertext **with** the
  16-byte GCM tag appended; `decrypt` raises `cryptography.exceptions.InvalidTag` on tamper or
  wrong key).
- **Key:** 32 raw bytes. Construction takes raw `bytes` (validated to be exactly 32) — key
  *resolution* (env vs DB) is the bootstrap's job (§6), not the store's. This keeps the store a
  pure, DB-free, unit-testable unit.
- **Nonce:** fresh 96-bit `os.urandom(12)` per `encrypt` call (GCM nonce-reuse is catastrophic;
  random 96-bit is safe at our credential-row volume).
- **Ciphertext format:** `v1:<nonce-b64>:<ciphertext+tag-b64>`. `version = "v1"`.
- **Lenient decrypt (legacy passthrough — decided, see §8):** if the input does **not** start
  with `"v1:"`, return it unchanged (it is a pre-encryption plaintext row). If it starts with
  `"v1:"` but fails to parse/authenticate, raise `SecretDecryptionError` (never silently pass a
  corrupt v1 blob through).

```python
# core/secrets/local.py
from __future__ import annotations

import base64
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .mixin import SecretDecryptionError, SecretStoreMixin

_VERSION = "v1"
_NONCE_BYTES = 12
# Any SF provider's versioned envelope ("v1:", "kms-v1:", a future "v2:"). Used to
# distinguish a non-v1 envelope (must fail) from genuine legacy plaintext (passthrough).
_SECRET_ENVELOPE_RE = re.compile(r"^(?:[a-z][a-z0-9]*-)*v[0-9]+:")


class LocalSecretStore(SecretStoreMixin):
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("LocalSecretStore key must be exactly 32 bytes (AES-256)")
        self._aesgcm = AESGCM(key)

    @property
    def version(self) -> str:
        return _VERSION

    async def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return f"{_VERSION}:{base64.b64encode(nonce).decode()}:{base64.b64encode(ct).decode()}"

    async def decrypt(self, ciphertext: str) -> str:
        if ciphertext.startswith(f"{_VERSION}:"):
            try:
                _, nonce_b64, ct_b64 = ciphertext.split(":", 2)
                nonce = base64.b64decode(nonce_b64, validate=True)
                ct = base64.b64decode(ct_b64, validate=True)
                return self._aesgcm.decrypt(nonce, ct, None).decode("utf-8")
            except (ValueError, InvalidTag) as exc:
                raise SecretDecryptionError("failed to decrypt v1 secret blob") from exc
        if _SECRET_ENVELOPE_RE.match(ciphertext):  # e.g. a future "kms-v1:" blob
            raise SecretDecryptionError("non-v1 secret envelope this provider cannot decrypt")
        return ciphertext  # legacy pre-encryption plaintext — see §8
```

> **Foreign-envelope guard (added in review):** decrypt only passes a value through as legacy
> plaintext when it does **not** match `_SECRET_ENVELOPE_RE = re.compile(r"^(?:[a-z][a-z0-9]*-)*v[0-9]+:")`
> — the version-tag namespace of any SF provider (`v1:`, `kms-v1:`, …). A non-v1 *versioned*
> envelope (e.g. a future KMS blob) fails loudly instead of being returned as plaintext. Real
> stored values never match (JSON begins with `{`; `token_urlsafe` secrets contain no `:`).
> Accepted edge: a legacy plaintext value literally beginning `v1:` would be treated as a corrupt
> v1 blob — astronomically unlikely for the values stored here.

### 4. `KMSSecretStore` (stub — ship it so factory dispatch is exercised)

```python
# core/secrets/kms.py
from __future__ import annotations

from .mixin import SecretStoreMixin


class KMSSecretStore(SecretStoreMixin):
    """Extension shape for cloud KMS / Vault providers (NOT implemented in SF-221).

    A real impl performs network I/O in async encrypt/decrypt (AWS KMS Encrypt/Decrypt,
    GCP KMS cryptoKeyVersion, Vault Transit) and stamps 'kms-v1:<payload>' so the storage
    layer can route during rotation.
    """

    @property
    def version(self) -> str:
        return "kms-v1"

    async def encrypt(self, plaintext: str) -> str:
        raise NotImplementedError("KMSSecretStore is a stub — see SF-221 non-goals")

    async def decrypt(self, ciphertext: str) -> str:
        raise NotImplementedError("KMSSecretStore is a stub — see SF-221 non-goals")
```

### 5. Factory + active-store singleton

The factory dispatches on `AIGATEWAY_SECRET_PROVIDER`. Because the local provider's key
resolution touches the DB (auto-gen path), the dispatcher is **async** and is run **once during
the app lifespan** (mirroring `get_or_create_jwt_secret`). The resolved instance is installed as
a process-wide active store; `ORMStore` reads it via a sync accessor. This avoids threading a
`secret_store` argument through the ~8 `ORMStore()` construction sites and the import-time
`app = create_app()`.

```python
# core/secrets/factory.py
from __future__ import annotations

from pydantic import SecretStr

from .local import LocalSecretStore
from .master_key import get_or_create_master_key
from .mixin import SecretStoreMixin

_active: SecretStoreMixin | None = None


# Takes primitives, not the whole Settings object, so core/secrets stays decoupled
# from the app config aggregate (DIP/ISP) and is unit-testable without Settings.
async def build_secret_store(provider: str, env_key: SecretStr | None = None) -> SecretStoreMixin:
    """Dispatch on the provider and resolve its key material."""
    normalized = provider.lower()
    if normalized == "local":
        key = await get_or_create_master_key(env_key)
        return LocalSecretStore(key)
    if normalized == "kms":
        from .kms import KMSSecretStore

        return KMSSecretStore()  # constructs; encrypt/decrypt raise NotImplementedError
    raise RuntimeError(f"Unknown AIGATEWAY_SECRET_PROVIDER={provider!r}")


def set_active_secret_store(store: SecretStoreMixin | None) -> None:
    global _active
    _active = store


def get_active_secret_store() -> SecretStoreMixin:
    if _active is None:
        raise RuntimeError(
            "secret store not initialized — build_secret_store() must run in the app lifespan "
            "before any credential read/write"
        )
    return _active
```

> Note: `build_secret_store` is the spec's `get_secret_store()` (renamed for clarity since it
> now also resolves keys and is async). `get_active_secret_store()` is the runtime accessor.

### 6. Master-key bootstrap (**auto-gen + warn** — decided)

Mirrors `core/auth/jwt_secret.py::get_or_create_jwt_secret`, but writes to its **own sibling
table**, never `credential_blobs` (the master key cannot be encrypted by itself — that is the
circular dependency the sibling table exists to break).

```python
# core/secrets/master_key.py
from __future__ import annotations

import base64
import binascii
import logging
import os

from pydantic import SecretStr
from tortoise.exceptions import IntegrityError

from .models import SecretMasterKey

logger = logging.getLogger(__name__)
_PROVIDER = "local"
_VERSION = "v1"


def _decode_key(b64: str) -> bytes:
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("AIGATEWAY_SECRET_KEY must be valid base64") from exc
    if len(raw) != 32:
        raise RuntimeError("AIGATEWAY_SECRET_KEY must decode to exactly 32 bytes")
    return raw


async def get_or_create_master_key(env_key: SecretStr | None = None) -> bytes:
    """Resolve the 32-byte AES-256 master key.

    Precedence: env (AIGATEWAY_SECRET_KEY) > persisted sibling-table row > auto-generate.
    Auto-generation is a single-worker LOCAL convenience: multi-worker / hosted deployments
    MUST set AIGATEWAY_SECRET_KEY so every worker shares one key.
    """
    if env_key is not None:
        return _decode_key(env_key.get_secret_value())

    existing = await SecretMasterKey.filter(provider=_PROVIDER, version=_VERSION).first()
    if existing is not None:
        return _decode_key(existing.key_material)

    raw = os.urandom(32)
    try:
        await SecretMasterKey.create(
            provider=_PROVIDER, version=_VERSION, key_material=base64.b64encode(raw).decode()
        )
    except IntegrityError:  # concurrent first-boot — re-read the winner
        existing = await SecretMasterKey.get(provider=_PROVIDER, version=_VERSION)
        return _decode_key(existing.key_material)
    logger.warning(
        "Generated and persisted aigateway secret master key (local). "
        "Multi-worker / hosted deployments MUST set AIGATEWAY_SECRET_KEY."
    )
    return raw
```

### 7. New model: `SecretMasterKey`

```python
# core/secrets/models/master_key.py
from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class BaseSecretMasterKey(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    provider = fields.CharField(max_length=32)
    key_material = fields.TextField()  # base64 of 32 raw bytes — LOCAL dev only; env in prod
    version = fields.CharField(max_length=16, default="v1")
    created_at = fields.DatetimeField(auto_now_add=True)


class SecretMasterKey(BaseSecretMasterKey):
    class Meta:
        table = "secret_master_keys"
        unique_together = (("provider", "version"),)  # one active key per provider+version
```

Register in `db.py` `TORTOISE_CONFIG["apps"]["models"]["models"]`:
add `"aigateway.core.secrets.models"` to the list.

### 8. Existing-data handling (**lenient prefix-driven passthrough** — decided)

Existing `credential_blobs` rows hold **plaintext JSON**. We do **not** force a re-encryption
migration. Instead:

- **Reads** are value-prefix driven (`LocalSecretStore.decrypt`, §3): a value not starting with
  `"v1:"` is returned as-is. So a plaintext OAuth token / JWT-secret row keeps working.
- **Writes** always produce `v1:` ciphertext, so each row upgrades to encrypted on its next write
  (token refresh, re-auth, JWT-secret regen). No maintenance window, zero downtime.
- The `ciphertext_version` column is a **write-time annotation** for future rotation tooling,
  **not** the source of truth for decryption — the value prefix is. (This resolves the prior
  draft's §7/§8 contradiction, where the column defaulted to `'v1'` yet a `'v0'` sentinel was
  simultaneously required.) The column is **nullable with no SQL `DEFAULT`**: legacy rows and any
  row created outside `ORMStore.write` are `NULL` (= "pre-encryption / unknown version"), so
  rotation tooling must treat `NULL` as unknown rather than assume `'v1'` (e.g.
  `WHERE ciphertext_version IS NULL OR ciphertext_version != 'vN'`).
- A future one-shot "encrypt all legacy rows + set column accordingly" command is optional and
  out of scope (non-goals).

### 9. Schema migration — **Tortoise built-in (NOT Aerich), file `0005`**

This repo uses **Tortoise 1.1.7 built-in migrations** (`from tortoise import migrations`); there
is no Aerich. The latest migration is `0004_gemini_credential_locator.py`, so the new file is
**`src/aigateway/migrations/0005_secret_store.py`**. Generate with
`uv run tortoise -c aigateway.db.TORTOISE_CONFIG makemigrations --name secret_store` and review,
or hand-author to match `0003`'s style. It performs **two** operations:

```python
# src/aigateway/migrations/0005_secret_store.py
from uuid import uuid4

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0004_gemini_credential_locator")]

    operations = [
        ops.AddField(
            model_name="CredentialBlob",
            name="ciphertext_version",
            # Nullable: ADD COLUMN must be safe on an already-populated table.
            # Tortoise emits no SQL DEFAULT, so existing rows become NULL (not
            # "v1") — exactly the "legacy/unknown version" semantics we want.
            field=fields.CharField(max_length=16, default="v1", null=True),
        ),
        ops.CreateModel(
            name="SecretMasterKey",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("provider", fields.CharField(max_length=32)),
                ("key_material", fields.TextField()),
                ("version", fields.CharField(max_length=16, default="v1")),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={
                "table": "secret_master_keys",
                "app": "models",
                "pk_attr": "id",
                "unique_together": (("provider", "version"),),
            },
            bases=["Model"],
        ),
    ]
```

Also add the field to the model so model ↔ migration agree (verify with `makemigrations` →
"No changes detected"):

```python
# core/credential_blob/model.py — add to BaseCredentialBlob
# null=True so ADD COLUMN is safe on a populated table; default="v1" is ORM-side
# only (no SQL DEFAULT), so legacy/omitted rows are NULL = "unknown version".
ciphertext_version = fields.CharField(max_length=16, null=True, default="v1")
```

(Verified APIs in `tortoise-orm==1.1.7`: `ops.AddField(model_name, name, field)` and
`ops.CreateModel(...)` both exist and match the signatures used here.)

### 10. ORMStore integration (match the **landed** SF-219 API)

The landed `ORMStore` is `class ORMStore:` (no base — `CredentialBlobStore` is a `Protocol`),
uses a race-safe `get` → `create`/`IntegrityError` pattern and `.filter(...).first()`. We keep
that and add encryption. `secret_store` is an **optional injected dependency** (DIP + unit-test
seam); when `None`, it resolves the process-active store **lazily at call time** (never in
`__init__`, so the import-time `ORMStore()` in `create_app` is safe before the DB is up).

```python
# core/credential_blob/store.py
from ..secrets.factory import get_active_secret_store
from ..secrets.mixin import SecretStoreMixin


class ORMStore:
    def __init__(self, secret_store: SecretStoreMixin | None = None) -> None:
        self._secret_store = secret_store

    def _secrets(self) -> SecretStoreMixin:
        return self._secret_store or get_active_secret_store()

    async def read(self, service: str, account: str) -> str | None:
        blob = await CredentialBlob.filter(service=service, account=account).first()
        if blob is None:
            return None
        return await self._secrets().decrypt(blob.value)

    async def write(self, service: str, account: str, value: str) -> None:
        store = self._secrets()
        ciphertext = await store.encrypt(value)
        version = store.version
        try:
            blob = await CredentialBlob.get(service=service, account=account)
        except DoesNotExist:
            try:
                await CredentialBlob.create(
                    service=service, account=account, value=ciphertext, ciphertext_version=version
                )
                return
            except IntegrityError:
                blob = await CredentialBlob.get(service=service, account=account)
        blob.value = ciphertext
        blob.ciphertext_version = version
        await blob.save(update_fields=["value", "ciphertext_version", "updated_at"])

    async def delete(self, service: str, account: str) -> None:
        await CredentialBlob.filter(service=service, account=account).delete()
```

Call sites in plugin auth modules / `profile_index` / `jwt_secret` stay **unchanged**.

### 11. Lifespan + settings wiring

**`main.py` `_lifespan`** — build & install the active secret store **first** (the JWT-secret
bootstrap and provider bootstrap both go through the now-encrypting `ORMStore`), and clear it on
teardown so it does not leak across `TestClient` instances in one process:

```python
from .core.secrets.factory import build_secret_store, set_active_secret_store
...
await init_db(database_url)
try:
    secret_store = await build_secret_store(
        app.state.settings.secret_provider, app.state.settings.secret_key
    )
    set_active_secret_store(secret_store)
    app.state.secret_store = secret_store

    credential_store = app.state.credential_store
    app.state.jwt_secret = await get_or_create_jwt_secret(credential_store, app.state.settings.jwt_secret)
    ...  # admin bootstrap, provider bootstrap (unchanged)
    yield
finally:
    await auth.close_loopback_callbacks(app)
    set_active_secret_store(None)
    await close_db()
```

**`config.py` `Settings`** — two new fields, following the existing `AIGATEWAY_*`
`validation_alias` convention:

```python
secret_key: SecretStr | None = Field(default=None, validation_alias="AIGATEWAY_SECRET_KEY")
secret_provider: str = Field(default="local", validation_alias="AIGATEWAY_SECRET_PROVIDER")

@field_validator("secret_key")
@classmethod
def _validate_secret_key(cls, value: SecretStr | None) -> SecretStr | None:
    if value is None:
        return value
    try:
        raw = base64.b64decode(value.get_secret_value(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("AIGATEWAY_SECRET_KEY must be valid base64") from exc
    if len(raw) != 32:
        raise ValueError("AIGATEWAY_SECRET_KEY must decode to exactly 32 bytes")
    return value

@field_validator("secret_provider")
@classmethod
def _validate_secret_provider(cls, value: str) -> str:
    if value.lower() not in {"local", "kms"}:
        raise ValueError("AIGATEWAY_SECRET_PROVIDER must be 'local' or 'kms'")
    return value.lower()
```

### 12. Security considerations

- **AES-256-GCM, fresh random 96-bit nonce per write, 128-bit tag** → confidentiality + tamper
  detection (validated: tamper and wrong-key both raise `InvalidTag`).
- **The master key is the crown jewel.** Prod: env `AIGATEWAY_SECRET_KEY` (a `SecretStr`, so its
  repr is redacted in logs/tracebacks). Local: a row in `secret_master_keys` in the user-private
  app-data SQLite file. Never logged.
- **Rejected-key leak avoided (review #5):** the key's base64/length is **not** validated in a
  Pydantic field validator — a raising validator lets Pydantic capture the rejected value in the
  `ValidationError` (`input_value=`), and a valid-length key (44 chars) is under Pydantic's 50-char
  truncation, so it would leak in full into startup logs despite `SecretStr`. Validation lives only
  in `master_key._decode_key` (runtime, in the lifespan), which raises a clean `RuntimeError` that
  never echoes the value. (`jwt_secret`/`provisioning_token` validators have the same pre-existing
  pattern — repo-wide follow-up, out of SF-221 scope.)
- **Lost master key ⇒ unrecoverable credentials** (users must re-auth). Documented prominently.
- **Legacy passthrough caveat:** a value that is **not** an SF versioned envelope is returned
  as-is. Safe because all *writes* produce `v1:` — only pre-existing plaintext rows match — but it
  means an attacker who can write arbitrary plaintext into the column is read back verbatim. The
  threat model assumes DB-write access is already a full compromise; mitigated long-term by a
  future re-encrypt sweep. **Foreign-envelope guard (review #6):** a *non-v1 versioned* envelope
  (e.g. a future `kms-v1:` blob) fails loudly via `SecretDecryptionError` rather than passing
  through as plaintext — preventing silent cross-provider format confusion.
- **Future hardening (out of scope):** bind ciphertext to row identity via AES-GCM associated
  data (`aad=f"{service}:{account}"`) to defeat ciphertext row-swap by an attacker with DB-write
  access. Deferred because it changes the port signature (`encrypt` would need row context).

### 13. Env / config summary

| Env var | Required | Default | Notes |
|---|---|---|---|
| `AIGATEWAY_SECRET_KEY` | hosted / multi-worker | auto-gen (local) | base64 of 32 raw bytes; generate with `python -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())'` |
| `AIGATEWAY_SECRET_PROVIDER` | no | `local` | `local` (AES-GCM) or `kms` (stub) |

---

## SOLID / Clean-Architecture / tortoise-dev compliance (requested check)

- **SRP** — `mixin` = encoding contract; `LocalSecretStore` = AES-GCM impl; `master_key` = key
  lifecycle; `factory` = wiring/dispatch; `ORMStore` = row storage. One reason to change each.
- **OCP** — a new provider = implement the port + add one `factory` branch. No edits to
  `ORMStore` or any call site.
- **LSP** — `LocalSecretStore` and `KMSSecretStore` are interchangeable behind the **async** port
  (the async signature is what makes a network KMS substitutable — see §2).
- **ISP** — the port is just `version` + `encrypt` + `decrypt`. No fat interface.
- **DIP** — `ORMStore` (high-level storage) depends on the `SecretStoreMixin` **abstraction**
  (injected or via the active-store accessor), not on a concrete provider.
- **Dependency direction** — everything lives in `core/`; no plugin imports. `core/credential_blob`
  importing `core/secrets` is core→core (allowed). `cryptography` is used only inside the
  `LocalSecretStore` adapter — consistent with how `ORMStore` already wraps Tortoise inside `core`.
- **tortoise-dev rules** — `SecretMasterKey` is model-per-file in a `models/` subpackage, with an
  abstract `BaseSecretMasterKey`, `Meta` first, members ordered Meta → fields. Registered in
  `TORTOISE_CONFIG`. Migration is committed source (Tortoise built-in — repo override of the
  skill's Aerich default, per the repo's existing `0001–0004`).

---

## Tests

New `tests/unit/secrets/` package:

- **`test_local_secret_store.py`** (no DB) — round-trip; output matches `v1:<b64>:<b64>`; two
  encrypts of the same plaintext yield different ciphertext (unique nonce); tamper one byte →
  `SecretDecryptionError`; decrypt with a *different* key → `SecretDecryptionError`; **legacy
  passthrough**: decrypt of `'{"plain":"json"}'` returns it unchanged; `version == "v1"`;
  `LocalSecretStore(b"short")` → `ValueError`.
- **`test_factory.py`** (no DB) — `get_active_secret_store()` before init → `RuntimeError`;
  `set/get_active` round-trips; `build_secret_store` with `provider="kms"` returns a
  `KMSSecretStore` whose `encrypt` raises `NotImplementedError`; unknown provider → `RuntimeError`.
- **`test_master_key.py`** (DB, reuse the `credential_blobs` tmp-DB fixture style) — env-key path
  returns 32 bytes; bad base64 / wrong length → `RuntimeError`; auto-gen persists exactly one row
  and is **stable** across repeated calls (idempotent).
- **Update `tests/unit/test_credential_blob_store.py`** — inject
  `ORMStore(secret_store=LocalSecretStore(TEST_KEY))` in the `orm_store` fixture. The raw probe
  assertion `credential_blobs.read(...) == "updated"` must change: assert the stored value
  **starts with `"v1:"` and is not `"updated"`** (proves no plaintext leak), while
  `await orm_store.read(...) == "updated"`. Add a legacy-row test: `credential_blobs.write(...)`
  a plaintext value directly, then `orm_store.read(...)` returns it unchanged.
- **Update `tests/conftest.py` `client` fixture** — set a fixed
  `AIGATEWAY_SECRET_KEY` (base64 of 32 bytes) so the JWT-secret round-trips deterministically
  through encryption (proves the lifespan ordering: secret store installed before jwt bootstrap).
- **Update `tests/integration/test_tortoise_migration_smoke.py`** — extend the asserted table set
  to include `"secret_master_keys"` (the `<=` subset check still passes for others).

## Docs

- **`apps/aigateway/README.md`** — new "Secrets at rest" section (algorithm, `AIGATEWAY_SECRET_KEY`
  generation one-liner, `AIGATEWAY_SECRET_PROVIDER`, multi-worker/hosted requirement, legacy
  upgrade-on-write behavior) + a "Rotate `AIGATEWAY_SECRET_KEY`" subsection (dual-read strategy is
  deferred; for local, delete the `secret_master_keys` row + restart — and note this invalidates
  all stored credentials).
- **`apps/aigateway/DEPLOYMENT.md`** — add `AIGATEWAY_SECRET_KEY` to the deploy env checklist as
  required for hosted/multi-worker.
- **`apps/aigateway/CLAUDE.md`** — extend the storage policy:
  > Secrets at rest in `credential_blobs` are encrypted via `SecretStoreMixin` (default
  > `LocalSecretStore`, AES-256-GCM). Never write plaintext secrets to `credential_blobs` —
  > always go through `ORMStore`, which encrypts. The only plaintext key material is the master
  > key: env `AIGATEWAY_SECRET_KEY` in prod, or the `secret_master_keys` sibling table in local
  > dev. To add a provider (KMS/Vault/HSM), implement `SecretStoreMixin` and register it in
  > `build_secret_store()`.

## pyproject

Add `cryptography` to runtime deps. The repo pins security-critical libs exactly
(`bcrypt==5.0.0`, `PyJWT==2.12.1`, `asyncpg==0.31.0`); match that convention:

```toml
"cryptography==48.0.0",
```

Run `uv add cryptography==48.0.0` (updates `uv.lock`). Bump on upstream security advisories.

---

## Build sequence

1. **Deps + settings.** `uv add cryptography==48.0.0`. Add `Settings.secret_key` /
   `secret_provider` + validators. Unit-test the validators.
2. **Secrets port + local provider.** `mixin.py`, `local.py`, `kms.py`. Full unit tests (no DB),
   incl. tamper / wrong-key / legacy-passthrough.
3. **Master-key model + bootstrap + factory.** `models/master_key.py`, `master_key.py`,
   `factory.py`. Register model in `db.py`. Write migration `0005_secret_store.py`; run
   `makemigrations` to confirm zero model↔migration drift. DB tests.
4. **ORMStore integration.** Add `ciphertext_version` to the model; wrap encrypt/decrypt + write
   the version column; optional injected `secret_store`. Update `test_credential_blob_store.py`.
5. **Lifespan wiring.** `build_secret_store` + `set_active_secret_store` first in `_lifespan`;
   clear on teardown. Update `conftest.py` `client` fixture. Confirm login still works (JWT secret
   now stored encrypted).
6. **Migration smoke + docs.** Extend the Postgres smoke assertion; write README / DEPLOYMENT /
   CLAUDE.md updates.
7. **Full validation.** `ruff check . && ruff format --check . && pyright && pytest`; offline
   `makemigrations` drift check; SQLite OAuth-flow inspection (below).

## Verification (must pass before merge)

- `cd apps/aigateway && uv run ruff check . && uv run ruff format --check . && uv run pyright`.
- `uv run pytest` — green (unit). `AIGW_TEST_PG=1 uv run pytest -m needs_postgres` if Postgres
  available (migration smoke now also asserts `secret_master_keys`).
- After a fresh OAuth flow: `sqlite3 aigateway.sqlite3 'select value from credential_blobs;'` →
  every freshly-written row begins with `v1:`; no plaintext token strings.
- **Tamper test:** hand-edit one base64 char of a `v1:` value → next read raises
  `SecretDecryptionError` (not silent garbage).
- **Local no-key boot:** unset `AIGATEWAY_SECRET_KEY`, `AIGATEWAY_SECRET_PROVIDER=local` →
  service starts, logs the master-key generation warning once, persists one `secret_master_keys`
  row, and survives a restart (same key, credentials still decrypt). *(Decided behavior: auto-gen
  + warn — NOT "refuse to start".)*
- **KMS dispatch:** `AIGATEWAY_SECRET_PROVIDER=kms` → service starts; any credential read/write
  raises `NotImplementedError` from the stub (proves factory wiring).
- Full SF e2e suite per the team's pre-merge gate.

## Risks

- **Lost master key = lost credentials** (unrecoverable; users re-auth). Mitigation: prominent
  README/CLAUDE.md warning; local auto-gen path persists the key to a known DB row so a wiped
  `.env` does not instantly brick local dev.
- **Lifespan ordering.** The active secret store must be installed before the JWT-secret bootstrap
  and any provider bootstrap (both now go through encrypting `ORMStore`). Enforced by placing
  `build_secret_store` first in `_lifespan`; covered by the `client`-fixture login test.
- **Key-rotation complexity.** Only one version (`v1`) ships; the column + format support future
  rotation, but the dual-read/re-encrypt script is deferred. Document "one rotation at a time".
- **Performance.** AES-GCM ≪1 ms/blob; the in-memory OAuth-token cache already absorbs repeat
  reads. No further change.
- **`uv.lock` churn / image size.** `cryptography` adds ~3 MB. Acceptable.

---

## Appendix A — corrections vs. the prior draft (codebase-validated 2026-06-08)

1. **Aerich → Tortoise built-in migrations.** Repo has no Aerich; migrations are
   `from tortoise import migrations` (see `0001`–`0004`).
2. **Migration `0004` → `0005`.** `0004_gemini_credential_locator.py` already exists.
3. **Sync mixin → async mixin.** Decided: async, for KMS/Vault substitutability.
4. **`v0` column sentinel → value-prefix lenient passthrough.** Removes the prior §7/§8
   contradiction; decryption keys off the self-describing value, not the column.
5. **"Refuse to start in prod" → auto-gen + warn.** No prod-detection flag exists; mirror the
   JWT-secret bootstrap. Prod requirement enforced by docs.
6. **Sync `get_secret_store()`/`from_env()` → async `build_secret_store()` + active-store
   singleton.** Resolves the local-key chicken-and-egg (DB not up at `ORMStore()` construction).
7. **ORMStore API match.** Landed code is `class ORMStore:` with race-safe `get`/`create` +
   `.filter().first()`, not `class ORMStore(CredentialStore)` with `update_or_create`/`get_or_none`.
8. **Master-key sibling table is mandatory + modeled.** `SecretMasterKey` (table
   `secret_master_keys`) is part of migration `0005` and `TORTOISE_CONFIG`, not "optional".

## Appendix B — post-implementation hardening (multi-agent review, 2026-06-08)

A 31-agent adversarial review (8 dimensions → per-finding skeptic verify → completeness critics)
found no critical/high defects. All confirmed findings were low/nit; the following in-scope ones
were fixed and are reflected above:

9. **`build_secret_store(settings)` → `build_secret_store(provider, env_key)`.** Decoupled from
   the `Settings` aggregate (DIP/ISP, DB-free unit-testability).
10. **`ciphertext_version` made `null=True`.** ADD COLUMN must be safe on a populated Postgres
    table; legacy/omitted rows are `NULL` (= unknown version), no SQL `DEFAULT`.
11. **Rejected-key leak fixed (#5).** Removed the `secret_key` Pydantic field validator (which let
    the rejected value leak into `ValidationError.input_value`); validation lives only in runtime
    `_decode_key`. Also collapses the prior config↔master_key DRY duplication.
12. **Foreign-envelope guard (#6).** `LocalSecretStore.decrypt` now raises on a non-v1 SF versioned
    envelope (`_SECRET_ENVELOPE_RE`) instead of returning it as plaintext; genuine legacy plaintext
    still passes through. Accepted edge: legacy plaintext literally starting `v1:` (negligible).
13. **Tests added.** Settings validators; app-level ciphertext-at-rest + JWT-generate-encrypted
    (real lifespan, no `AIGATEWAY_JWT_SECRET`); master-key `IntegrityError` race branch;
    foreign-envelope reject; probe-vs-`LocalSecretStore` format-fidelity guard.

**Deferred (own tickets):** repo-wide `jwt_secret`/`provisioning_token`/`admin_password` validator-leak fix (all three raising `SecretStr` validators echo the rejected value into `ValidationError.input_value`); the
`kms-v1` decode routing when a real KMS provider lands; Helm chart `AIGATEWAY_SECRET_KEY` wiring;
pre-existing `OAuthConnection.account` FK migration drift.

**Mixin naming:** `SecretStoreMixin` is an ABC port, not a behavior mixin; name retained to match
the ticket, with an explicit clarifying docstring note added.