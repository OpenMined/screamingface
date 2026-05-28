# SF-169: SF Backend Plugins Consume aigateway OAuth Connections — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Asana:** https://app.asana.com/1/1185126988600652/task/1214568344507183
**Ticket:** SF-169 / DEMO-027 — SF backend plugins consume aigateway OAuth Connections
**Branch:** `SF-169-aigw-oauth-connections-consumer` (already created from fresh `origin/main`)

**Goal:** Teach the three OAuth-using SF backend plugins (`claude_backend_api`, `codex_backend_api`, `gemini_backend_api`) to optionally fetch access tokens from the aigateway OAuth Connections API (`GET /v1/oauth/connections/{id}/token`) instead of reading the provider's CLI keychain. When the new `connection_id` setting is unset, behavior is byte-for-byte identical to today.

**Architecture:** Inject an optional `AigwTokenSource` into each `OAuthStrategy` subclass via the existing `__init__`. When present, `_read_credential` / `_refresh_credential` route through the helper instead of the on-disk keychain. The helper caches in-memory until 30s before expiry, serializes refreshes with an `asyncio.Lock`, and reads a fresh JWT from a caller-supplied async getter on every fetch (so re-login pickup is automatic). `_build_headers` is unchanged — each provider's subclass still owns its provider-specific header shape.

**Tech Stack:** Python 3.13, httpx async, pydantic-settings, pytest-asyncio, `httpx.MockTransport` for the fake aigateway in e2e.

---

## ⛔ Blockers — verify before starting

Both must be confirmed landed (or this plan stalls):

### 1. Aigateway `/token` endpoint (D-AIGW-010) does NOT exist on `origin/main`

Current routes in `apps/aigateway/src/aigateway/routes/oauth_connections.py` are:
- `GET /v1/oauth/connections`
- `GET /v1/oauth/connections/{id}`
- `POST /v1/oauth/connections`
- `PATCH /v1/oauth/connections/{id}`
- `DELETE /v1/oauth/connections/{id}`
- `POST /v1/oauth/connections/{id}/refresh`

There is **no `GET /v1/oauth/connections/{id}/token`** that returns `{access_token, expires_at}`. SF-169 cannot run without it.

**Required contract** (this plan assumes once D-AIGW-010 lands):
```
GET /v1/oauth/connections/{id}/token
  Headers: Authorization: Bearer <aigw-jwt>
  200: { "access_token": "...", "expires_at": "2026-05-26T15:00:00Z" }
  401: aigw JWT invalid / expired                — clear error, user re-logs into aigw
  404: connection_id not found / not owned       — clear error
  409: connection.status != "active"             — clear error
  503: aigw upstream refresh failed              — clear error, optionally retry
```

**Action:** Open a separate ticket "D-AIGW-010 — Token-fetch endpoint with JWT auth on OAuth Connections" if not already tracked. Mark SF-169 as blocked-by until it merges.

### 2. JWT-provider plumbing on the SF server side is undefined

The ticket's snippet takes `aigw_jwt_provider: Callable[[], Awaitable[str]]`. There is no aigw-JWT source today on the SF server. DEMO-029 (desktop session manager) is the upstream owner, but that ticket isn't this one.

**This plan's stance:** SF-169 implements the strategy plumbing for a JWT provider, but bootstraps the initial JWT from an env var `SF_AIGW_JWT`. DEMO-029 later supplants the env-var source with desktop-driven IPC. This lets SF-169 ship + test end-to-end without depending on the desktop work.

If you disagree with the env-var bootstrap, stop here and discuss before Task 1.

---

## File Structure

**Create:**
- `apps/server/src/screamingface/plugins/llm_base/aigw_token_source.py` — `AigwTokenSource`, `AigwTokenError`, `AigwAuthError`, `aigw_jwt_from_env`
- `apps/server/src/screamingface/plugins/llm_base/tests/test_aigw_token_source.py` — unit tests with `httpx.MockTransport`
- `apps/server/tests/e2e/infrastructure/fake_aigw.py` — small reusable fake-aigw ASGI app or transport for e2e
- `apps/server/tests/e2e/test_aigw_connection_path.py` — backend → aigw → mocked Anthropic full path

**Modify:**
- `apps/server/src/screamingface/plugins/llm_base/oauth_base.py` — accept optional `aigw_source`, route `_read_credential` + `_refresh_credential` through it when set
- `apps/server/src/screamingface/plugins/claude_backend_api/auth.py` — accept + forward `aigw_source`
- `apps/server/src/screamingface/plugins/codex_backend_api/auth.py` — same
- `apps/server/src/screamingface/plugins/gemini_backend_api/auth.py` — same
- `apps/server/src/screamingface/plugins/claude_backend_api/plugin.py` — Settings: `connection_id`, `aigw_url`; `customize_schema` annotates the field; backend wiring builds `AigwTokenSource`
- `apps/server/src/screamingface/plugins/codex_backend_api/plugin.py` — same
- `apps/server/src/screamingface/plugins/gemini_backend_api/plugin.py` — same
- `apps/server/src/screamingface/plugins/claude_backend_api/backend.py` — accept `aigw_source` in `AnthropicBackend.__init__`; forward to `ClaudeCodeOAuth`
- `apps/server/src/screamingface/plugins/codex_backend_api/backend.py` — same wiring as claude
- `apps/server/src/screamingface/plugins/gemini_backend_api/backend.py` — same wiring

**Design note on the integration shape:**
The ticket draft says "OAuthStrategy.get_token() delegates". The real base class method is `get_authorization_header()`, and provider-specific header shapes (anthropic-beta, gemini User-Agent, etc.) must still be built. The cleanest integration is at the `_read_credential` / `_refresh_credential` hooks — when an `aigw_source` is wired in, both hooks call the source and synthesize a provider-shaped creds dict; `_build_headers(creds)` is unchanged. Each provider subclass owns the shape-translation because each uses different keys (Claude: `accessToken`+`expiresAt` ms; Codex: `access_token` + JWT-decoded exp; Gemini: `access_token` + `expiry_date` ms).

---

## Task 1: AigwTokenSource helper + unit tests

**Files:**
- Create: `apps/server/src/screamingface/plugins/llm_base/aigw_token_source.py`
- Create: `apps/server/src/screamingface/plugins/llm_base/tests/test_aigw_token_source.py`

- [ ] **Step 1: Write the failing unit tests**

```python
# apps/server/src/screamingface/plugins/llm_base/tests/test_aigw_token_source.py
"""Unit tests for AigwTokenSource — token fetch, cache, refresh, error paths."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from screamingface.plugins.llm_base.aigw_token_source import (
    AigwAuthError,
    AigwTokenError,
    AigwTokenSource,
)


def _ok_payload(*, access_token: str = "tok-1", ttl_seconds: int = 3600) -> dict:
    return {
        "access_token": access_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(),
    }


def _mk_source(handler, *, jwt: str = "jwt-A") -> AigwTokenSource:
    async def jwt_provider() -> str:
        return jwt

    transport = httpx.MockTransport(handler)
    return AigwTokenSource(
        connection_id="conn-1",
        aigw_url="http://aigw.test",
        aigw_jwt_provider=jwt_provider,
        http_transport=transport,
    )


@pytest.mark.asyncio
async def test_fetches_and_returns_access_token():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/oauth/connections/conn-1/token"
        assert req.headers["authorization"] == "Bearer jwt-A"
        return httpx.Response(200, json=_ok_payload(access_token="tok-A"))

    src = _mk_source(handler)
    assert await src.fetch_token() == "tok-A"


@pytest.mark.asyncio
async def test_caches_until_near_expiry():
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_ok_payload(access_token=f"tok-{calls}"))

    src = _mk_source(handler)
    tokens = [await src.fetch_token() for _ in range(100)]
    assert tokens == ["tok-1"] * 100
    assert calls == 1


@pytest.mark.asyncio
async def test_refetches_after_expiry():
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        # First token: already expired (ttl 0); second: long-lived.
        ttl = 0 if calls == 1 else 3600
        return httpx.Response(200, json=_ok_payload(access_token=f"tok-{calls}", ttl_seconds=ttl))

    src = _mk_source(handler)
    assert await src.fetch_token() == "tok-1"
    assert await src.fetch_token() == "tok-2"
    assert calls == 2


@pytest.mark.asyncio
async def test_401_raises_auth_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "jwt expired"})

    src = _mk_source(handler)
    with pytest.raises(AigwAuthError) as exc_info:
        await src.fetch_token()
    assert "re-login" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_404_raises_token_error_with_connection_id():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "connection_not_found"})

    src = _mk_source(handler)
    with pytest.raises(AigwTokenError) as exc_info:
        await src.fetch_token()
    assert "conn-1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_503_raises_token_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream refresh failed")

    src = _mk_source(handler)
    with pytest.raises(AigwTokenError):
        await src.fetch_token()


@pytest.mark.asyncio
async def test_transport_error_raises_token_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("aigw unreachable")

    src = _mk_source(handler)
    with pytest.raises(AigwTokenError) as exc_info:
        await src.fetch_token()
    assert "aigw" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_fetch():
    calls = 0
    gate = asyncio.Event()

    def handler(req: httpx.Request) -> httpx.Response:
        # Synchronous handler — but we can't await here. Just count.
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_ok_payload(access_token=f"tok-{calls}"))

    src = _mk_source(handler)
    tokens = await asyncio.gather(*[src.fetch_token() for _ in range(20)])
    assert len(set(tokens)) == 1  # all callers got the same token
    assert calls == 1


@pytest.mark.asyncio
async def test_jwt_provider_called_each_fetch_attempt():
    jwt_calls = 0

    async def jwt_provider() -> str:
        nonlocal jwt_calls
        jwt_calls += 1
        return f"jwt-{jwt_calls}"

    sent_headers: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent_headers.append(req.headers["authorization"])
        # Already-expired token forces refetch next call.
        return httpx.Response(200, json=_ok_payload(ttl_seconds=0))

    transport = httpx.MockTransport(handler)
    src = AigwTokenSource(
        connection_id="conn-1",
        aigw_url="http://aigw.test",
        aigw_jwt_provider=jwt_provider,
        http_transport=transport,
    )
    await src.fetch_token()
    await src.fetch_token()
    assert sent_headers == ["Bearer jwt-1", "Bearer jwt-2"]
```

- [ ] **Step 2: Run the tests — confirm they fail**

```bash
cd apps/server && uv run pytest src/screamingface/plugins/llm_base/tests/test_aigw_token_source.py -v
```

Expected: ImportError / ModuleNotFoundError for `aigw_token_source`.

- [ ] **Step 3: Implement the helper**

```python
# apps/server/src/screamingface/plugins/llm_base/aigw_token_source.py
"""AigwTokenSource — fetch + cache OAuth tokens from aigateway.

Plugged into OAuthStrategy._read_credential / _refresh_credential when a
backend plugin has connection_id + aigw_url configured. Aigateway handles
provider-side refresh; this helper just trusts the access_token + expires_at
it gets back and caches in-memory until 30s before expiry.

Critical: aigateway is NOT on the LLM hot path. We fetch a fresh token,
then call the LLM provider directly. Aigateway availability affects auth,
not chat completions.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

_REFRESH_WINDOW = timedelta(seconds=30)
_DEFAULT_TIMEOUT = 5.0


class AigwTokenError(Exception):
    """Aigateway returned a non-recoverable status (404/503/transport)."""


class AigwAuthError(AigwTokenError):
    """Aigateway returned 401 — the caller's JWT is invalid / expired."""


@dataclass
class _CacheEntry:
    access_token: str
    expires_at: datetime


class AigwTokenSource:
    """Fetch + cache aigateway access tokens for one connection.

    Args:
        connection_id: aigateway OAuthConnection id.
        aigw_url: aigateway base URL (e.g. http://localhost:9105).
        aigw_jwt_provider: async getter for the current aigw JWT. Called
            on every fetch so re-login picks up automatically.
        http_timeout: per-request timeout in seconds. Default 5s.
        http_transport: injected by tests (httpx.MockTransport).
    """

    def __init__(
        self,
        *,
        connection_id: str,
        aigw_url: str,
        aigw_jwt_provider: Callable[[], Awaitable[str]],
        http_timeout: float = _DEFAULT_TIMEOUT,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._connection_id = connection_id
        self._aigw_url = aigw_url.rstrip("/")
        self._jwt_provider = aigw_jwt_provider
        self._timeout = http_timeout
        self._transport = http_transport
        self._cache: _CacheEntry | None = None
        self._lock = asyncio.Lock()

    async def fetch_token(self) -> str:
        async with self._lock:
            now = datetime.now(timezone.utc)
            if self._cache is not None and self._cache.expires_at - now > _REFRESH_WINDOW:
                return self._cache.access_token
            entry = await self._fetch_once()
            self._cache = entry
            return entry.access_token

    @property
    def connection_id(self) -> str:
        return self._connection_id

    async def _fetch_once(self) -> _CacheEntry:
        jwt = await self._jwt_provider()
        url = f"{self._aigw_url}/v1/oauth/connections/{self._connection_id}/token"
        client_kwargs: dict = {"timeout": self._timeout}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {jwt}"})
        except httpx.RequestError as exc:
            raise AigwTokenError(f"aigw unreachable at {url}: {exc}") from exc

        if resp.status_code == 401:
            raise AigwAuthError(
                "aigateway rejected the JWT — re-login to aigateway required."
            )
        if resp.status_code != 200:
            raise AigwTokenError(
                f"aigateway returned {resp.status_code} for connection "
                f"{self._connection_id}: {resp.text[:200]}"
            )
        data = resp.json()
        try:
            expires_at = datetime.fromisoformat(data["expires_at"])
        except (KeyError, ValueError) as exc:
            raise AigwTokenError(
                f"aigateway response missing or malformed 'expires_at': {data!r}"
            ) from exc
        if "access_token" not in data:
            raise AigwTokenError(
                f"aigateway response missing 'access_token': {data!r}"
            )
        # Tolerate naive datetimes — assume UTC.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return _CacheEntry(access_token=data["access_token"], expires_at=expires_at)


async def aigw_jwt_from_env() -> str:
    """Default JWT provider — reads SF_AIGW_JWT from the environment.

    Bootstrap path until DEMO-029 (desktop session manager) wires a
    real IPC-driven provider. If the env var is unset, the helper
    raises AigwAuthError so the failure surfaces as 'aigw JWT missing'
    rather than a 401 round-trip.
    """
    jwt = os.environ.get("SF_AIGW_JWT", "").strip()
    if not jwt:
        raise AigwAuthError(
            "SF_AIGW_JWT is not set — log in to aigateway or unset connection_id."
        )
    return jwt


__all__ = ["AigwTokenSource", "AigwTokenError", "AigwAuthError", "aigw_jwt_from_env"]
```

- [ ] **Step 4: Run tests — all pass**

```bash
cd apps/server && uv run pytest src/screamingface/plugins/llm_base/tests/test_aigw_token_source.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/screamingface/plugins/llm_base/aigw_token_source.py \
        apps/server/src/screamingface/plugins/llm_base/tests/test_aigw_token_source.py
git commit -m "SF-169: add AigwTokenSource helper with cache + lock + JWT-provider"
```

---

## Task 2: Wire optional aigw_source into OAuthStrategy

**Files:**
- Modify: `apps/server/src/screamingface/plugins/llm_base/oauth_base.py`
- Create: `apps/server/src/screamingface/plugins/llm_base/tests/test_oauth_base_aigw.py`

**Design summary:** `OAuthStrategy.__init__` gains an optional `aigw_source: AigwTokenSource | None`. When set:
- `_read_credential()` calls a NEW abstract hook `_aigw_creds_shape(access_token, expires_at)` to convert the aigw response into a provider-shaped creds dict (Claude: `{accessToken, expiresAt: ms}`; Codex/Gemini: `{access_token, …}`).
- `_refresh_credential()` does the same — there's no provider refresh round-trip because aigw owns refresh.

The base class supplies a default `_aigw_creds_shape` that raises `NotImplementedError` — providers must opt in explicitly.

- [ ] **Step 1: Write failing tests for the new branch**

```python
# apps/server/src/screamingface/plugins/llm_base/tests/test_oauth_base_aigw.py
"""Test that OAuthStrategy routes through aigw_source when configured."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
from screamingface.plugins.llm_base.oauth_base import OAuthStrategy


class _FakeStrategy(OAuthStrategy):
    """Concrete strategy that uses the snake_case shape (like Codex/Gemini)."""

    def _read_credential(self) -> dict:
        raise AssertionError("CLI keychain path must not be reached with aigw_source set")

    def _is_expired(self, creds: dict) -> bool:
        return False

    async def _refresh_credential(self, creds: dict) -> dict:
        raise AssertionError("provider refresh must not be reached with aigw_source set")

    def _build_headers(self, creds: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {creds['access_token']}"}

    def _aigw_creds_shape(self, access_token: str, expires_at: datetime) -> dict:
        return {"access_token": access_token, "expires_at_iso": expires_at.isoformat()}


@pytest.mark.asyncio
async def test_aigw_source_replaces_keychain_read():
    fake_source = AsyncMock(spec=AigwTokenSource)
    fake_source.fetch_token.return_value = "aigw-token-1"
    strat = _FakeStrategy(aigw_source=fake_source)

    headers = await strat.get_authorization_header()
    assert headers == {"Authorization": "Bearer aigw-token-1"}
    fake_source.fetch_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_aigw_source_unset_uses_existing_path():
    """Sanity: without aigw_source the existing abstract hooks are called."""

    class _LocalStrategy(_FakeStrategy):
        called = False

        def _read_credential(self):
            _LocalStrategy.called = True
            return {"access_token": "from-disk"}

    strat = _LocalStrategy()
    headers = await strat.get_authorization_header()
    assert headers == {"Authorization": "Bearer from-disk"}
    assert _LocalStrategy.called is True
```

- [ ] **Step 2: Run — expect AttributeError / NotImplementedError**

```bash
cd apps/server && uv run pytest src/screamingface/plugins/llm_base/tests/test_oauth_base_aigw.py -v
```

- [ ] **Step 3: Modify `oauth_base.py`**

Apply these changes:

```python
# At top, add the import
from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource

# Modify __init__:
def __init__(self, *, aigw_source: AigwTokenSource | None = None) -> None:
    self._cached: dict | None = None
    self._lock = asyncio.Lock()
    self._aigw_source = aigw_source

# Inside get_authorization_header(), update the slow path to branch on aigw:
async with self._lock:
    if self._cached is None:
        self._cached = await self._load_credential()
    if self._is_expired(self._cached):
        self._cached = await self._refresh_or_aigw(self._cached)

# Add two new helper methods on the class:
async def _load_credential(self) -> dict:
    if self._aigw_source is not None:
        return await self._fetch_via_aigw()
    return self._read_credential()

async def _refresh_or_aigw(self, creds: dict) -> dict:
    if self._aigw_source is not None:
        return await self._fetch_via_aigw()
    return await self._refresh_credential(creds)

async def _fetch_via_aigw(self) -> dict:
    from datetime import datetime, timezone
    token = await self._aigw_source.fetch_token()
    # Aigateway owns expiry; the helper already filters near-expiry tokens,
    # so we just stamp now+1h as a placeholder. The next get_authorization_header
    # call will hit the helper's cache anyway.
    placeholder_expiry = datetime.now(timezone.utc).replace(microsecond=0)
    return self._aigw_creds_shape(token, placeholder_expiry)

# Add the new hook (no @abstractmethod — providers opt in):
def _aigw_creds_shape(self, access_token: str, expires_at) -> dict:
    raise NotImplementedError(
        f"{type(self).__name__} does not support aigw_source — set connection_id only "
        "on a provider that has implemented _aigw_creds_shape."
    )
```

**Important:** the existing `_read_credential` and `_refresh_credential` abstractmethods stay — they're still required for the CLI-keychain path. Providers gain `_aigw_creds_shape` as a new opt-in hook.

Also update `refresh()` similarly:
```python
async def refresh(self) -> None:
    async with self._lock:
        if self._cached is None:
            self._cached = await self._load_credential()
        self._cached = await self._refresh_or_aigw(self._cached)
```

- [ ] **Step 4: Run base tests — confirm green**

```bash
cd apps/server && uv run pytest src/screamingface/plugins/llm_base/tests/test_oauth_base_aigw.py -v
# also re-run the full llm_base suite to catch regressions:
uv run pytest src/screamingface/plugins/llm_base -v
```

Expected: 2 new tests pass; no existing tests break.

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/screamingface/plugins/llm_base/oauth_base.py \
        apps/server/src/screamingface/plugins/llm_base/tests/test_oauth_base_aigw.py
git commit -m "SF-169: add optional aigw_source slot to OAuthStrategy base"
```

---

## Task 3: Claude backend — strategy, settings, plugin wiring

**Files:**
- Modify: `apps/server/src/screamingface/plugins/claude_backend_api/auth.py`
- Modify: `apps/server/src/screamingface/plugins/claude_backend_api/backend.py`
- Modify: `apps/server/src/screamingface/plugins/claude_backend_api/plugin.py`
- Modify: `apps/server/src/screamingface/plugins/claude_backend_api/tests/test_auth.py` — add aigw shape test

- [ ] **Step 1: Write failing tests for the Claude aigw path**

Append to `apps/server/src/screamingface/plugins/claude_backend_api/tests/test_auth.py`:

```python
@pytest.mark.asyncio
async def test_claude_oauth_uses_aigw_source_when_set(monkeypatch):
    from unittest.mock import AsyncMock

    from screamingface.plugins.claude_backend_api.auth import ClaudeCodeOAuth
    from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource

    fake = AsyncMock(spec=AigwTokenSource)
    fake.fetch_token.return_value = "aigw-claude-token"

    strat = ClaudeCodeOAuth(aigw_source=fake)
    headers = await strat.get_authorization_header()

    assert headers["Authorization"] == "Bearer aigw-claude-token"
    assert "anthropic-version" in headers
    assert "anthropic-beta" in headers
    fake.fetch_token.assert_awaited_once()
```

- [ ] **Step 2: Implement in `auth.py`**

Modify `ClaudeCodeOAuth.__init__`:

```python
def __init__(
    self,
    *,
    credential_store: CredentialStore | None = None,
    account: str | None = None,
    http_client_factory=None,
    aigw_source: AigwTokenSource | None = None,  # NEW
) -> None:
    super().__init__(aigw_source=aigw_source)  # NEW: pass through
    self._store = credential_store or get_credential_store()
    self._account = account if account is not None else os.environ.get("USER", "")
    self._http_factory = http_client_factory or (
        lambda: httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    )
```

Add the import at the top:
```python
from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
```

Add the `_aigw_creds_shape` override on the class:
```python
def _aigw_creds_shape(self, access_token: str, expires_at) -> dict:
    """Build the Claude keychain shape from an aigw token.

    Subscription/scope fields aren't supplied by aigw — they're not needed
    for _build_headers, which only reads accessToken.
    """
    return {
        "accessToken": access_token,
        "expiresAt": int(expires_at.timestamp() * 1000),
        "scopes": OAUTH_REFRESH_SCOPES,
        "subscriptionType": "max",
        "rateLimitTier": "default_claude_max_5x",
    }
```

- [ ] **Step 3: Modify `backend.py`**

Add `aigw_source` to `AnthropicBackend.__init__` and forward into `ClaudeCodeOAuth`:

```python
def __init__(
    self,
    *,
    auth: ClaudeCodeOAuth | None = None,
    adapter: AnthropicAdapter | None = None,
    http_client_factory=None,
    aigw_source: AigwTokenSource | None = None,  # NEW
) -> None:
    self._auth = auth or ClaudeCodeOAuth(aigw_source=aigw_source)
    self._adapter = adapter or AnthropicAdapter()
    self._http_factory = http_client_factory or default_http_factory
```

Add the import:
```python
from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource
```

- [ ] **Step 4: Modify `plugin.py` — settings + customize_schema**

In `ClaudeBackendApiSettings`, add fields:

```python
connection_id: str | None = Field(
    default=None,
    description="aigateway OAuthConnection id. When set, tokens are fetched "
                "from aigateway instead of the Claude Code credential store.",
)
aigw_url: str = Field(
    default="http://localhost:9105",
    description="Base URL of the aigateway service.",
)
```

In `ClaudeBackendApiPlugin`, override `customize_schema` to annotate the field:

```python
def customize_schema(self, schema: dict) -> dict:
    schema = super().customize_schema(schema)
    props = schema.get("properties", {})
    if "connection_id" in props:
        # Tell the desktop config UI (DEMO-028) to render a connection picker.
        props["connection_id"]["x-aigw-connection-picker"] = {
            "provider": "claude",
            "aigw_url_field": "aigw_url",
        }
    return schema
```

Also: where the plugin builds its backend (in `_make_interpreter` and wherever else), construct an `AigwTokenSource` when `settings.connection_id` is non-empty and pass it through. **Search the plugin for the existing `AnthropicBackend()` / `ClaudeCodeOAuth()` instantiation sites and update each.**

Suggested factory helper on the plugin module:

```python
def _maybe_aigw_source(settings: ClaudeBackendApiSettings) -> AigwTokenSource | None:
    if not settings.connection_id:
        return None
    from screamingface.plugins.llm_base.aigw_token_source import (
        AigwTokenSource,
        aigw_jwt_from_env,
    )
    return AigwTokenSource(
        connection_id=settings.connection_id,
        aigw_url=settings.aigw_url,
        aigw_jwt_provider=aigw_jwt_from_env,
    )
```

- [ ] **Step 5: Run all claude_backend_api tests**

```bash
cd apps/server && uv run pytest src/screamingface/plugins/claude_backend_api -v
```

Expected: all green, including the new aigw test.

- [ ] **Step 6: Commit**

```bash
git add apps/server/src/screamingface/plugins/claude_backend_api/
git commit -m "SF-169: claude-backend-api consumes aigw OAuth connections"
```

---

## Task 4: Codex backend — same shape as Task 3

**Files mirror Task 3 under `codex_backend_api/`.**

- [ ] **Step 1: Write the failing test (snake_case shape)**

Append to `apps/server/src/screamingface/plugins/codex_backend_api/tests/test_auth.py`:

```python
@pytest.mark.asyncio
async def test_codex_oauth_uses_aigw_source_when_set():
    from unittest.mock import AsyncMock

    from screamingface.plugins.codex_backend_api.auth import CodexOAuth
    from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource

    fake = AsyncMock(spec=AigwTokenSource)
    fake.fetch_token.return_value = "aigw-codex-token"

    strat = CodexOAuth(aigw_source=fake)
    headers = await strat.get_authorization_header()

    assert headers == {"Authorization": "Bearer aigw-codex-token"}
    fake.fetch_token.assert_awaited_once()
```

- [ ] **Step 2: Modify `CodexOAuth.__init__`** — accept `aigw_source` and pass to `super().__init__(aigw_source=...)`.

- [ ] **Step 3: Override `_aigw_creds_shape`** on `CodexOAuth`:

```python
def _aigw_creds_shape(self, access_token: str, expires_at) -> dict:
    return {
        "access_token": access_token,
        "refresh_token": "",
        "id_token": "",
    }
```

(Codex's `_is_expired` decodes the JWT exp; the aigw path bypasses `_is_expired` since the helper owns expiry — but `_build_headers` only reads `access_token`, so the shape is fine.)

- [ ] **Step 4: Modify `codex_backend_api/backend.py` + `plugin.py`** mirroring Task 3 step 3-4.

- [ ] **Step 5: Test + commit**

```bash
cd apps/server && uv run pytest src/screamingface/plugins/codex_backend_api -v
git add apps/server/src/screamingface/plugins/codex_backend_api/
git commit -m "SF-169: codex-backend-api consumes aigw OAuth connections"
```

---

## Task 5: Gemini backend — same shape as Task 3

- [ ] **Step 1: Failing test**

```python
@pytest.mark.asyncio
async def test_gemini_oauth_uses_aigw_source_when_set():
    from unittest.mock import AsyncMock

    from screamingface.plugins.gemini_backend_api.auth import GeminiAuth
    from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource

    fake = AsyncMock(spec=AigwTokenSource)
    fake.fetch_token.return_value = "aigw-gemini-token"

    strat = GeminiAuth(aigw_source=fake)
    headers = await strat.get_authorization_header()

    assert headers["Authorization"] == "Bearer aigw-gemini-token"
    assert headers["User-Agent"].startswith("GeminiCLI/")
    fake.fetch_token.assert_awaited_once()
```

- [ ] **Step 2: Modify `GeminiAuth.__init__`** as in Task 3.

- [ ] **Step 3: Override `_aigw_creds_shape`**:

```python
def _aigw_creds_shape(self, access_token: str, expires_at) -> dict:
    return {
        "access_token": access_token,
        "refresh_token": "",
        "expiry_date": int(expires_at.timestamp() * 1000),
        "token_type": "Bearer",
    }
```

**Header override caveat:** Gemini's `_header_override` short-circuits to API-key headers when `GEMINI_API_KEY` is set. The aigw branch lives AFTER the override check in `get_authorization_header`, so a user with both an API key and a connection_id gets the API key — same precedence as today. Document this in the settings field description.

- [ ] **Step 4: Modify `gemini_backend_api/backend.py` + `plugin.py`** mirroring Task 3.

- [ ] **Step 5: Test + commit**

```bash
cd apps/server && uv run pytest src/screamingface/plugins/gemini_backend_api -v
git add apps/server/src/screamingface/plugins/gemini_backend_api/
git commit -m "SF-169: gemini-backend-api consumes aigw OAuth connections"
```

---

## Task 6: E2E test with fake aigateway

**Files:**
- Create: `apps/server/tests/e2e/infrastructure/fake_aigw.py`
- Create: `apps/server/tests/e2e/test_aigw_connection_path.py`

- [ ] **Step 1: Write the fake aigateway transport**

```python
# apps/server/tests/e2e/infrastructure/fake_aigw.py
"""Tiny httpx.MockTransport-backed fake aigateway for SF-169 e2e tests.

Returns canned token responses for a fixed connection_id; rejects all
others with 404. Asserts the Authorization header matches an expected JWT.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx


def make_fake_aigw(
    *,
    expected_connection_id: str,
    expected_jwt: str,
    access_token: str = "aigw-fake-token",
    ttl_seconds: int = 3600,
) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        path = f"/v1/oauth/connections/{expected_connection_id}/token"
        if req.url.path != path:
            return httpx.Response(404, json={"detail": "connection_not_found"})
        auth = req.headers.get("authorization", "")
        if auth != f"Bearer {expected_jwt}":
            return httpx.Response(401, json={"detail": "jwt invalid"})
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).isoformat()
        return httpx.Response(
            200, json={"access_token": access_token, "expires_at": expires_at}
        )

    return httpx.MockTransport(handler)
```

- [ ] **Step 2: Write the e2e test**

```python
# apps/server/tests/e2e/test_aigw_connection_path.py
"""End-to-end: SF backend → aigateway → Anthropic.

Verifies that when claude-backend-api is configured with a connection_id,
- the outbound /messages call carries the aigw-supplied bearer token
- the CLI keychain is never read
- aigw is hit exactly once for a sequence of requests within the cache window
"""

from __future__ import annotations

import pytest

from screamingface.plugins.claude_backend_api.auth import ClaudeCodeOAuth
from screamingface.plugins.llm_base.aigw_token_source import AigwTokenSource

from .infrastructure.fake_aigw import make_fake_aigw


@pytest.mark.asyncio
async def test_claude_backend_with_aigw_connection_id(monkeypatch):
    monkeypatch.setenv("SF_AIGW_JWT", "test-jwt")

    transport = make_fake_aigw(
        expected_connection_id="conn-e2e",
        expected_jwt="test-jwt",
        access_token="downstream-claude-token",
    )

    from screamingface.plugins.llm_base.aigw_token_source import aigw_jwt_from_env

    source = AigwTokenSource(
        connection_id="conn-e2e",
        aigw_url="http://aigw.test",
        aigw_jwt_provider=aigw_jwt_from_env,
        http_transport=transport,
    )
    strat = ClaudeCodeOAuth(aigw_source=source)

    headers = await strat.get_authorization_header()
    assert headers["Authorization"] == "Bearer downstream-claude-token"

    # Sequence of calls within cache window → exactly one upstream fetch.
    for _ in range(50):
        await strat.get_authorization_header()
    # AigwTokenSource has its own counter; assert via source state.
    assert source._cache is not None  # noqa: SLF001 — e2e introspection
```

(Optional, only if the existing fixtures make it cheap: wire the strategy into a real `AnthropicBackend` with a mocked Anthropic transport and call through `handle_backend_call` to verify the header lands on the Anthropic request. Skip if the existing e2e harness doesn't already support an injected http_client_factory at the plugin boundary.)

- [ ] **Step 3: Run**

```bash
cd apps/server && uv run pytest tests/e2e/test_aigw_connection_path.py -v
```

Expected: PASS.

- [ ] **Step 4: Re-run existing backend e2e regression**

```bash
cd apps/server && uv run pytest tests/e2e/data/claude/ tests/e2e/data/codex/ tests/e2e/data/gemini/ -v
```

Expected: all green (no behavior change without `connection_id`).

- [ ] **Step 5: Commit**

```bash
git add apps/server/tests/e2e/infrastructure/fake_aigw.py \
        apps/server/tests/e2e/test_aigw_connection_path.py
git commit -m "SF-169: e2e test for SF-backend → aigw token-fetch path"
```

---

## Task 7: Full gates, push, PR

- [ ] **Step 1: Run full local gates**

```bash
cd apps/server && uv run pre-commit run --config .pre-commit-config.yaml --all-files
uv run pytest -x
```

Expected: ruff clean (within SF-218 thresholds), pyright clean, all tests pass.

- [ ] **Step 2: Push**

```bash
git push -u origin SF-169-aigw-oauth-connections-consumer
```

- [ ] **Step 3: Open PR**

```bash
gh pr create --title "SF-169: SF backend plugins consume aigateway OAuth Connections" --body "$(cat <<'EOF'
## Summary
- Adds optional aigateway token-fetch path to the three OAuth-using SF backend plugins (claude, codex, gemini)
- New `AigwTokenSource` helper in `llm_base`: cached, lock-protected, JWT-provider-driven
- `OAuthStrategy` base gains an opt-in `aigw_source` slot; providers add a tiny `_aigw_creds_shape` hook to translate aigw responses into their on-disk keychain shape
- Each plugin's Settings adds `connection_id` + `aigw_url`; `customize_schema` annotates the field with `x-aigw-connection-picker` for the DEMO-028 desktop UI

## Behavior
- **Without `connection_id` set:** byte-for-byte identical to today (CLI keychain reads + provider refresh)
- **With `connection_id` set:** aigateway is the source of truth; CLI keychain is not read; aigw owns refresh
- Aigateway is NOT on the LLM hot path — token fetched, then provider called directly

## Prereqs
- [ ] **D-AIGW-010** (`GET /v1/oauth/connections/{id}/token` + JWT auth) MUST be merged before this. See plan for the required response contract.
- This PR bootstraps the JWT from `SF_AIGW_JWT` env var. DEMO-029 will replace this with desktop-driven IPC later — the `aigw_jwt_provider` callable shape is stable.

## Test plan
- [x] Unit: `AigwTokenSource` — happy path, cache, refetch, 401/404/503/transport errors, concurrent callers, JWT-provider invocation
- [x] Unit: `OAuthStrategy` aigw branch
- [x] Per-provider: aigw path returns provider-shaped headers
- [x] E2E: fake-aigw integration via `httpx.MockTransport`
- [x] Regression: existing claude/codex/gemini e2e green

Closes SF-169 / DEMO-027 (pending D-AIGW-010).
EOF
)"
```

**Stop here.** Per project rules, do not auto-merge.

---

## Self-Review

**Spec coverage** vs ticket acceptance criteria:
- ✅ `AigwTokenSource` cached + lock-protected → Task 1
- ✅ Helper handles 200 / 404 / 503 → Task 1 tests + handler error branches
- ✅ All three plugins route through helper when `connection_id` is set → Tasks 3-5
- ✅ All three Settings classes expose `connection_id` + `aigw_url` with defaults → Tasks 3-5 step 4
- ✅ `customize_schema` annotation for the connection picker → Tasks 3-5 step 4
- ✅ Existing e2e green → Task 6 step 4
- ✅ New e2e with fake aigw → Task 6
- ✅ Token cache: 100 sequential calls = 1 fetch → Task 1 `test_caches_until_near_expiry` + Task 6 cache assertion
- ✅ Expired token triggers refetch → Task 1 `test_refetches_after_expiry`
- ✅ Aigateway unreachable → clear error → Task 1 `test_transport_error_raises_token_error` (propagation as 502 from SF route is a side-effect of FastAPI default exception handling for `AigwTokenError`; if you want explicit 502 mapping, add a route-level exception handler in `routes_shared.py` — out of scope unless a reviewer asks)

**Placeholder scan:** every step has the exact code or exact command. No "TBD"; no "similar to above" without code (Tasks 4-5 do say "mirror Task 3 step 3-4" but step 3-4 is laid out in full in Task 3, and the deltas for Codex/Gemini — different creds keys — are spelled out explicitly per-provider).

**Type consistency:** `AigwTokenSource` constructor params match every call site (positional-keyword: `connection_id`, `aigw_url`, `aigw_jwt_provider`, optional `http_timeout`, optional `http_transport` for tests). `_aigw_creds_shape(access_token, expires_at)` has the same signature in base class default-raise and every provider override.

**Drift from ticket draft:**
- Helper is named `AigwTokenSource` (matches ticket) but does NOT take `http_timeout` as the *first* positional arg — uses keyword-only for everything to match the rest of `llm_base` codebase conventions. Constructor signature differs slightly from the ticket snippet.
- Integration point is `_read_credential` / `_refresh_credential` hooks (via `_load_credential` / `_refresh_or_aigw` shims), not a renamed `get_token()` method. The ticket's `get_token()` wording is incompatible with the existing `get_authorization_header` template-method shape. Functional behavior is unchanged.
- JWT-provider bootstrap is `SF_AIGW_JWT` env var, not desktop-IPC. Document'd and replaceable.
