# Superseded By SF-219

This historical plan describes an OS credential-store design for AIGateway. It is superseded by SF-219, which replaces AIGateway runtime credential storage with Tortoise-backed `ORMStore` and the `credential_blobs` table. Do not use this document to reintroduce OS credential storage under `apps/aigateway`.

# AI Gateway profile-based OAuth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `apps/aigateway/` to support multiple per-provider OAuth profiles with editable per-account defaults, replacing SF-138/139's single-identity hardcode.

**Architecture:** A two-layer credential store (`aigateway:index` JSON entry holding profile metadata + defaults, one `aigateway:<provider>:<profile_name>` entry per profile holding tokens). New `/v1/auth/*` endpoints let Electron list profiles, kick off OAuth (gateway returns `authorize_url`), host the callback, edit defaults, and delete profiles. Chat requests select an identity via the `X-Profile` header; gateway looks up the profile, merges its defaults into the OpenAI body where the body omits a field, fetches the (refreshed-if-needed) bearer, and dispatches via `litellm.acompletion`.

**Tech Stack:** Python 3.12 + FastAPI + LiteLLM + httpx + pydantic + the existing `MacOSCredentialStore` / `LinuxCredentialStore` / `WindowsCredentialStore` from SF-139. Tests via pytest + `httpx.MockTransport` for outbound HTTP and a fake `CredentialStore` for storage.

**Spec:** `docs/superpowers/specs/2026-04-30-aigateway-profile-auth-design.md`

**Branch:** `SF-142-aigateway-profile-auth-spec` already exists with the spec doc. Implementation should land on follow-up branches `SF-143-…` onwards (one or more, at the implementer's discretion). All work is local to `apps/aigateway/`; `apps/server/` is untouched.

---

## File structure

### New files

| Path | Responsibility |
|---|---|
| `src/aigateway/core/profile_models.py` | Pydantic `Profile`, `ProfileDefaults`, `ProfileState`, `ProfileIndex` schema models. |
| `src/aigateway/core/profile_index.py` | `ProfileIndexStore`: reads/writes the `aigateway:index` credential store entry under an `asyncio.Lock`. |
| `src/aigateway/core/pending_auth.py` | In-memory `PendingAuthTable` (state → verifier+profile_id) with TTL sweep. |
| `src/aigateway/core/oauth_pkce.py` | `generate_pkce()` returning code_verifier + code_challenge; `generate_state()` returning a CSRF token. |
| `src/aigateway/core/bootstrap.py` | `bootstrap_from_claude_code()`: one-time import of CC credential store entry into the gateway's index + tokens. |
| `src/aigateway/routes/auth.py` | All `/v1/auth/*` endpoints. |
| `src/aigateway/plugins/anthropic_provider/oauth_config.py` | `AUTHORIZE_URL`, `TOKEN_URL`, `SCOPES`, `CLIENT_ID` constants for Anthropic. |

### Modified files

| Path | What changes |
|---|---|
| `src/aigateway/core/plugin_base.py` | `ProviderPluginBase` adds `oauth_config()` (returning provider OAuth metadata) and `oauth_strategy_for(profile_name)` (factory) instead of single-instance `oauth_strategy()`. |
| `src/aigateway/core/oauth_base.py` | `BaseOAuthStrategy.__init__` takes `profile_name`, reads `aigateway:<provider>:<name>` credential store entry (not `Claude Code-credentials`). |
| `src/aigateway/core/errors.py` | New: `ProfileNotFoundError`, `ProfilePendingAuthError`, `BootstrapError`. |
| `src/aigateway/plugins/anthropic_provider/auth.py` | Read/write `aigateway:anthropic:<profile_name>` instead of `Claude Code-credentials`. Add `_exchange_authorization_code()` for the OAuth callback. |
| `src/aigateway/plugins/anthropic_provider/plugin.py` | Implement `oauth_config()` and `oauth_strategy_for(name)`. Drop the cached single-instance `_strategy`. |
| `src/aigateway/routes/chat.py` | Replace fixed-identity auth with `X-Profile` resolution + Bucket-A merge. |
| `src/aigateway/main.py` | Mount `auth` router; run `bootstrap_from_claude_code` on startup. |
| `tests/live/test_anthropic_live.py` | Send `X-Profile: default`. |

### New test files

- `tests/unit/test_profile_index.py`
- `tests/unit/test_pending_auth.py`
- `tests/unit/test_oauth_pkce.py`
- `tests/unit/test_bootstrap.py`
- `tests/unit/test_auth_routes.py`
- `tests/unit/test_chat_x_profile.py`
- `tests/unit/anthropic/test_anthropic_auth.py` — extended; existing tests remain.

### Test helpers

- `tests/conftest.py` — adds a `credential_blobs` fixture (in-memory `CredentialStore` shared across tests) and a `client_with_profiles` fixture that wires that fake into `create_app()`.

---

## Task 1: Profile data models

**Files:**
- Create: `src/aigateway/core/profile_models.py`
- Test: `tests/unit/test_profile_index.py` (test file shared with Task 2)

- [ ] **Step 1.1: Write the failing test for profile model round-trip**

`tests/unit/test_profile_index.py`:

```python
from __future__ import annotations

from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileIndex, ProfileState


def test_profile_round_trips_through_json() -> None:
    p = Profile(
        id="anthropic:default",
        provider="anthropic",
        name="default",
        account_label="user@example.com",
        scopes=["user:inference"],
        last_refreshed_at=None,
        state=ProfileState.AUTHENTICATED,
        defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5", max_tokens=4096),
    )
    raw = p.model_dump_json()
    restored = Profile.model_validate_json(raw)
    assert restored == p


def test_profile_index_serializes_with_version() -> None:
    idx = ProfileIndex(version=1, profiles=[])
    data = idx.model_dump()
    assert data == {"version": 1, "profiles": []}
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_profile_index.py -v
```

Expected: ImportError / ModuleNotFoundError on `aigateway.core.profile_models`.

- [ ] **Step 1.3: Implement `profile_models.py`**

`src/aigateway/core/profile_models.py`:

```python
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProfileState(str, Enum):
    PENDING = "pending"
    AUTHENTICATED = "authenticated"
    ERROR = "error"


class ProfileDefaults(BaseModel):
    """Per-profile fallback values applied when the chat body omits a field."""

    model: str | None = None
    system_prompt: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_seconds: float | None = None
    reasoning_effort: str | None = None  # "low" | "medium" | "high"


class Profile(BaseModel):
    id: str  # f"{provider}:{name}"
    provider: str
    name: str
    account_label: str | None = None
    scopes: list[str] = Field(default_factory=list)
    last_refreshed_at: datetime | None = None
    state: ProfileState = ProfileState.PENDING
    defaults: ProfileDefaults = Field(default_factory=ProfileDefaults)


class ProfileIndex(BaseModel):
    version: int = 1
    profiles: list[Profile] = Field(default_factory=list)
```

- [ ] **Step 1.4: Run test to verify it passes**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_profile_index.py -v
```

Expected: 2 passed.

- [ ] **Step 1.5: Commit**

```bash
git add apps/aigateway/src/aigateway/core/profile_models.py apps/aigateway/tests/unit/test_profile_index.py
git commit -m "feat(SF-143): profile data models for aigateway multi-identity auth"
```

---

## Task 2: ProfileIndexStore (read/write `aigateway:index` credential store entry)

**Files:**
- Create: `src/aigateway/core/profile_index.py`
- Test: `tests/unit/test_profile_index.py` (extend Task 1's file)
- Modify: `tests/conftest.py` (add `credential_blobs` fixture)

- [ ] **Step 2.1: Add the `credential_blobs` fixture**

`tests/conftest.py` (new file if it doesn't exist):

```python
from __future__ import annotations

import pytest

from aigateway.core.credential_store import CredentialStore


class FakeCredentialStore(CredentialStore):
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def read(self, service: str, account: str) -> str | None:
        return self._data.get((service, account))

    def write(self, service: str, account: str, value: str) -> None:
        self._data[(service, account)] = value

    def all(self) -> dict[tuple[str, str], str]:
        return dict(self._data)

    def delete(self, service: str, account: str) -> None:
        self._data.pop((service, account), None)


@pytest.fixture
def credential_blobs() -> FakeCredentialStore:
    return FakeCredentialStore()
```

Also extend `CredentialStore` ABC at `src/aigateway/core/credential_store.py` to require `delete`. Add to each concrete impl:

```python
# In CredentialStore ABC, after `write`:
@abstractmethod
def delete(self, service: str, account: str) -> None: ...

# In MacOSCredentialStore:
def delete(self, service: str, account: str) -> None:
    try:
        result = subprocess.run(
            ["security", "delete-generic-password", "-s", service, "-a", account],
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("`security` command not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"`security delete` timed out for service={service!r}") from exc
    if result.returncode == 44:
        return  # already absent — idempotent
    if result.returncode != 0:
        raise RuntimeError(
            f"`security delete-generic-password` failed exit {result.returncode}: "
            f"{result.stderr.strip() or '<no stderr>'}"
        )

# In LinuxCredentialStore:
def delete(self, service: str, account: str) -> None:
    if shutil.which("secret-tool") is None:
        raise RuntimeError("`secret-tool` not found")
    try:
        subprocess.run(
            ["secret-tool", "clear", "service", service, "account", account],
            check=True, timeout=5, capture_output=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"`secret-tool clear` timed out") from exc
    except subprocess.CalledProcessError:
        return  # idempotent

# In WindowsCredentialStore:
def delete(self, service: str, account: str) -> None:
    keyring = _try_import_keyring()
    if keyring is None:
        raise RuntimeError("Windows credential delete requires `python-keyring`.")
    try:
        keyring.delete_password(service, account)
    except Exception:  # pragma: no cover
        pass  # idempotent — many backends raise on missing entry
```

- [ ] **Step 2.2: Write the failing test for `ProfileIndexStore`**

Append to `tests/unit/test_profile_index.py`:

```python
import pytest

from aigateway.core.profile_index import INDEX_CREDENTIAL_SERVICE, ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileDefaults


@pytest.mark.asyncio
async def test_index_store_returns_empty_index_when_credential store_empty(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs)
    idx = await store.read()
    assert idx.version == 1
    assert idx.profiles == []


@pytest.mark.asyncio
async def test_index_store_round_trip(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs)
    p = Profile(
        id="anthropic:default",
        provider="anthropic",
        name="default",
        defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5"),
    )
    await store.upsert(p)
    idx = await store.read()
    assert len(idx.profiles) == 1
    assert idx.profiles[0].id == "anthropic:default"
    raw = credential_blobs.read(INDEX_CREDENTIAL_SERVICE, "default")
    assert "anthropic:default" in raw


@pytest.mark.asyncio
async def test_index_store_upsert_replaces_by_id(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs)
    await store.upsert(Profile(id="anthropic:default", provider="anthropic", name="default"))
    await store.upsert(Profile(
        id="anthropic:default",
        provider="anthropic",
        name="default",
        account_label="updated@example.com",
    ))
    idx = await store.read()
    assert len(idx.profiles) == 1
    assert idx.profiles[0].account_label == "updated@example.com"


@pytest.mark.asyncio
async def test_index_store_remove(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs)
    await store.upsert(Profile(id="anthropic:default", provider="anthropic", name="default"))
    await store.remove("anthropic:default")
    idx = await store.read()
    assert idx.profiles == []
```

- [ ] **Step 2.3: Run test to verify failure**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_profile_index.py -v
```

Expected: ImportError on `aigateway.core.profile_index`.

- [ ] **Step 2.4: Implement `ProfileIndexStore`**

`src/aigateway/core/profile_index.py`:

```python
from __future__ import annotations

import asyncio
import json
import logging

from .credential_store import CredentialStore, get_credential_store
from .profile_models import Profile, ProfileIndex

logger = logging.getLogger(__name__)

INDEX_CREDENTIAL_SERVICE = "aigateway:index"
_INDEX_ACCOUNT = "default"  # single-tenant; every install has one index


class ProfileIndexStore:
    """Read/write the `aigateway:index` credential store entry under an asyncio.Lock."""

    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store or get_credential_store()
        self._lock = asyncio.Lock()

    async def read(self) -> ProfileIndex:
        raw = await asyncio.to_thread(self._store.read, INDEX_CREDENTIAL_SERVICE, _INDEX_ACCOUNT)
        if raw is None:
            return ProfileIndex()
        return ProfileIndex.model_validate_json(raw)

    async def upsert(self, profile: Profile) -> None:
        async with self._lock:
            idx = await self.read()
            idx.profiles = [p for p in idx.profiles if p.id != profile.id] + [profile]
            await asyncio.to_thread(
                self._store.write,
                INDEX_CREDENTIAL_SERVICE,
                _INDEX_ACCOUNT,
                idx.model_dump_json(),
            )

    async def remove(self, profile_id: str) -> None:
        async with self._lock:
            idx = await self.read()
            idx.profiles = [p for p in idx.profiles if p.id != profile_id]
            await asyncio.to_thread(
                self._store.write,
                INDEX_CREDENTIAL_SERVICE,
                _INDEX_ACCOUNT,
                idx.model_dump_json(),
            )

    async def get(self, provider: str, name: str) -> Profile | None:
        idx = await self.read()
        for p in idx.profiles:
            if p.provider == provider and p.name == name:
                return p
        return None
```

- [ ] **Step 2.5: Run test to verify it passes**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_profile_index.py -v
```

Expected: 6 passed.

- [ ] **Step 2.6: Commit**

```bash
git add apps/aigateway/src/aigateway/core/profile_index.py apps/aigateway/src/aigateway/core/credential_store.py apps/aigateway/tests/unit/test_profile_index.py apps/aigateway/tests/conftest.py
git commit -m "feat(SF-143): profile index credential store with delete capability"
```

---

## Task 3: PKCE + pending-auth helpers

**Files:**
- Create: `src/aigateway/core/oauth_pkce.py`
- Create: `src/aigateway/core/pending_auth.py`
- Test: `tests/unit/test_oauth_pkce.py`
- Test: `tests/unit/test_pending_auth.py`

- [ ] **Step 3.1: Write the failing test for PKCE**

`tests/unit/test_oauth_pkce.py`:

```python
import base64
import hashlib

from aigateway.core.oauth_pkce import generate_pkce, generate_state


def test_pkce_returns_verifier_and_challenge_pair() -> None:
    verifier, challenge = generate_pkce()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


def test_state_is_url_safe_and_unique() -> None:
    a = generate_state()
    b = generate_state()
    assert a != b
    assert len(a) >= 32
    assert all(c.isalnum() or c in "-_" for c in a)
```

- [ ] **Step 3.2: Run to verify failure**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_oauth_pkce.py -v
```

Expected: ImportError.

- [ ] **Step 3.3: Implement `oauth_pkce.py`**

`src/aigateway/core/oauth_pkce.py`:

```python
from __future__ import annotations

import base64
import hashlib
import secrets


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge_S256)."""
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def generate_state() -> str:
    return secrets.token_urlsafe(32)
```

- [ ] **Step 3.4: Run to verify it passes**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_oauth_pkce.py -v
```

Expected: 2 passed.

- [ ] **Step 3.5: Write the failing test for `PendingAuthTable`**

`tests/unit/test_pending_auth.py`:

```python
import time

import pytest

from aigateway.core.pending_auth import PendingAuthEntry, PendingAuthTable


def test_pending_table_round_trip() -> None:
    table = PendingAuthTable(ttl_seconds=600)
    table.put("state-1", PendingAuthEntry(profile_id="anthropic:work", code_verifier="v"))
    entry = table.pop("state-1")
    assert entry is not None
    assert entry.profile_id == "anthropic:work"
    assert entry.code_verifier == "v"


def test_pop_consumes_entry() -> None:
    table = PendingAuthTable(ttl_seconds=600)
    table.put("state-1", PendingAuthEntry(profile_id="anthropic:work", code_verifier="v"))
    table.pop("state-1")
    assert table.pop("state-1") is None  # second pop is a miss


def test_expired_entry_is_swept(monkeypatch) -> None:
    fake = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: fake["now"])
    table = PendingAuthTable(ttl_seconds=10)
    table.put("state-1", PendingAuthEntry(profile_id="anthropic:work", code_verifier="v"))
    fake["now"] = 1100.0  # 100s later
    assert table.pop("state-1") is None


def test_unknown_state_returns_none() -> None:
    table = PendingAuthTable(ttl_seconds=600)
    assert table.pop("nonexistent") is None
```

- [ ] **Step 3.6: Run to verify failure**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_pending_auth.py -v
```

Expected: ImportError.

- [ ] **Step 3.7: Implement `pending_auth.py`**

`src/aigateway/core/pending_auth.py`:

```python
from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class PendingAuthEntry:
    profile_id: str
    code_verifier: str


class PendingAuthTable:
    """In-memory CSRF-state store for pending OAuth flows. TTL-bounded."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[PendingAuthEntry, float]] = {}

    def put(self, state: str, entry: PendingAuthEntry) -> None:
        self._entries[state] = (entry, time.monotonic())

    def pop(self, state: str) -> PendingAuthEntry | None:
        item = self._entries.pop(state, None)
        if item is None:
            return None
        entry, ts = item
        if time.monotonic() - ts > self._ttl:
            return None
        return entry
```

- [ ] **Step 3.8: Run to verify it passes**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_pending_auth.py -v
```

Expected: 4 passed.

- [ ] **Step 3.9: Commit**

```bash
git add apps/aigateway/src/aigateway/core/oauth_pkce.py apps/aigateway/src/aigateway/core/pending_auth.py apps/aigateway/tests/unit/test_oauth_pkce.py apps/aigateway/tests/unit/test_pending_auth.py
git commit -m "feat(SF-143): PKCE + pending-auth table helpers"
```

---

## Task 4: Refactor `ProviderPluginBase` for multi-profile + OAuth config

**Files:**
- Modify: `src/aigateway/core/plugin_base.py`
- Modify: `src/aigateway/core/errors.py`
- Test: `tests/unit/test_registry.py` (extend)

- [ ] **Step 4.1: Add new error types**

Append to `src/aigateway/core/errors.py`:

```python
class ProfileNotFoundError(AigwError):
    """No profile found for the given (provider, name)."""


class ProfilePendingAuthError(AigwError):
    """Profile exists but is still in 'pending' state — auth not complete."""


class BootstrapError(AigwError):
    """Failed to bootstrap the gateway profile index from an existing CC credential store."""
```

- [ ] **Step 4.2: Write failing test extending `ProviderPluginBase` contract**

Append to `tests/unit/test_registry.py`:

```python
from dataclasses import dataclass


def test_provider_plugin_base_exposes_oauth_config() -> None:
    """Plugins now declare OAuth provider metadata so the gateway can
    dispatch start/callback without per-provider knowledge in the routes."""
    from aigateway.core.plugin_base import OAuthConfig, ProviderPluginBase

    class P(ProviderPluginBase):
        custom_llm_provider = "stub"

        def register_models(self):
            return []

        def oauth_config(self):
            return OAuthConfig(
                authorize_url="https://stub.example/authorize",
                token_url="https://stub.example/token",
                client_id="cid",
                scopes=["s1"],
                redirect_path="/v1/auth/stub/callback",
            )

    cfg = P().oauth_config()
    assert cfg.authorize_url == "https://stub.example/authorize"
    assert cfg.scopes == ["s1"]


def test_provider_plugin_base_strategy_factory() -> None:
    """oauth_strategy_for(profile_name) returns a per-profile strategy."""
    from aigateway.core.plugin_base import OAuthStrategy, ProviderPluginBase

    class FakeStrat(OAuthStrategy):
        def __init__(self, profile_name: str) -> None:
            self.profile_name = profile_name

        async def get_authorization_header(self):
            return {"Authorization": f"Bearer tok-{self.profile_name}"}

    class P(ProviderPluginBase):
        custom_llm_provider = "stub"

        def register_models(self):
            return []

        def oauth_strategy_for(self, profile_name: str):
            return FakeStrat(profile_name)

    a = P().oauth_strategy_for("work")
    b = P().oauth_strategy_for("personal")
    assert isinstance(a, FakeStrat)
    assert a.profile_name == "work"
    assert b.profile_name == "personal"
```

- [ ] **Step 4.3: Run to verify failure**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_registry.py -v
```

Expected: failures on `OAuthConfig` import and `oauth_strategy_for`.

- [ ] **Step 4.4: Update `plugin_base.py`**

Replace the bottom of `src/aigateway/core/plugin_base.py` (keep `ModelEntry` and `OAuthStrategy` ABC; replace `ProviderPluginBase`):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class OAuthConfig:
    """Provider-level OAuth metadata used to drive the start + callback flow."""

    authorize_url: str
    token_url: str
    client_id: str
    scopes: list[str]
    redirect_path: str  # absolute path on the gateway, e.g. /v1/auth/anthropic/callback
    extra_authorize_params: dict[str, str] | None = None


class ProviderPluginBase(ABC):
    custom_llm_provider: str

    @abstractmethod
    def register_models(self) -> list[ModelEntry]:
        ...

    def oauth_config(self) -> OAuthConfig | None:
        """Return provider OAuth metadata, or None for no-auth providers (e.g. local Ollama)."""
        return None

    def oauth_strategy_for(self, profile_name: str) -> OAuthStrategy | None:
        """Return a per-profile OAuthStrategy. Default: no auth."""
        return None

    def auth_router(self):
        """Provider-specific auth routes. Default: handled by the shared `routes/auth.py`."""
        return None
```

Remove the previous `oauth_strategy()` (no-arg) method.

- [ ] **Step 4.5: Update existing tests that referenced the removed `oauth_strategy()`**

Search and update: in `tests/unit/test_registry.py` (the original tests), find:

```python
def oauth_strategy(self) -> OAuthStrategy | None:
    return _FakeStrategy()
```

Replace with:

```python
def oauth_strategy_for(self, profile_name: str) -> OAuthStrategy | None:
    return _FakeStrategy()
```

(Or whatever the matching test currently has — adjust the existing fake plugin definitions consistently.)

- [ ] **Step 4.6: Run to verify it passes**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_registry.py -v
```

Expected: all pass (existing + 2 new).

- [ ] **Step 4.7: Commit**

```bash
git add apps/aigateway/src/aigateway/core/plugin_base.py apps/aigateway/src/aigateway/core/errors.py apps/aigateway/tests/unit/test_registry.py
git commit -m "feat(SF-143): ProviderPluginBase contract for multi-profile OAuth"
```

---

## Task 5: Refactor `BaseOAuthStrategy` and `AnthropicOAuth` for per-profile entries

**Files:**
- Modify: `src/aigateway/core/oauth_base.py`
- Modify: `src/aigateway/plugins/anthropic_provider/auth.py`
- Create: `src/aigateway/plugins/anthropic_provider/oauth_config.py`
- Modify: `src/aigateway/plugins/anthropic_provider/plugin.py`
- Modify: `tests/unit/anthropic/test_anthropic_auth.py`

- [ ] **Step 5.1: Write the failing test — anthropic auth keyed by profile name**

Replace the body of `tests/unit/anthropic/test_anthropic_auth.py` to use the new credential store key. Update the helper:

```python
# Replace test_credential_service_constant (used to assert "Claude Code-credentials")
@pytest.mark.asyncio
async def test_credential_service_uses_aigateway_namespace() -> None:
    """Profiles are stored under aigateway:anthropic:<name>, not Claude Code's credential store."""
    from aigateway.plugins.anthropic_provider.auth import credential_service_for
    assert credential_service_for("default") == "aigateway:anthropic:default"
    assert credential_service_for("work") == "aigateway:anthropic:work"
```

Update each existing test that constructs `AnthropicOAuth(...)` to pass `profile_name="default"`. Pattern:

```python
strat = AnthropicOAuth(
    profile_name="default",
    credential_store=_FakeStore(payload=...),
    account="alice",
)
```

The fake store now needs to respond to the `aigateway:anthropic:default` service. Update `_FakeStore.read` if it's currently keyed naively:

```python
class _FakeStore(CredentialStore):
    def __init__(self, payload: str | None = None) -> None:
        self.payload = payload
        self.writes: list[tuple[str, str, str]] = []

    def read(self, service: str, account: str) -> str | None:
        # Single payload, served regardless of service+account — fine for these unit tests.
        return self.payload

    def write(self, service: str, account: str, value: str) -> None:
        self.writes.append((service, account, value))
        self.payload = value

    def delete(self, service: str, account: str) -> None:
        self.payload = None
```

Also: token write payload no longer wraps in `{"claudeAiOauth": ...}` — it's a flat object. Update the helper:

```python
def _wrap(creds: dict) -> str:
    """Token payload as stored in aigateway:anthropic:<name>."""
    return json.dumps(creds)


def _fresh_creds(expires_in_ms: int = 3_600_000) -> dict:
    return {
        "access_token": "tok-fresh",
        "refresh_token": "rt-1",
        "expires_at_ms": int(time.time() * 1000) + expires_in_ms,
        "token_type": "Bearer",
    }
```

(Note: snake_case + `_ms` suffix — the spec's flat token shape.)

The `test_expired_credential_triggers_refresh` test assertion changes:

```python
assert len(store.writes) == 1
written = json.loads(store.writes[0][2])
assert written["access_token"] == "tok-new"
assert written["refresh_token"] == "rt-2"
```

(No more `claudeAiOauth` wrapper.)

- [ ] **Step 5.2: Run to verify failures**

```bash
cd apps/aigateway && uv run pytest tests/unit/anthropic/test_anthropic_auth.py -v
```

Expected: failures on `credential_service_for` import and tests asserting new shapes.

- [ ] **Step 5.3: Update `BaseOAuthStrategy` to take `profile_name` and expose helpers**

Modify `src/aigateway/core/oauth_base.py`:

```python
class BaseOAuthStrategy(OAuthStrategy):
    refresh_window_seconds: int = 60

    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        self._cached: dict | None = None
        self._lock = asyncio.Lock()

    @abstractmethod
    def credential_service(self) -> str:
        """Return the OS credential store `service` string for this profile's tokens.

        Used by the auth routes to delete tokens on profile delete and to
        write tokens after the OAuth callback exchange. Provider plugins
        override (e.g. Anthropic returns f"aigateway:anthropic:{profile_name}").
        """

    @abstractmethod
    def credential_account(self) -> str:
        """Return the OS credential store `account` string for this profile's tokens."""

    def set_credentials(self, creds: dict) -> None:
        """Store a credential blob (used after callback's code-for-token exchange)."""
        self._cached = creds
        self._write_to_store(creds)

    async def refresh(self) -> None:
        async with self._lock:
            if self._cached is None:
                self._cached = self._read_credential()
            self._cached = await self._refresh_credential(self._cached)

    # ... rest unchanged (get_authorization_header, _read_credential, _is_expired,
    # _refresh_credential, _build_headers, _header_override, _write_to_store)
```

Remove the previous no-arg `__init__`. Subclasses (`AnthropicOAuth`) must implement
`credential_service()`, `credential_account()`, and `_write_to_store()`.

- [ ] **Step 5.4: Create anthropic OAuth config constants**

`src/aigateway/plugins/anthropic_provider/oauth_config.py`:

```python
from __future__ import annotations

ANTHROPIC_AUTHORIZE_URL = "https://console.anthropic.com/oauth/authorize"
ANTHROPIC_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # public Claude Code OAuth app
ANTHROPIC_SCOPES = ["user:inference", "user:profile"]
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_BETA = ",".join(
    [
        "claude-code-20250219",
        "oauth-2025-04-20",
        "interleaved-thinking-2025-05-14",
        "prompt-caching-scope-2026-01-05",
    ]
)
ANTHROPIC_REDIRECT_PATH = "/v1/auth/anthropic/callback"
```

- [ ] **Step 5.5: Refactor `auth.py` to use per-profile credential store**

`src/aigateway/plugins/anthropic_provider/auth.py`:

```python
"""Anthropic OAuth strategy keyed by profile name.

Each profile has its own credential store entry under
`aigateway:anthropic:<profile_name>`. The token blob is the flat shape
defined in the spec (snake_case keys; expires_at_ms in milliseconds).
"""

from __future__ import annotations

import json
import logging
import os
import time

import httpx

from aigateway.core.credential_store import CredentialStore, get_credential_store
from aigateway.core.errors import AuthError, CredentialNotFoundError
from aigateway.core.oauth_base import BaseOAuthStrategy

from .oauth_config import (
    ANTHROPIC_BETA,
    ANTHROPIC_CLIENT_ID,
    ANTHROPIC_TOKEN_URL,
    ANTHROPIC_VERSION,
)

logger = logging.getLogger(__name__)


def credential_service_for(profile_name: str) -> str:
    return f"aigateway:anthropic:{profile_name}"


_ACCOUNT = "default"  # single account inside each provider credential store entry


class AnthropicOAuth(BaseOAuthStrategy):
    def __init__(
        self,
        profile_name: str,
        *,
        credential_store: CredentialStore | None = None,
        account: str | None = None,
        http_client_factory=None,
    ) -> None:
        super().__init__(profile_name=profile_name)
        self._store = credential_store or get_credential_store()
        # `account` retained for ergonomics (unused inside aigateway-namespaced entries).
        self._account = account if account is not None else _ACCOUNT
        self._http_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        )

    def credential_service(self) -> str:
        return credential_service_for(self.profile_name)

    def credential_account(self) -> str:
        return self._account

    def _read_credential(self) -> dict:
        raw = self._store.read(self.credential_service(), self.credential_account())
        if raw is None:
            raise CredentialNotFoundError(
                f"No tokens for anthropic profile {self.profile_name!r}. Re-authenticate via Electron."
            )
        try:
            creds = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthError(f"Token blob for {self.profile_name!r} is not valid JSON: {exc}") from exc
        for key in ("access_token", "refresh_token", "expires_at_ms"):
            if key not in creds:
                raise AuthError(f"Token blob missing required field {key!r}")
        return creds

    def _is_expired(self, creds: dict) -> bool:
        return time.time() * 1000 >= creds["expires_at_ms"] - (self.refresh_window_seconds * 1000)

    def _build_headers(self, creds: dict) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {creds['access_token']}",
            "anthropic-version": ANTHROPIC_VERSION,
            "anthropic-beta": ANTHROPIC_BETA,
        }

    async def _refresh_credential(self, creds: dict) -> dict:
        body = {
            "grant_type": "refresh_token",
            "refresh_token": creds["refresh_token"],
            "client_id": ANTHROPIC_CLIENT_ID,
        }
        try:
            async with self._http_factory() as client:
                resp = await client.post(
                    ANTHROPIC_TOKEN_URL,
                    json=body,
                    headers={"content-type": "application/json"},
                )
        except httpx.RequestError as exc:
            raise AuthError(f"Refresh endpoint unreachable: {exc}") from exc

        if resp.status_code == 401:
            raise AuthError(
                f"Refresh returned 401 for profile {self.profile_name!r}. Re-auth required."
            )
        if resp.status_code != 200:
            raise AuthError(
                f"OAuth refresh failed status {resp.status_code}: {resp.text[:500]}"
            )
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise AuthError(f"OAuth refresh response not JSON: {exc}") from exc

        new_creds = self._convert_refresh_response(data)
        self._write_to_store(new_creds)
        return new_creds

    def _convert_refresh_response(self, data: dict) -> dict:
        for required in ("access_token", "refresh_token", "expires_in"):
            if required not in data:
                raise AuthError(f"OAuth refresh response missing {required!r}")
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at_ms": int((time.time() + int(data["expires_in"])) * 1000),
            "token_type": data.get("token_type", "Bearer"),
        }

    def _write_to_store(self, creds: dict) -> None:
        self._store.write(self.credential_service(), self.credential_account(), json.dumps(creds))


async def exchange_authorization_code(
    code: str,
    code_verifier: str,
    *,
    http_client_factory=None,
) -> dict:
    """Exchange an authorization code for tokens. Used by the OAuth callback handler."""
    factory = http_client_factory or (lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0)))
    async with factory() as client:
        resp = await client.post(
            ANTHROPIC_TOKEN_URL,
            json={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "client_id": ANTHROPIC_CLIENT_ID,
            },
            headers={"content-type": "application/json"},
        )
    if resp.status_code != 200:
        raise AuthError(
            f"Authorization code exchange failed status {resp.status_code}: {resp.text[:500]}"
        )
    data = resp.json()
    for required in ("access_token", "refresh_token", "expires_in"):
        if required not in data:
            raise AuthError(f"Authorization code response missing {required!r}")
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at_ms": int((time.time() + int(data["expires_in"])) * 1000),
        "token_type": data.get("token_type", "Bearer"),
    }
```

- [ ] **Step 5.6: Update `plugin.py` to expose OAuth config and strategy factory**

`src/aigateway/plugins/anthropic_provider/plugin.py`:

```python
from __future__ import annotations

from aigateway.core.plugin_base import (
    ModelEntry,
    OAuthConfig,
    OAuthStrategy,
    ProviderPluginBase,
)

from .auth import AnthropicOAuth
from .models import MODELS
from .oauth_config import (
    ANTHROPIC_AUTHORIZE_URL,
    ANTHROPIC_CLIENT_ID,
    ANTHROPIC_REDIRECT_PATH,
    ANTHROPIC_SCOPES,
    ANTHROPIC_TOKEN_URL,
)


class AnthropicProviderPlugin(ProviderPluginBase):
    custom_llm_provider = "anthropic"

    def register_models(self) -> list[ModelEntry]:
        return list(MODELS)

    def oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            authorize_url=ANTHROPIC_AUTHORIZE_URL,
            token_url=ANTHROPIC_TOKEN_URL,
            client_id=ANTHROPIC_CLIENT_ID,
            scopes=ANTHROPIC_SCOPES,
            redirect_path=ANTHROPIC_REDIRECT_PATH,
        )

    def oauth_strategy_for(self, profile_name: str) -> OAuthStrategy:
        return AnthropicOAuth(profile_name=profile_name)


PLUGIN = AnthropicProviderPlugin()
```

- [ ] **Step 5.7: Run anthropic tests**

```bash
cd apps/aigateway && uv run pytest tests/unit/anthropic/ -v
```

Expected: all pass (the rewritten test file).

- [ ] **Step 5.8: Run all unit tests to confirm no regressions**

```bash
cd apps/aigateway && uv run pytest -m "not live" -v
```

Expected: all pass.

- [ ] **Step 5.9: Commit**

```bash
git add apps/aigateway/src/aigateway/core/oauth_base.py apps/aigateway/src/aigateway/plugins/anthropic_provider/ apps/aigateway/tests/unit/anthropic/
git commit -m "feat(SF-143): per-profile credential store entries + auth code exchange"
```

---

## Task 6: Bootstrap from Claude Code credential store

**Files:**
- Create: `src/aigateway/core/bootstrap.py`
- Create: `tests/unit/test_bootstrap.py`

- [ ] **Step 6.1: Write the failing test**

`tests/unit/test_bootstrap.py`:

```python
import json
import time

import pytest

from aigateway.core.bootstrap import bootstrap_from_claude_code
from aigateway.core.profile_index import INDEX_CREDENTIAL_SERVICE, ProfileIndexStore
from aigateway.plugins.anthropic_provider.auth import credential_service_for


CC_SERVICE = "Claude Code-credentials"


@pytest.mark.asyncio
async def test_bootstrap_imports_cc_default_when_index_empty(credential_blobs) -> None:
    cc_payload = json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": "cc-tok",
                "refreshToken": "cc-rt",
                "expiresAt": int(time.time() * 1000) + 3_600_000,
                "scopes": ["user:inference"],
            }
        }
    )
    credential_blobs.write(CC_SERVICE, "alice", cc_payload)

    await bootstrap_from_claude_code(
        credential_store=credential_blobs,
        index_store=ProfileIndexStore(credential_store=credential_blobs),
        cc_account="alice",
    )

    aigw_payload = credential_blobs.read(credential_service_for("default"), "default")
    assert aigw_payload is not None
    converted = json.loads(aigw_payload)
    assert converted["access_token"] == "cc-tok"
    assert converted["refresh_token"] == "cc-rt"
    assert "expires_at_ms" in converted

    idx_raw = credential_blobs.read(INDEX_CREDENTIAL_SERVICE, "default")
    assert idx_raw is not None
    assert "anthropic:default" in idx_raw

    # CC entry untouched
    assert credential_blobs.read(CC_SERVICE, "alice") == cc_payload


@pytest.mark.asyncio
async def test_bootstrap_noop_when_index_already_exists(credential_blobs) -> None:
    credential_blobs.write(INDEX_CREDENTIAL_SERVICE, "default", '{"version":1,"profiles":[]}')
    credential_blobs.write(
        CC_SERVICE,
        "alice",
        json.dumps({"claudeAiOauth": {"accessToken": "x", "refreshToken": "y", "expiresAt": 1}}),
    )
    await bootstrap_from_claude_code(
        credential_store=credential_blobs,
        index_store=ProfileIndexStore(credential_store=credential_blobs),
        cc_account="alice",
    )
    assert credential_blobs.read(credential_service_for("default"), "default") is None


@pytest.mark.asyncio
async def test_bootstrap_noop_when_cc_entry_missing(credential_blobs) -> None:
    await bootstrap_from_claude_code(
        credential_store=credential_blobs,
        index_store=ProfileIndexStore(credential_store=credential_blobs),
        cc_account="alice",
    )
    assert credential_blobs.read(INDEX_CREDENTIAL_SERVICE, "default") is None
```

- [ ] **Step 6.2: Run to verify failure**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_bootstrap.py -v
```

Expected: ImportError on `aigateway.core.bootstrap`.

- [ ] **Step 6.3: Implement bootstrap**

`src/aigateway/core/bootstrap.py`:

```python
"""One-time import of Claude Code's credential store entry into the gateway's index.

Runs on FastAPI startup. If the gateway has no profile index yet but the
Claude Code CLI has stored credentials on this machine, copy the token
blob into the gateway's per-profile namespace (`aigateway:anthropic:default`)
and seed an index with one `anthropic:default` profile in the
`authenticated` state. The original Claude Code entry is left in place.

Idempotent: if the gateway index already exists, this function is a no-op.
"""

from __future__ import annotations

import json
import logging
import os
import time

from aigateway.core.credential_store import CredentialStore, get_credential_store
from aigateway.core.errors import BootstrapError
from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileState
from aigateway.plugins.anthropic_provider.auth import credential_service_for

logger = logging.getLogger(__name__)

CLAUDE_CODE_SERVICE = "Claude Code-credentials"


async def bootstrap_from_claude_code(
    credential_store: CredentialStore | None = None,
    index_store: ProfileIndexStore | None = None,
    cc_account: str | None = None,
) -> None:
    store = credential_store or get_credential_store()
    idx = index_store or ProfileIndexStore(credential_store=store)
    account = cc_account if cc_account is not None else os.environ.get("USER", "")

    existing = await idx.read()
    if existing.profiles:
        logger.debug("bootstrap: gateway index already populated; skipping")
        return

    cc_raw = store.read(CLAUDE_CODE_SERVICE, account)
    if cc_raw is None:
        logger.info("bootstrap: no Claude Code credential store entry found; nothing to import")
        return

    try:
        outer = json.loads(cc_raw)
        cc_creds = outer["claudeAiOauth"]
        converted = {
            "access_token": cc_creds["accessToken"],
            "refresh_token": cc_creds["refreshToken"],
            "expires_at_ms": int(cc_creds["expiresAt"]),
            "token_type": "Bearer",
        }
    except (KeyError, ValueError, TypeError) as exc:
        raise BootstrapError(
            f"Claude Code credential store entry has unexpected shape: {exc}"
        ) from exc

    store.write(
        credential_service_for("default"),
        "default",
        json.dumps(converted),
    )
    profile = Profile(
        id="anthropic:default",
        provider="anthropic",
        name="default",
        scopes=cc_creds.get("scopes", []),
        state=ProfileState.AUTHENTICATED,
        defaults=ProfileDefaults(),
    )
    await idx.upsert(profile)
    logger.info("bootstrap: imported Claude Code creds into anthropic:default")
```

- [ ] **Step 6.4: Run to verify it passes**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_bootstrap.py -v
```

Expected: 3 passed.

- [ ] **Step 6.5: Commit**

```bash
git add apps/aigateway/src/aigateway/core/bootstrap.py apps/aigateway/tests/unit/test_bootstrap.py
git commit -m "feat(SF-143): bootstrap gateway profile from Claude Code credential store"
```

---

## Task 7: Auth routes — list + get profile

**Files:**
- Create: `src/aigateway/routes/auth.py`
- Create: `tests/unit/test_auth_routes.py`
- Modify: `src/aigateway/main.py`

- [ ] **Step 7.1: Write failing test**

`tests/unit/test_auth_routes.py`:

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileState
from aigateway.main import create_app


@pytest.fixture
def client_with_index(credential_blobs, monkeypatch):
    """Patch the global credential store so create_app() picks up our fake."""
    from aigateway.core import credential_store as cs_module

    monkeypatch.setattr(cs_module, "get_credential_store", lambda: credential_blobs)
    # Also patch the bootstrap import path to use the fake
    from aigateway.core import bootstrap as bs_module

    monkeypatch.setattr(bs_module, "get_credential_store", lambda: credential_blobs)

    app = create_app()
    return TestClient(app), credential_blobs


@pytest.mark.asyncio
async def test_list_profiles_empty(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.get("/v1/auth/profiles")
    assert resp.status_code == 200
    assert resp.json() == {"profiles": []}


@pytest.mark.asyncio
async def test_list_profiles_returns_seeded(credential_blobs) -> None:
    idx = ProfileIndexStore(credential_store=credential_blobs)
    await idx.upsert(
        Profile(
            id="anthropic:default",
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5"),
        )
    )

    from aigateway.core import credential_store as cs_module
    cs_module.get_credential_store = lambda: credential_blobs  # type: ignore
    from aigateway.core import bootstrap as bs_module
    bs_module.get_credential_store = lambda: credential_blobs  # type: ignore

    app = create_app()
    client = TestClient(app)

    resp = client.get("/v1/auth/profiles")
    body = resp.json()
    assert resp.status_code == 200
    assert len(body["profiles"]) == 1
    assert body["profiles"][0]["id"] == "anthropic:default"
    # tokens never appear in this listing
    assert "access_token" not in str(body)
```

- [ ] **Step 7.2: Run to verify failure**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_auth_routes.py -v
```

Expected: 404 (no `/v1/auth/profiles` route yet).

- [ ] **Step 7.3: Implement `routes/auth.py`**

`src/aigateway/routes/auth.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core.profile_index import ProfileIndexStore

router = APIRouter()


def _index_store(request: Request) -> ProfileIndexStore:
    return request.app.state.profile_index


@router.get("/v1/auth/profiles")
async def list_profiles(request: Request) -> dict:
    idx = await _index_store(request).read()
    return {"profiles": [p.model_dump(mode="json") for p in idx.profiles]}


@router.get("/v1/auth/{provider}/profiles")
async def list_provider_profiles(provider: str, request: Request) -> dict:
    idx = await _index_store(request).read()
    return {
        "profiles": [
            p.model_dump(mode="json") for p in idx.profiles if p.provider == provider
        ]
    }


@router.get("/v1/auth/{provider}/profiles/{name}")
async def get_profile(provider: str, name: str, request: Request) -> dict:
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "profile_not_found", "provider": provider, "name": name},
        )
    return p.model_dump(mode="json")
```

- [ ] **Step 7.4: Mount auth router + attach `profile_index` to app state**

Modify `src/aigateway/main.py`:

```python
from .core.profile_index import ProfileIndexStore
# ...
from .routes import auth, chat, health, models  # add auth

# inside create_app(), after registry setup:
app.state.profile_index = ProfileIndexStore()

# include the router after the existing include_router calls:
app.include_router(auth.router)
```

- [ ] **Step 7.5: Run tests to verify pass**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_auth_routes.py -v
```

Expected: 2 passed.

- [ ] **Step 7.6: Commit**

```bash
git add apps/aigateway/src/aigateway/routes/auth.py apps/aigateway/src/aigateway/main.py apps/aigateway/tests/unit/test_auth_routes.py
git commit -m "feat(SF-143): GET /v1/auth/profiles + per-provider listing"
```

---

## Task 8: Auth routes — start OAuth + callback

**Files:**
- Modify: `src/aigateway/routes/auth.py`
- Modify: `src/aigateway/main.py`
- Modify: `tests/unit/test_auth_routes.py` (extend)

- [ ] **Step 8.1: Write failing test for `POST /v1/auth/{provider}/profiles`**

Append to `tests/unit/test_auth_routes.py`:

```python
def test_start_oauth_returns_authorize_url(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.post(
        "/v1/auth/anthropic/profiles",
        json={"name": "work"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["profile_id"] == "anthropic:work"
    assert body["authorize_url"].startswith("https://console.anthropic.com/oauth/authorize")
    assert "state=" in body["authorize_url"]
    assert "code_challenge=" in body["authorize_url"]
    assert "code_challenge_method=S256" in body["authorize_url"]


def test_start_oauth_for_unknown_provider_404(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.post("/v1/auth/ghost/profiles", json={"name": "x"})
    assert resp.status_code == 404


def test_start_oauth_creates_pending_profile(client_with_index) -> None:
    client, _ = client_with_index
    client.post("/v1/auth/anthropic/profiles", json={"name": "work"})
    resp = client.get("/v1/auth/anthropic/profiles/work")
    assert resp.status_code == 200
    assert resp.json()["state"] == "pending"
```

Also test the callback. We need to mock the token exchange so the test doesn't actually hit Anthropic. Add a fixture and test:

```python
import httpx
from aigateway.plugins.anthropic_provider import auth as anthropic_auth_module


def test_callback_completes_auth(client_with_index, monkeypatch) -> None:
    client, credential_blobs = client_with_index

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "new-tok",
                "refresh_token": "new-rt",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    transport = httpx.MockTransport(mock_handler)

    def factory():
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))

    monkeypatch.setattr(
        anthropic_auth_module,
        "exchange_authorization_code",
        lambda code, code_verifier: anthropic_auth_module.exchange_authorization_code.__wrapped__(
            code, code_verifier, http_client_factory=factory
        )
        if False
        else _wrap_exchange(code, code_verifier, factory),
    )

    # Simpler approach: just monkeypatch the underlying http factory used by routes/auth.py.
    # We'll wire it via app.state.
    client.app.state.anthropic_http_factory = factory  # type: ignore

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "work"})
    state = start.json()["state"]

    cb = client.get(
        "/v1/auth/anthropic/callback",
        params={"code": "auth-code-1", "state": state},
        follow_redirects=False,
    )
    assert cb.status_code == 200

    # Profile flipped
    prof = client.get("/v1/auth/anthropic/profiles/work").json()
    assert prof["state"] == "authenticated"

    # Tokens written
    from aigateway.plugins.anthropic_provider.auth import credential_service_for
    blob = credential_blobs.read(credential_service_for("work"), "default")
    assert "new-tok" in blob


async def _wrap_exchange(code, code_verifier, factory):
    return await anthropic_auth_module.exchange_authorization_code(
        code, code_verifier, http_client_factory=factory
    )


def test_callback_with_unknown_state_400(client_with_index) -> None:
    client, _ = client_with_index
    resp = client.get(
        "/v1/auth/anthropic/callback",
        params={"code": "x", "state": "never-issued"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 8.2: Run to verify failures**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_auth_routes.py -v
```

Expected: failures on missing routes.

- [ ] **Step 8.3: Implement start + callback in `routes/auth.py`**

Add to `src/aigateway/routes/auth.py`:

```python
from urllib.parse import urlencode

from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..core.oauth_pkce import generate_pkce, generate_state
from ..core.pending_auth import PendingAuthEntry
from ..core.profile_models import Profile, ProfileDefaults, ProfileState
from ..plugins.anthropic_provider import auth as anthropic_auth_module


class StartAuthRequest(BaseModel):
    name: str
    defaults: ProfileDefaults | None = None


def _registry(request: Request):
    return request.app.state.providers


def _pending(request: Request):
    return request.app.state.pending_auth


@router.post("/v1/auth/{provider}/profiles", status_code=201)
async def start_oauth(provider: str, body: StartAuthRequest, request: Request) -> dict:
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider", "provider": provider})

    cfg = plugin.oauth_config()
    if cfg is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})

    profile_id = f"{provider}:{body.name}"
    code_verifier, code_challenge = generate_pkce()
    state = generate_state()

    _pending(request).put(
        state,
        PendingAuthEntry(profile_id=profile_id, code_verifier=code_verifier),
    )

    redirect_uri = f"http://127.0.0.1:{request.app.state.settings.port}{cfg.redirect_path}"
    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(cfg.scopes),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if cfg.extra_authorize_params:
        params.update(cfg.extra_authorize_params)
    authorize_url = f"{cfg.authorize_url}?{urlencode(params)}"

    profile = Profile(
        id=profile_id,
        provider=provider,
        name=body.name,
        state=ProfileState.PENDING,
        defaults=body.defaults or ProfileDefaults(),
    )
    await _index_store(request).upsert(profile)

    return {
        "profile_id": profile_id,
        "authorize_url": authorize_url,
        "state": state,
        "expires_in": 600,
    }


_CALLBACK_HTML = """<!doctype html>
<html><body><p>Authentication complete. You may close this window.</p></body></html>
"""


@router.get("/v1/auth/anthropic/callback")
async def anthropic_callback(code: str, state: str, request: Request):
    return await _generic_callback("anthropic", code, state, request)


async def _generic_callback(provider: str, code: str, state: str, request: Request):
    pending = _pending(request).pop(state)
    if pending is None:
        raise HTTPException(
            status_code=400,
            detail={"code": "unknown_state", "message": "OAuth state not recognized or expired"},
        )

    expected_provider, name = pending.profile_id.split(":", 1)
    if expected_provider != provider:
        raise HTTPException(status_code=400, detail={"code": "provider_mismatch"})

    factory = getattr(request.app.state, f"{provider}_http_factory", None)
    creds = await anthropic_auth_module.exchange_authorization_code(
        code,
        pending.code_verifier,
        http_client_factory=factory,
    )

    plugin = _registry(request).get(provider)
    strategy = plugin.oauth_strategy_for(name)
    strategy.set_credentials(creds)

    p = await _index_store(request).get(provider, name)
    if p is not None:
        p.state = ProfileState.AUTHENTICATED
        await _index_store(request).upsert(p)

    return HTMLResponse(_CALLBACK_HTML)
```

- [ ] **Step 8.4: Wire pending-auth table into `main.py`**

In `create_app()` of `main.py`:

```python
from .core.pending_auth import PendingAuthTable
# ...
app.state.pending_auth = PendingAuthTable(ttl_seconds=600)
```

- [ ] **Step 8.5: Run tests**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_auth_routes.py -v
```

Expected: all pass.

- [ ] **Step 8.6: Commit**

```bash
git add apps/aigateway/src/aigateway/routes/auth.py apps/aigateway/src/aigateway/main.py apps/aigateway/tests/unit/test_auth_routes.py
git commit -m "feat(SF-143): POST start + GET callback OAuth endpoints"
```

---

## Task 9: Auth routes — status, refresh, edit, delete

**Files:**
- Modify: `src/aigateway/routes/auth.py`
- Modify: `tests/unit/test_auth_routes.py`

- [ ] **Step 9.1: Write failing tests**

Append to `tests/unit/test_auth_routes.py`:

```python
def test_status_returns_pending_then_authenticated(client_with_index, monkeypatch) -> None:
    client, credential_blobs = client_with_index

    import httpx
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={
            "access_token": "t", "refresh_token": "r", "expires_in": 3600, "token_type": "Bearer"
        })
    )
    client.app.state.anthropic_http_factory = lambda: httpx.AsyncClient(transport=transport)  # type: ignore

    start = client.post("/v1/auth/anthropic/profiles", json={"name": "x"})
    state = start.json()["state"]

    s1 = client.get("/v1/auth/anthropic/profiles/x/status").json()
    assert s1["state"] == "pending"

    client.get("/v1/auth/anthropic/callback", params={"code": "c", "state": state})

    s2 = client.get("/v1/auth/anthropic/profiles/x/status").json()
    assert s2["state"] == "authenticated"


def test_patch_updates_defaults(client_with_index) -> None:
    client, _ = client_with_index
    # Manually seed an authenticated profile by calling start + callback (simpler)
    import httpx
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={
            "access_token": "t", "refresh_token": "r", "expires_in": 3600, "token_type": "Bearer"
        })
    )
    client.app.state.anthropic_http_factory = lambda: httpx.AsyncClient(transport=transport)  # type: ignore
    start = client.post("/v1/auth/anthropic/profiles", json={"name": "y"})
    client.get("/v1/auth/anthropic/callback", params={"code": "c", "state": start.json()["state"]})

    resp = client.patch(
        "/v1/auth/anthropic/profiles/y",
        json={"defaults": {"model": "anthropic/claude-opus-4-7", "max_tokens": 8192}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["defaults"]["model"] == "anthropic/claude-opus-4-7"
    assert body["defaults"]["max_tokens"] == 8192


def test_delete_removes_profile_and_tokens(client_with_index) -> None:
    client, credential_blobs = client_with_index
    import httpx
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={
            "access_token": "t", "refresh_token": "r", "expires_in": 3600, "token_type": "Bearer"
        })
    )
    client.app.state.anthropic_http_factory = lambda: httpx.AsyncClient(transport=transport)  # type: ignore
    start = client.post("/v1/auth/anthropic/profiles", json={"name": "z"})
    client.get("/v1/auth/anthropic/callback", params={"code": "c", "state": start.json()["state"]})

    from aigateway.plugins.anthropic_provider.auth import credential_service_for
    assert credential_blobs.read(credential_service_for("z"), "default") is not None

    resp = client.delete("/v1/auth/anthropic/profiles/z")
    assert resp.status_code == 204
    assert credential_blobs.read(credential_service_for("z"), "default") is None
    g = client.get("/v1/auth/anthropic/profiles/z")
    assert g.status_code == 404
```

- [ ] **Step 9.2: Run failures**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_auth_routes.py -v
```

Expected: failures on missing routes.

- [ ] **Step 9.3: Implement status, patch, delete, refresh**

Append to `src/aigateway/routes/auth.py`:

```python
@router.get("/v1/auth/{provider}/profiles/{name}/status")
async def profile_status(provider: str, name: str, request: Request) -> dict:
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "profile_not_found", "provider": provider, "name": name},
        )
    return {
        "state": p.state.value,
        "account_label": p.account_label,
        "last_refreshed_at": p.last_refreshed_at.isoformat() if p.last_refreshed_at else None,
    }


class PatchProfileRequest(BaseModel):
    defaults: ProfileDefaults | None = None
    account_label: str | None = None


@router.patch("/v1/auth/{provider}/profiles/{name}")
async def patch_profile(
    provider: str, name: str, body: PatchProfileRequest, request: Request
) -> dict:
    idx = _index_store(request)
    p = await idx.get(provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    if body.defaults is not None:
        p.defaults = body.defaults
    if body.account_label is not None:
        p.account_label = body.account_label
    await idx.upsert(p)
    return p.model_dump(mode="json")


@router.delete("/v1/auth/{provider}/profiles/{name}", status_code=204)
async def delete_profile(provider: str, name: str, request: Request):
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider"})
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    strategy = plugin.oauth_strategy_for(name)
    if strategy is not None and hasattr(strategy, "_store"):
        strategy._store.delete(strategy.credential_service(), strategy.credential_account())
    await _index_store(request).remove(p.id)


@router.post("/v1/auth/{provider}/profiles/{name}/refresh")
async def refresh_profile(provider: str, name: str, request: Request) -> dict:
    plugin = _registry(request).get(provider)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_provider"})
    strategy = plugin.oauth_strategy_for(name)
    if strategy is None:
        raise HTTPException(status_code=400, detail={"code": "provider_does_not_use_oauth"})
    await strategy.refresh()
    p = await _index_store(request).get(provider, name)
    if p is None:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found"})
    return p.model_dump(mode="json")
```

Note: `BaseOAuthStrategy.refresh()` already exists from SF-139's earlier code. If the version on disk doesn't have it, add:

```python
# In src/aigateway/core/oauth_base.py BaseOAuthStrategy:
async def refresh(self) -> None:
    async with self._lock:
        if self._cached is None:
            self._cached = self._read_credential()
        self._cached = await self._refresh_credential(self._cached)
```

- [ ] **Step 9.4: Run tests**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_auth_routes.py -v
```

Expected: all pass.

- [ ] **Step 9.5: Commit**

```bash
git add apps/aigateway/src/aigateway/routes/auth.py apps/aigateway/src/aigateway/core/oauth_base.py apps/aigateway/tests/unit/test_auth_routes.py
git commit -m "feat(SF-143): GET status, PATCH defaults, DELETE, POST refresh"
```

---

## Task 10: Chat route — `X-Profile` resolution + Bucket-A merge

**Files:**
- Modify: `src/aigateway/routes/chat.py`
- Create: `tests/unit/test_chat_x_profile.py`

- [ ] **Step 10.1: Write failing tests**

`tests/unit/test_chat_x_profile.py`:

```python
from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileState
from aigateway.main import create_app
from aigateway.plugins.anthropic_provider.auth import credential_service_for


def _seed_authenticated_profile(credential_blobs, defaults=None) -> None:
    import time
    credential_blobs.write(
        credential_service_for("default"),
        "default",
        json.dumps({
            "access_token": "tok",
            "refresh_token": "rt",
            "expires_at_ms": int(time.time() * 1000) + 3_600_000,
            "token_type": "Bearer",
        }),
    )


@pytest.mark.asyncio
async def test_chat_404_when_profile_missing(credential_blobs, monkeypatch) -> None:
    from aigateway.core import credential_store as cs_module
    from aigateway.core import bootstrap as bs_module
    monkeypatch.setattr(cs_module, "get_credential_store", lambda: credential_blobs)
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: credential_blobs)

    client = TestClient(create_app())
    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Profile": "missing"},
        json={"model": "anthropic/claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


@pytest.mark.asyncio
async def test_chat_409_when_profile_pending(credential_blobs, monkeypatch) -> None:
    from aigateway.core import credential_store as cs_module
    from aigateway.core import bootstrap as bs_module
    monkeypatch.setattr(cs_module, "get_credential_store", lambda: credential_blobs)
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: credential_blobs)

    idx = ProfileIndexStore(credential_store=credential_blobs)
    await idx.upsert(
        Profile(id="anthropic:default", provider="anthropic", name="default", state=ProfileState.PENDING)
    )
    client = TestClient(create_app())
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "anthropic/claude-haiku-4-5", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "profile_pending_auth"


@pytest.mark.asyncio
async def test_chat_merges_profile_defaults(credential_blobs, monkeypatch) -> None:
    from aigateway.core import credential_store as cs_module
    from aigateway.core import bootstrap as bs_module
    monkeypatch.setattr(cs_module, "get_credential_store", lambda: credential_blobs)
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: credential_blobs)

    _seed_authenticated_profile(credential_blobs)
    idx = ProfileIndexStore(credential_store=credential_blobs)
    await idx.upsert(
        Profile(
            id="anthropic:default",
            provider="anthropic",
            name="default",
            state=ProfileState.AUTHENTICATED,
            defaults=ProfileDefaults(max_tokens=4096, reasoning_effort="medium"),
        )
    )

    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        from types import SimpleNamespace
        return SimpleNamespace(model_dump=lambda: {"id": "x", "choices": [{"message": {"content": "ok"}}]})

    with patch("aigateway.routes.chat.litellm.acompletion", fake_acompletion):
        client = TestClient(create_app())
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
                "reasoning_effort": "high",  # body wins
                # max_tokens omitted — profile default fills in
            },
        )
        assert resp.status_code == 200
        assert captured["max_tokens"] == 4096
        assert captured["reasoning_effort"] == "high"
        assert captured["api_key"] == "tok"
```

- [ ] **Step 10.2: Run failures**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_chat_x_profile.py -v
```

Expected: assertion errors / 500s.

- [ ] **Step 10.3: Rewrite `routes/chat.py`**

Replace `src/aigateway/routes/chat.py`:

```python
"""POST /v1/chat/completions — resolves profile auth + merges defaults, dispatches via LiteLLM."""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..core.errors import AuthError, CredentialNotFoundError
from ..core.profile_index import ProfileIndexStore
from ..core.profile_models import ProfileDefaults, ProfileState
from ..core.registry import ProviderRegistry

logger = logging.getLogger(__name__)
router = APIRouter()


_BUCKET_A_FIELDS = (
    "model",
    "max_tokens",
    "temperature",
    "timeout_seconds",
    "reasoning_effort",
)


def _apply_defaults(body: dict[str, Any], defaults: ProfileDefaults) -> dict[str, Any]:
    """Body wins per field. Fields the body omits get the profile default."""
    if defaults.system_prompt and not _has_system_message(body):
        body.setdefault("messages", [])
        body["messages"] = [
            {"role": "system", "content": defaults.system_prompt},
            *body["messages"],
        ]
    for field in _BUCKET_A_FIELDS:
        gateway_field = "timeout" if field == "timeout_seconds" else field
        value = getattr(defaults, field)
        if value is not None and gateway_field not in body:
            body[gateway_field] = value
    return body


def _has_system_message(body: dict[str, Any]) -> bool:
    return any(m.get("role") == "system" for m in body.get("messages", []))


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    body = await request.json()
    if not isinstance(body, dict) or "model" not in body or "messages" not in body:
        raise HTTPException(status_code=400, detail="model and messages are required")

    profile_name = request.headers.get("X-Profile", "default")
    model = body.get("model", "")
    provider = model.split("/", 1)[0] if "/" in model else None
    if not provider:
        raise HTTPException(status_code=400, detail="model must be prefixed (e.g. anthropic/...)")

    registry: ProviderRegistry = request.app.state.providers
    plugin = registry.get(provider)
    if plugin is None:
        raise HTTPException(status_code=400, detail=f"unknown provider: {provider}")

    idx: ProfileIndexStore = request.app.state.profile_index
    profile = await idx.get(provider, profile_name)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "profile_not_found", "provider": provider, "name": profile_name},
        )
    if profile.state == ProfileState.PENDING:
        raise HTTPException(
            status_code=409,
            detail={"code": "profile_pending_auth", "provider": provider, "name": profile_name},
        )

    body = _apply_defaults(body, profile.defaults)

    strategy = plugin.oauth_strategy_for(profile_name)
    if strategy is not None:
        try:
            headers = await strategy.get_authorization_header()
        except CredentialNotFoundError as exc:
            raise HTTPException(
                status_code=401,
                detail={"code": "auth_required", "message": str(exc)},
            )
        except AuthError as exc:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "auth_required",
                    "message": str(exc),
                    "reauth_url": f"/v1/auth/{provider}/profiles/{profile_name}",
                },
            )
        auth_value = headers.pop("Authorization", None)
        if auth_value and auth_value.lower().startswith("bearer "):
            body.setdefault("api_key", auth_value.split(" ", 1)[1])
        if headers:
            merged = dict(body.get("extra_headers") or {})
            merged.update(headers)
            body["extra_headers"] = merged

    if body.get("stream"):
        return StreamingResponse(_stream(body), media_type="text/event-stream")

    response = await litellm.acompletion(**body)
    return response.model_dump() if hasattr(response, "model_dump") else response


async def _stream(body: dict[str, Any]):
    try:
        stream = await litellm.acompletion(**body)
        async for chunk in stream:
            payload = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        logger.exception("stream failed")
        err = {"error": {"message": str(exc), "type": type(exc).__name__}}
        yield f"data: {json.dumps(err)}\n\n"
```

- [ ] **Step 10.4: Run tests**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_chat_x_profile.py -v
```

Expected: 3 passed.

- [ ] **Step 10.5: Run all unit tests**

```bash
cd apps/aigateway && uv run pytest -m "not live" -v
```

Expected: all pass.

- [ ] **Step 10.6: Commit**

```bash
git add apps/aigateway/src/aigateway/routes/chat.py apps/aigateway/tests/unit/test_chat_x_profile.py
git commit -m "feat(SF-143): X-Profile resolution + Bucket-A defaults merge in chat route"
```

---

## Task 11: Wire bootstrap into FastAPI startup

**Files:**
- Modify: `src/aigateway/main.py`

- [ ] **Step 11.1: Add bootstrap call to `create_app()`**

Modify `create_app()` so the bootstrap runs on app startup (lifespan):

```python
from contextlib import asynccontextmanager

from .core.bootstrap import bootstrap_from_claude_code

@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        await bootstrap_from_claude_code(index_store=app.state.profile_index)
    except Exception:
        logger.exception("bootstrap failed; gateway will start with empty index")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()
    app = FastAPI(title="aigateway", version="0.1.0", lifespan=_lifespan)
    # ... rest unchanged
```

- [ ] **Step 11.2: Add a test that exercises bootstrap on startup**

Append to `tests/unit/test_bootstrap.py`:

```python
from fastapi.testclient import TestClient


def test_app_lifespan_runs_bootstrap(credential_blobs, monkeypatch) -> None:
    import json
    import time

    credential_blobs.write(
        CC_SERVICE,
        "alice",
        json.dumps({
            "claudeAiOauth": {
                "accessToken": "boot-tok",
                "refreshToken": "boot-rt",
                "expiresAt": int(time.time() * 1000) + 3_600_000,
                "scopes": ["user:inference"],
            }
        }),
    )
    monkeypatch.setenv("USER", "alice")

    from aigateway.core import credential_store as cs_module
    monkeypatch.setattr(cs_module, "get_credential_store", lambda: credential_blobs)
    from aigateway.core import bootstrap as bs_module
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: credential_blobs)

    from aigateway.main import create_app
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/v1/auth/profiles")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["profiles"]]
        assert "anthropic:default" in ids
```

(`TestClient` as a context manager is what triggers the lifespan.)

- [ ] **Step 11.3: Run**

```bash
cd apps/aigateway && uv run pytest tests/unit/test_bootstrap.py -v
```

Expected: 4 passed.

- [ ] **Step 11.4: Commit**

```bash
git add apps/aigateway/src/aigateway/main.py apps/aigateway/tests/unit/test_bootstrap.py
git commit -m "feat(SF-143): run Claude Code bootstrap on FastAPI startup"
```

---

## Task 12: Update live e2e to profile-based path

**Files:**
- Modify: `tests/live/test_anthropic_live.py`

- [ ] **Step 12.1: Update the live test**

`tests/live/test_anthropic_live.py`:

```python
"""End-to-end live test against api.anthropic.com via the profile-based path.

Skipped unless AIGW_LIVE=1. Requires the gateway's `anthropic:default`
profile to be authenticated — typically achieved on this machine by the
Claude Code bootstrap importing existing CC credentials.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from aigateway.main import create_app

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.environ.get("AIGW_LIVE") == "1"


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_round_trip_via_default_profile() -> None:
    with TestClient(create_app()) as client:
        # Sanity: bootstrap should have populated the default profile from CC.
        listing = client.get("/v1/auth/profiles").json()
        ids = {p["id"] for p in listing["profiles"]}
        assert "anthropic:default" in ids, (
            "anthropic:default profile not present. "
            "Run `claude auth login` or seed a profile via /v1/auth/anthropic/profiles."
        )

        resp = client.post(
            "/v1/chat/completions",
            headers={"X-Profile": "default"},
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "Reply with the single word 'pong'."}],
                "max_tokens": 10,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["choices"][0]["message"]["content"]
```

- [ ] **Step 12.2: Run live**

```bash
cd apps/aigateway && AIGW_LIVE=1 uv run pytest tests/live/ -v
```

Expected: 1 passed (assuming a working CC credential store entry exists on the test machine).

- [ ] **Step 12.3: Run full suite (unit + live) one more time**

```bash
cd apps/aigateway && AIGW_LIVE=1 uv run pytest -v
```

Expected: every test passes.

- [ ] **Step 12.4: Commit**

```bash
git add apps/aigateway/tests/live/test_anthropic_live.py
git commit -m "test(SF-143): live e2e exercises profile-based chat path"
```

---

## Final verification

- [ ] **Run the gateway by hand**

```bash
cd apps/aigateway
uv run uvicorn aigateway.main:app --port 9105 --log-level info
```

In another shell:

```bash
# Listing
curl -s http://127.0.0.1:9105/v1/auth/profiles | python3 -m json.tool

# Status of default
curl -s http://127.0.0.1:9105/v1/auth/anthropic/profiles/default/status | python3 -m json.tool

# Edit defaults
curl -s -X PATCH http://127.0.0.1:9105/v1/auth/anthropic/profiles/default \
  -H 'content-type: application/json' \
  -d '{"defaults": {"max_tokens": 8192, "reasoning_effort": "high"}}' \
  | python3 -m json.tool

# Chat (default profile)
curl -s -X POST http://127.0.0.1:9105/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"anthropic/claude-haiku-4-5","messages":[{"role":"user","content":"pong?"}],"max_tokens":10}' \
  | python3 -m json.tool

# Start a new profile (browser dance required to complete)
curl -s -X POST http://127.0.0.1:9105/v1/auth/anthropic/profiles \
  -H 'content-type: application/json' \
  -d '{"name":"work"}' \
  | python3 -m json.tool
```

All four should succeed (the last one returns an authorize_url; opening it in a browser completes the flow against `localhost:9105/v1/auth/anthropic/callback`).
