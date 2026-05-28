# Superseded By SF-219

This historical plan describes an OS credential-store design for AIGateway. It is superseded by SF-219, which replaces AIGateway runtime credential storage with Tortoise-backed `ORMStore` and the `credential_blobs` table. Do not use this document to reintroduce OS credential storage under `apps/aigateway`.

# aigw-*-backend OAuth Authenticate button — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Authenticate button in the SF Backend Status panel for aigw-*-backend plugins that drives the user through the AI Gateway's OAuth flow (gateway already stores the resulting token).

**Architecture:** SF server gains two thin proxy routes (`POST <prefix>/auth/start`, `GET <prefix>/auth/status`) that forward to the aigateway's existing `/v1/auth/{provider}/...` endpoints. `AigwBackend.health()` probes profile status so the existing reauth-button machinery in `BackendStatusPanel` lights up. A new field `auth_kind: "cli" | "browser"` on `/backends/status` distinguishes the new browser-OAuth flow from the old CLI-spawn flow. Electron main gets an `oauth-launcher` service that calls start, opens the authorize URL via `shell.openExternal`, polls until AUTHENTICATED, and notifies the renderer.

**Tech Stack:** Python 3.12 / FastAPI / pytest / httpx (server side); TypeScript / Electron / React / Vitest (desktop side).

**Spec:** `docs/superpowers/specs/2026-05-07-aigw-backend-oauth-authenticate-button-design.md`

**Asana:** https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214600798519030

---

## File Structure

| File | Responsibility | New / Modified |
| --- | --- | --- |
| `apps/server/src/screamingface/plugins/aigw_base/auth_proxy_router.py` | `build_aigw_auth_proxy_router(...)` factory: `POST /auth/start`, `GET /auth/status` proxying to aigateway | NEW |
| `apps/server/src/screamingface/plugins/aigw_base/__init__.py` | Re-export the new factory | MODIFIED |
| `apps/server/src/screamingface/plugins/aigw_base/plugin_base.py` | Adds `gateway_provider: ClassVar[str \| None] = None` | MODIFIED |
| `apps/server/src/screamingface/plugins/aigw_base/backend.py` | Replace stub `health()` with gateway profile probe | MODIFIED |
| `apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py` | Unit tests for the auth-proxy factory (httpx MockTransport) | NEW |
| `apps/server/src/screamingface/plugins/aigw_base/tests/test_backend_health.py` | Unit tests for `AigwBackend.health()` | NEW |
| `apps/server/src/screamingface/plugins/aigw_claude_backend/plugin.py` | Sets `gateway_provider = "anthropic"` | MODIFIED |
| `apps/server/src/screamingface/plugins/aigw_claude_backend/routes.py` | Mounts the auth-proxy router | MODIFIED |
| `apps/server/src/screamingface/plugins/aigw_claude_backend/tests/test_auth_proxy_mount.py` | Plugin-level test confirming the routes are reachable | NEW |
| `apps/server/src/screamingface/plugins/llm_base/routes.py` | Adds `auth_kind: "cli" \| "browser"` to `/backends/status` entries | MODIFIED |
| `apps/server/src/screamingface/plugins/llm_base/tests/test_backends_status_auth_kind.py` | Unit test for the new field | NEW |
| `apps/server/tests/e2e/test_aigw_auth_e2e.py` | Subprocess-based integration tests covering 6 scenarios from the spec | NEW |
| `apps/desktop/src/main/services/oauth-launcher.ts` | OAuth launcher service: start, openExternal, poll, emit | NEW |
| `apps/desktop/src/main/services/__tests__/oauth-launcher.test.ts` | Unit tests for the launcher | NEW |
| `apps/desktop/src/main/ipc/backends.ts` (or equivalent) | New IPC channel `backends:authenticateOAuth` | MODIFIED |
| `apps/desktop/src/preload/index.ts` | Expose `window.electronAPI.backends.authenticateOAuth` | MODIFIED |
| `apps/desktop/src/renderer/src/components/server/BackendStatusPanel.tsx` | Wire `auth_kind === "browser"` to the new IPC method, "Waiting..." UI | MODIFIED |
| `apps/desktop/src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx` | Renderer tests covering both `cli` and `browser` paths | NEW |

---

## Task 1: Auth-proxy router factory — `POST /auth/start` happy path

**Files:**
- Create: `apps/server/src/screamingface/plugins/aigw_base/auth_proxy_router.py`
- Test: `apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py
"""Unit tests for the aigw auth-proxy router factory.

We mount the factory's router on a bare FastAPI app and use httpx
MockTransport to fake the upstream aigateway. Each test asserts that
the SF-side route forwards correctly and reshapes errors as documented
in docs/superpowers/specs/2026-05-07-aigw-backend-oauth-authenticate-button-design.md.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.aigw_base.auth_proxy_router import (
    build_aigw_auth_proxy_router,
)


def _make_client(handler) -> TestClient:
    """Mount the auth-proxy router onto a stub app, with a MockTransport gateway."""
    transport = httpx.MockTransport(handler)

    def http_factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    app = FastAPI()
    app.include_router(
        build_aigw_auth_proxy_router(
            path_prefix="/claude",
            gateway_url="http://gateway",
            gateway_provider="anthropic",
            profile_name="default",
            http_client_factory=http_factory,
        )
    )
    return TestClient(app)


def test_start_happy_path_passes_through_authorize_url() -> None:
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = req.read().decode() if req.content else ""
        return httpx.Response(
            201,
            json={
                "profile_id": "anthropic:default",
                "authorize_url": "https://provider/authorize?x=1",
                "state": "abc",
                "expires_in": 600,
            },
        )

    client = _make_client(handler)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["authorize_url"] == "https://provider/authorize?x=1"
    assert body["profile_id"] == "anthropic:default"
    assert body["state"] == "abc"
    assert body["expires_in"] == 600
    # Verify the SF route forwarded to the right gateway endpoint
    assert captured["url"] == "http://gateway/v1/auth/anthropic/profiles"
    assert '"name": "default"' in captured["body"] or "'name': 'default'" in captured["body"]
```

- [ ] **Step 2: Run test to verify it fails**

```
cd apps/server
uv run pytest src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py::test_start_happy_path_passes_through_authorize_url -v
```
Expected: `ModuleNotFoundError: No module named 'screamingface.plugins.aigw_base.auth_proxy_router'`

- [ ] **Step 3: Write the minimal implementation**

```python
# apps/server/src/screamingface/plugins/aigw_base/auth_proxy_router.py
"""Auth-proxy router for aigw-*-backend plugins.

Two routes per backend:

- ``POST {prefix}/auth/start`` — start an OAuth cycle; returns the
  upstream provider authorize URL.
- ``GET  {prefix}/auth/status`` — read the gateway-side profile state.

Both forward to the aigateway's ``/v1/auth/{provider}/...`` endpoints.
The SF server never sees the OAuth callback or the upstream token —
the gateway owns all credential state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

__all__ = ["build_aigw_auth_proxy_router"]


HttpClientFactory = Callable[[float], httpx.AsyncClient]


def _default_http_factory(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout))


def build_aigw_auth_proxy_router(
    *,
    path_prefix: str,
    gateway_url: str,
    gateway_provider: str,
    profile_name: str,
    http_client_factory: HttpClientFactory | None = None,
    timeout_seconds: float = 10.0,
) -> APIRouter:
    """Build the two SF-side proxy routes that drive the gateway OAuth flow."""
    router = APIRouter(tags=[f"{path_prefix.lstrip('/')}-auth"])
    base = gateway_url.rstrip("/")
    factory = http_client_factory or _default_http_factory

    @router.post(f"{path_prefix}/auth/start")
    async def start_auth() -> dict[str, Any]:
        url = f"{base}/v1/auth/{gateway_provider}/profiles"
        try:
            async with factory(timeout_seconds) as client:
                resp = await client.post(url, json={"name": profile_name})
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "gateway_unreachable",
                    "message": f"AI Gateway unreachable at {base}: {exc}",
                },
            ) from exc

        if resp.status_code >= 500:
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_error", "upstream_status": resp.status_code},
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))
        return resp.json()

    return router


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:500]}
```

- [ ] **Step 4: Run the test to verify it passes**

```
uv run pytest src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py::test_start_happy_path_passes_through_authorize_url -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add apps/server/src/screamingface/plugins/aigw_base/auth_proxy_router.py \
        apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py
git commit -m "feat(aigw-base): auth-proxy POST /auth/start happy path"
```

---

## Task 2: Auth-proxy `POST /auth/start` error paths

**Files:**
- Modify: `apps/server/src/screamingface/plugins/aigw_base/auth_proxy_router.py` (already covers the cases — these tests are guard rails)
- Test: `apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py`

- [ ] **Step 1: Add the failing tests (append to the existing file)**

```python
def test_start_gateway_5xx_becomes_502() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    client = _make_client(handler)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"]["code"] == "gateway_error"
    assert body["detail"]["upstream_status"] == 503


def test_start_gateway_unreachable_becomes_502() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    client = _make_client(handler)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 502
    body = resp.json()
    assert body["detail"]["code"] == "gateway_unreachable"
    assert "connection refused" in body["detail"]["message"].lower()


def test_start_gateway_4xx_passes_through() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "unknown_provider", "provider": "anthropic"})

    client = _make_client(handler)
    resp = client.post("/claude/auth/start")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "unknown_provider"
```

- [ ] **Step 2: Run the tests to verify they pass (logic already implemented in Task 1)**

```
uv run pytest src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py -v
```
Expected: 4 passed.

- [ ] **Step 3: Commit**

```
git add apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py
git commit -m "test(aigw-base): cover /auth/start error paths"
```

---

## Task 3: Auth-proxy `GET /auth/status`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/aigw_base/auth_proxy_router.py`
- Test: `apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py`

- [ ] **Step 1: Add the failing tests**

```python
def test_status_happy_path_passes_through() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == "http://gateway/v1/auth/anthropic/profiles/default/status"
        return httpx.Response(
            200,
            json={
                "state": "authenticated",
                "account_label": None,
                "last_refreshed_at": "2026-05-07T10:00:00+00:00",
            },
        )

    client = _make_client(handler)
    resp = client.get("/claude/auth/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "authenticated"
    assert body["last_refreshed_at"] == "2026-05-07T10:00:00+00:00"


def test_status_gateway_404_passes_through() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "profile_not_found"})

    client = _make_client(handler)
    resp = client.get("/claude/auth/status")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "profile_not_found"


def test_status_gateway_unreachable_becomes_502() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=req)

    client = _make_client(handler)
    resp = client.get("/claude/auth/status")
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "gateway_unreachable"
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py -v
```
Expected: 3 new tests FAIL with 404 (route not found).

- [ ] **Step 3: Add the `GET /auth/status` route**

In `auth_proxy_router.py`, just before `return router`, insert:

```python
    @router.get(f"{path_prefix}/auth/status")
    async def auth_status() -> dict[str, Any]:
        url = f"{base}/v1/auth/{gateway_provider}/profiles/{profile_name}/status"
        try:
            async with factory(timeout_seconds) as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "gateway_unreachable",
                    "message": f"AI Gateway unreachable at {base}: {exc}",
                },
            ) from exc

        if resp.status_code >= 500:
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_error", "upstream_status": resp.status_code},
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))
        return resp.json()
```

- [ ] **Step 4: Run all auth-proxy tests**

```
uv run pytest src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add apps/server/src/screamingface/plugins/aigw_base/auth_proxy_router.py \
        apps/server/src/screamingface/plugins/aigw_base/tests/test_auth_proxy.py
git commit -m "feat(aigw-base): auth-proxy GET /auth/status"
```

---

## Task 4: Mount auth-proxy in `aigw_claude_backend` + plugin-level test

**Files:**
- Modify: `apps/server/src/screamingface/plugins/aigw_base/__init__.py`
- Modify: `apps/server/src/screamingface/plugins/aigw_base/plugin_base.py`
- Modify: `apps/server/src/screamingface/plugins/aigw_claude_backend/plugin.py`
- Modify: `apps/server/src/screamingface/plugins/aigw_claude_backend/routes.py`
- Test: `apps/server/src/screamingface/plugins/aigw_claude_backend/tests/test_auth_proxy_mount.py`

- [ ] **Step 1: Write the failing plugin-level test**

```python
# apps/server/src/screamingface/plugins/aigw_claude_backend/tests/test_auth_proxy_mount.py
"""Confirms that the aigw-claude-backend plugin mounts the auth-proxy
routes at /claude/auth/{start,status} when its router is built.

We don't drive the upstream gateway here — that's covered by the
auth_proxy unit tests and the e2e test. This guard test only asserts
that the routes exist on the FastAPI app the plugin produces.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)


def test_aigw_claude_backend_mounts_auth_proxy_routes() -> None:
    app = FastAPI()
    settings = AigwClaudeBackendSettings()
    router = AigwClaudeBackendPlugin.create_router(settings, app=app)
    app.include_router(router)

    routes = {(r.methods, r.path) for r in app.routes if hasattr(r, "methods")}
    paths = {p for _, p in routes}
    assert "/claude/auth/start" in paths
    assert "/claude/auth/status" in paths


def test_aigw_claude_backend_declares_gateway_provider() -> None:
    assert AigwClaudeBackendPlugin.gateway_provider == "anthropic"
```

- [ ] **Step 2: Run the test to verify it fails**

```
uv run pytest src/screamingface/plugins/aigw_claude_backend/tests/test_auth_proxy_mount.py -v
```
Expected: both tests FAIL — `gateway_provider` attribute missing on plugin, and the auth routes are not registered.

- [ ] **Step 3: Add `gateway_provider` to the base + re-export the factory**

In `apps/server/src/screamingface/plugins/aigw_base/plugin_base.py`, add the class attribute:

```python
class AigwBackendApiPluginBase(BackendApiPluginBase):
    """Base class for every aigw_*_backend plugin."""

    tags: ClassVar[list[str]] = ["product:aigw"]
    depends: ClassVar[list[str]] = ["llm-base", "backend-api-base", "aigw-base"]
    conflicts: ClassVar[list[str]] = []
    # Provider key used by the AI Gateway (e.g. "anthropic", "openai").
    # Subclasses MUST set this if they want the auth-proxy router mounted.
    gateway_provider: ClassVar[str | None] = None

    def _make_interpreter(self, app: FastAPI):
        # ... unchanged
```

In `apps/server/src/screamingface/plugins/aigw_base/__init__.py`, append the re-export:

```python
from .auth_proxy_router import build_aigw_auth_proxy_router
from .backend import AigwBackend, AigwGatewayError
from .interpreter import AigwInterpreter
from .plugin_base import AigwBackendApiPluginBase
from .settings import AigwBackendApiSettingsBase

__all__ = [
    "AigwBackend",
    "AigwBackendApiPluginBase",
    "AigwBackendApiSettingsBase",
    "AigwGatewayError",
    "AigwInterpreter",
    "build_aigw_auth_proxy_router",
]
```

- [ ] **Step 4: Set `gateway_provider` on aigw_claude_backend and mount the router**

In `apps/server/src/screamingface/plugins/aigw_claude_backend/plugin.py`, inside `class AigwClaudeBackendPlugin(...)` add:

```python
    gateway_provider = "anthropic"
```

In `apps/server/src/screamingface/plugins/aigw_claude_backend/routes.py`, modify `create_router`:

```python
from screamingface.plugins.aigw_base import (
    AigwBackend,
    AigwInterpreter,
    build_aigw_auth_proxy_router,
)

# ... existing imports ...

_DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"


def create_router(settings: AigwClaudeBackendSettings, app: Any = None) -> APIRouter:
    backend = AigwBackend(
        gateway_url=settings.gateway_url,
        profile_name=settings.auth_profile,
    )

    def build_interpreter() -> Any:
        return AigwInterpreter(app=app, settings=settings, backend=backend)

    router = build_backend_api_router(
        BackendApiConfig(
            name="aigw-claude-backend",
            path_prefix="/claude",
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="aigw_claude",
        )
    )
    router.include_router(
        build_aigw_auth_proxy_router(
            path_prefix="/claude",
            gateway_url=settings.gateway_url,
            gateway_provider="anthropic",
            profile_name=settings.auth_profile,
        )
    )
    return router
```

- [ ] **Step 5: Run the plugin tests**

```
uv run pytest src/screamingface/plugins/aigw_claude_backend/tests/ -v
```
Expected: all pass (including the two new ones).

- [ ] **Step 6: Commit**

```
git add apps/server/src/screamingface/plugins/aigw_base/__init__.py \
        apps/server/src/screamingface/plugins/aigw_base/plugin_base.py \
        apps/server/src/screamingface/plugins/aigw_claude_backend/plugin.py \
        apps/server/src/screamingface/plugins/aigw_claude_backend/routes.py \
        apps/server/src/screamingface/plugins/aigw_claude_backend/tests/test_auth_proxy_mount.py
git commit -m "feat(aigw-claude-backend): mount auth-proxy routes; declare gateway_provider"
```

---

## Task 5: `AigwBackend.health()` probes gateway profile status

**Files:**
- Modify: `apps/server/src/screamingface/plugins/aigw_base/backend.py`
- Test: `apps/server/src/screamingface/plugins/aigw_base/tests/test_backend_health.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/server/src/screamingface/plugins/aigw_base/tests/test_backend_health.py
"""Unit tests for AigwBackend.health() — gateway profile-state probe.

We mock the upstream gateway with httpx.MockTransport. Each test asserts
that a given gateway response maps to the documented HealthStatus.
"""

from __future__ import annotations

import httpx
import pytest

from screamingface.plugins.aigw_base.backend import AigwBackend


def _backend(handler) -> AigwBackend:
    transport = httpx.MockTransport(handler)

    def factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    return AigwBackend(
        gateway_url="http://gateway",
        profile_name="default",
        http_client_factory=factory,
    )


@pytest.mark.asyncio
async def test_health_authenticated_when_profile_is_authenticated() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        # Health probes the gateway's *anthropic* profile by default
        assert "/v1/auth/anthropic/profiles/default/status" in str(req.url)
        return httpx.Response(
            200,
            json={"state": "authenticated", "account_label": None, "last_refreshed_at": None},
        )

    status = await _backend(handler).health()
    assert status.authenticated is True
    assert status.error is None


@pytest.mark.asyncio
async def test_health_not_authenticated_when_profile_is_pending() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"state": "pending"})

    status = await _backend(handler).health()
    assert status.authenticated is False
    assert "OAuth in progress" in (status.error or "")


@pytest.mark.asyncio
async def test_health_not_authenticated_when_profile_is_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"state": "error"})

    status = await _backend(handler).health()
    assert status.authenticated is False
    assert "error" in (status.error or "").lower()


@pytest.mark.asyncio
async def test_health_not_authenticated_when_profile_404() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "profile_not_found"})

    status = await _backend(handler).health()
    assert status.authenticated is False
    assert "not yet created" in (status.error or "").lower()


@pytest.mark.asyncio
async def test_health_not_authenticated_when_gateway_unreachable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    status = await _backend(handler).health()
    assert status.authenticated is False
    assert "unreachable" in (status.error or "").lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

```
uv run pytest src/screamingface/plugins/aigw_base/tests/test_backend_health.py -v
```
Expected: all 5 FAIL — `health()` currently returns the inherited stub
(`authenticated=False, error="health() not implemented"`), so most assertions miss. The first one (authenticated case) fails outright.

- [ ] **Step 3: Replace `AigwBackend.health()`**

Currently `AigwBackend` inherits `Backend.health()` (the stub). Add a real `health` method to `AigwBackend` in `apps/server/src/screamingface/plugins/aigw_base/backend.py` (insert after `__init__`, before `run`). We also need the gateway provider — derive it from the configured backend at construction time. Add a constructor parameter, default `"anthropic"`:

```python
    def __init__(
        self,
        *,
        gateway_url: str = "http://127.0.0.1:9105",
        profile_name: str = "default",
        gateway_provider: str = "anthropic",
        http_client_factory=None,
    ) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._profile_name = profile_name
        self._gateway_provider = gateway_provider
        self._http_factory = http_client_factory or (
            lambda timeout: httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        )

    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        url = (
            f"{self._gateway_url}/v1/auth/{self._gateway_provider}"
            f"/profiles/{self._profile_name}/status"
        )
        try:
            async with self._http_factory(10.0) as client:
                resp = await client.get(url)
        except httpx.RequestError as exc:
            return HealthStatus(
                authenticated=False, error=f"AI Gateway unreachable: {exc}"
            )

        if resp.status_code == 404:
            return HealthStatus(
                authenticated=False, error="Profile not yet created at gateway"
            )
        if resp.status_code >= 500:
            return HealthStatus(
                authenticated=False,
                error=f"Gateway error (HTTP {resp.status_code})",
            )
        if resp.status_code >= 400:
            return HealthStatus(
                authenticated=False, error=f"Gateway HTTP {resp.status_code}"
            )
        body = resp.json() if resp.content else {}
        state = (body.get("state") or "").lower()
        if state == "authenticated":
            return HealthStatus(authenticated=True)
        if state == "pending":
            return HealthStatus(authenticated=False, error="OAuth in progress")
        if state == "error":
            return HealthStatus(authenticated=False, error="Profile in error state")
        return HealthStatus(authenticated=False, error=f"Unknown profile state: {state!r}")
```

You also need to import `HealthStatus`:

```python
from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
```

(Adjust the existing `from .backend_base import Backend` line.)

- [ ] **Step 4: Pass `gateway_provider` through from `aigw_claude_backend/routes.py`**

In `apps/server/src/screamingface/plugins/aigw_claude_backend/routes.py`, update the backend construction inside `create_router`:

```python
    backend = AigwBackend(
        gateway_url=settings.gateway_url,
        profile_name=settings.auth_profile,
        gateway_provider="anthropic",
    )
```

- [ ] **Step 5: Run health tests**

```
uv run pytest src/screamingface/plugins/aigw_base/tests/test_backend_health.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Run the full aigw test suite — guard against regressions**

```
uv run pytest src/screamingface/plugins/aigw_base src/screamingface/plugins/aigw_claude_backend -v
```
Expected: all pass (existing tests still green).

- [ ] **Step 7: Commit**

```
git add apps/server/src/screamingface/plugins/aigw_base/backend.py \
        apps/server/src/screamingface/plugins/aigw_base/tests/test_backend_health.py \
        apps/server/src/screamingface/plugins/aigw_claude_backend/routes.py
git commit -m "feat(aigw-base): AigwBackend.health() probes gateway profile status"
```

---

## Task 6: `auth_kind` field on `/backends/status`

**Files:**
- Modify: `apps/server/src/screamingface/plugins/llm_base/routes.py`
- Test: `apps/server/src/screamingface/plugins/llm_base/tests/test_backends_status_auth_kind.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/server/src/screamingface/plugins/llm_base/tests/test_backends_status_auth_kind.py
"""Tests for the auth_kind field on the /backends/status payload.

Plugins that declare ``gateway_provider`` get auth_kind="browser"; all
others (CLI-spawn flow) get auth_kind="cli".
"""

from __future__ import annotations

from screamingface.plugins.llm_base.routes import _classify_auth_kind


class _CliPlugin:
    name = "claude-backend-api"
    backend_call_paths = ["/claude"]


class _BrowserPlugin:
    name = "aigw-claude-backend"
    backend_call_paths = ["/claude"]
    gateway_provider = "anthropic"


def test_auth_kind_browser_when_plugin_has_gateway_provider() -> None:
    assert _classify_auth_kind(_BrowserPlugin) == "browser"


def test_auth_kind_cli_when_plugin_lacks_gateway_provider() -> None:
    assert _classify_auth_kind(_CliPlugin) == "cli"


def test_auth_kind_cli_when_gateway_provider_is_none() -> None:
    class _P:
        gateway_provider = None

    assert _classify_auth_kind(_P) == "cli"
```

- [ ] **Step 2: Run the test to verify it fails**

```
uv run pytest src/screamingface/plugins/llm_base/tests/test_backends_status_auth_kind.py -v
```
Expected: `ImportError: cannot import name '_classify_auth_kind'`.

- [ ] **Step 3: Add `_classify_auth_kind` and wire it into the route**

In `apps/server/src/screamingface/plugins/llm_base/routes.py`, near the other classifier helpers:

```python
def _classify_auth_kind(plugin: Any) -> str:
    """Tells the UI which auth flow to drive when action == 'reauth'.

    - ``"browser"`` — open the gateway-managed authorize URL in a browser
      (used by aigw-*-backend plugins via ``gateway_provider``).
    - ``"cli"``     — spawn a terminal running the plugin's CLI auth
      command (the historical claude/codex/gemini path).
    """
    if getattr(plugin, "gateway_provider", None):
        return "browser"
    return "cli"
```

Then in the `backends_status` endpoint, after `health["help_text"] = _help_text(name, health)`, add one more line:

```python
            health["auth_kind"] = _classify_auth_kind(plugin)
```

- [ ] **Step 4: Run the new test plus the existing routes tests**

```
uv run pytest src/screamingface/plugins/llm_base/ -v
```
Expected: all pass; the three new tests included.

- [ ] **Step 5: Commit**

```
git add apps/server/src/screamingface/plugins/llm_base/routes.py \
        apps/server/src/screamingface/plugins/llm_base/tests/test_backends_status_auth_kind.py
git commit -m "feat(llm-base): add auth_kind field to /backends/status"
```

---

## Task 7: End-to-end integration tests (aigateway subprocess + fake provider)

**Files:**
- Test: `apps/server/tests/e2e/test_aigw_auth_e2e.py`

This task uses the existing subprocess pattern from `apps/server/tests/e2e/test_aigw_claude_e2e.py`. We boot a real aigateway with a fake in-memory credential store + a fake Anthropic OAuth server. We exercise the SF auth-proxy + gateway through real HTTP.

- [ ] **Step 1: Write the integration test scaffolding**

```python
# apps/server/tests/e2e/test_aigw_auth_e2e.py
"""End-to-end: SF aigw-claude-backend auth-proxy ↔ real aigateway.

Boots a real aigateway subprocess with:
- a fake in-memory credential store (no real OS credential store)
- a fake Anthropic OAuth provider via httpx MockTransport injected
  through ``app.state.anthropic_http_factory``

Drives the full OAuth cycle through the SF endpoints and asserts that
the SF auth-proxy + gateway combination behaves as documented in
docs/superpowers/specs/2026-05-07-aigw-backend-oauth-authenticate-button-design.md.

This test does NOT open a browser; it simulates the browser by issuing
the callback request directly to the gateway, which is exactly what
the real Electron flow does (the browser hits the gateway's callback
URL directly — the SF server is never on the OAuth callback path).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def aigw_subprocess(tmp_path) -> Iterator[dict]:
    """Boot a real aigateway with a fake credential store + fake Anthropic OAuth."""
    port = _free_port()
    env = os.environ.copy()
    env["AIGATEWAY_PORT"] = str(port)
    env["AIGATEWAY_FAKE_CREDENTIAL_STORE"] = "1"
    env["AIGATEWAY_FAKE_ANTHROPIC_OAUTH"] = "1"
    env["AIGATEWAY_CREDENTIAL_STORE_FILE"] = str(tmp_path / "fake-kc.json")

    proc = subprocess.Popen(
        [sys.executable, "-m", "aigateway"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(Path(__file__).resolve().parents[3] / "aigateway"),
        text=True,
    )

    # Wait for /healthz
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1)
            if r.status_code == 200:
                break
        except httpx.RequestError:
            time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("aigateway failed to start")

    try:
        yield {"port": port, "proc": proc}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
```

NOTE: The harness above relies on two env-driven test-only switches in
`apps/aigateway/src/aigateway/main.py` — `AIGATEWAY_FAKE_CREDENTIAL_STORE` and
`AIGATEWAY_FAKE_ANTHROPIC_OAUTH`. These must be added in the same task
(see Step 2 below) before the fixture works.

- [ ] **Step 2: Add the test-only switches to aigateway**

In `apps/aigateway/src/aigateway/main.py`, near the top of `create_app`, after `registry = ProviderRegistry()`:

```python
    if os.getenv("AIGATEWAY_FAKE_CREDENTIAL_STORE") == "1":
        from .core.credential_store import InMemoryCredentialStore
        from .core import credential_store as cs_mod

        kc_path = os.getenv("AIGATEWAY_CREDENTIAL_STORE_FILE")
        store = InMemoryCredentialStore(persist_path=kc_path)
        cs_mod._fake_singleton = store  # type: ignore[attr-defined]

    if os.getenv("AIGATEWAY_FAKE_ANTHROPIC_OAUTH") == "1":
        from httpx import MockTransport

        def _fake_handler(req):
            import httpx as _h

            # Token-exchange endpoint
            if req.url.host == "console.anthropic.com" and req.url.path.endswith("/oauth/token"):
                return _h.Response(
                    200,
                    json={
                        "access_token": "fake-tok",
                        "refresh_token": "fake-rt",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    },
                )
            return _h.Response(404, json={"error": "unmapped"})

        def _factory(timeout=None):
            return _h.AsyncClient(transport=MockTransport(_fake_handler), timeout=timeout)

        app.state.anthropic_http_factory = _factory  # noqa: PLW0644
```

(The exact import paths for `InMemoryCredentialStore` may need a small
adapter; if `credential_store.py` doesn't already expose an in-memory
variant, add one — a thin dict-backed `CredentialStore` with optional
JSON persistence. Keep it under 30 lines.)

- [ ] **Step 3: Add scenario 1 — happy path full cycle**

```python
def test_full_oauth_cycle_via_sf_auth_proxy(aigw_subprocess) -> None:
    """SF /claude/auth/start → gateway PENDING → simulated callback →
    SF /claude/auth/status → AUTHENTICATED → SF /claude/health green."""
    gw_port = aigw_subprocess["port"]
    # Stand up an in-process SF FastAPI app with the aigw-claude-backend
    # router mounted, pointed at the real aigateway.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from screamingface.plugins.aigw_claude_backend.plugin import (
        AigwClaudeBackendPlugin,
        AigwClaudeBackendSettings,
    )

    settings = AigwClaudeBackendSettings(gateway_url=f"http://127.0.0.1:{gw_port}")
    app = FastAPI()
    app.include_router(AigwClaudeBackendPlugin.create_router(settings, app=app))
    sf = TestClient(app)

    # 1. SF /claude/auth/start → gateway PENDING
    resp = sf.post("/claude/auth/start")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["profile_id"] == "anthropic:default"
    assert body["authorize_url"].startswith("https://")
    state = body["state"]

    # 2. SF /claude/auth/status → pending
    s = sf.get("/claude/auth/status").json()
    assert s["state"] == "pending"

    # 3. Simulate browser callback (the real browser would do this directly)
    cb = httpx.get(
        f"http://127.0.0.1:{gw_port}/v1/auth/anthropic/callback",
        params={"code": "fake-code", "state": state},
    )
    assert cb.status_code == 200, cb.text

    # 4. SF /claude/auth/status → AUTHENTICATED
    s = sf.get("/claude/auth/status").json()
    assert s["state"] == "authenticated"

    # 5. SF /claude/health → authenticated:true
    h = sf.get("/claude/health")
    assert h.status_code == 200
    assert h.json()["authenticated"] is True
```

- [ ] **Step 4: Add scenario 2 — idempotent re-start**

```python
def test_restart_authenticated_profile_yields_fresh_authorize_url(aigw_subprocess) -> None:
    gw_port = aigw_subprocess["port"]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from screamingface.plugins.aigw_claude_backend.plugin import (
        AigwClaudeBackendPlugin,
        AigwClaudeBackendSettings,
    )

    settings = AigwClaudeBackendSettings(gateway_url=f"http://127.0.0.1:{gw_port}")
    app = FastAPI()
    app.include_router(AigwClaudeBackendPlugin.create_router(settings, app=app))
    sf = TestClient(app)

    # Authenticate once
    state = sf.post("/claude/auth/start").json()["state"]
    httpx.get(
        f"http://127.0.0.1:{gw_port}/v1/auth/anthropic/callback",
        params={"code": "c1", "state": state},
    )
    assert sf.get("/claude/auth/status").json()["state"] == "authenticated"

    # Re-start: must get a NEW authorize_url + transition back to pending
    body = sf.post("/claude/auth/start").json()
    assert body["state"] != state
    assert sf.get("/claude/auth/status").json()["state"] == "pending"
```

- [ ] **Step 5: Add scenario 3 — state mismatch on callback**

```python
def test_callback_with_wrong_state_does_not_authenticate(aigw_subprocess) -> None:
    gw_port = aigw_subprocess["port"]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from screamingface.plugins.aigw_claude_backend.plugin import (
        AigwClaudeBackendPlugin,
        AigwClaudeBackendSettings,
    )

    settings = AigwClaudeBackendSettings(gateway_url=f"http://127.0.0.1:{gw_port}")
    app = FastAPI()
    app.include_router(AigwClaudeBackendPlugin.create_router(settings, app=app))
    sf = TestClient(app)

    sf.post("/claude/auth/start")
    cb = httpx.get(
        f"http://127.0.0.1:{gw_port}/v1/auth/anthropic/callback",
        params={"code": "c", "state": "definitely-wrong"},
    )
    assert cb.status_code == 400
    assert sf.get("/claude/auth/status").json()["state"] == "pending"
```

- [ ] **Step 6: Add scenario 4 — token exchange fails at upstream**

For this one we override the fake Anthropic handler to return 400. Add an env
switch `AIGATEWAY_FAKE_ANTHROPIC_OAUTH_FAIL=1` checked alongside the existing
fake handler:

```python
            if req.url.host == "console.anthropic.com" and req.url.path.endswith("/oauth/token"):
                if os.getenv("AIGATEWAY_FAKE_ANTHROPIC_OAUTH_FAIL") == "1":
                    return _h.Response(400, json={"error": "invalid_grant"})
                return _h.Response(200, json={...as before...})
```

Then add a fixture variant that boots the gateway with that env set:

```python
@pytest.fixture
def aigw_subprocess_failing(tmp_path):
    port = _free_port()
    env = os.environ.copy()
    env["AIGATEWAY_PORT"] = str(port)
    env["AIGATEWAY_FAKE_CREDENTIAL_STORE"] = "1"
    env["AIGATEWAY_FAKE_ANTHROPIC_OAUTH"] = "1"
    env["AIGATEWAY_FAKE_ANTHROPIC_OAUTH_FAIL"] = "1"
    env["AIGATEWAY_CREDENTIAL_STORE_FILE"] = str(tmp_path / "fake-kc.json")
    proc = subprocess.Popen(
        [sys.executable, "-m", "aigateway"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(Path(__file__).resolve().parents[3] / "aigateway"),
        text=True,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1)
            if r.status_code == 200:
                break
        except httpx.RequestError:
            time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("aigateway failed to start")
    try:
        yield {"port": port, "proc": proc}
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_callback_when_token_exchange_fails_marks_profile_error(aigw_subprocess_failing) -> None:
    gw_port = aigw_subprocess_failing["port"]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from screamingface.plugins.aigw_claude_backend.plugin import (
        AigwClaudeBackendPlugin,
        AigwClaudeBackendSettings,
    )

    settings = AigwClaudeBackendSettings(gateway_url=f"http://127.0.0.1:{gw_port}")
    app = FastAPI()
    app.include_router(AigwClaudeBackendPlugin.create_router(settings, app=app))
    sf = TestClient(app)

    state = sf.post("/claude/auth/start").json()["state"]
    cb = httpx.get(
        f"http://127.0.0.1:{gw_port}/v1/auth/anthropic/callback",
        params={"code": "c", "state": state},
    )
    assert cb.status_code >= 400
    s = sf.get("/claude/auth/status").json()
    assert s["state"] in ("error", "pending")  # gateway may use either, both are non-authenticated
```

- [ ] **Step 7: Add scenario 5 — gateway down at start**

```python
def test_start_when_gateway_is_down_returns_502(tmp_path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from screamingface.plugins.aigw_claude_backend.plugin import (
        AigwClaudeBackendPlugin,
        AigwClaudeBackendSettings,
    )

    # Pick a port nothing is listening on
    port = _free_port()
    settings = AigwClaudeBackendSettings(gateway_url=f"http://127.0.0.1:{port}")
    app = FastAPI()
    app.include_router(AigwClaudeBackendPlugin.create_router(settings, app=app))
    sf = TestClient(app)

    resp = sf.post("/claude/auth/start")
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "gateway_unreachable"
```

- [ ] **Step 8: Add scenario 6 — profile not yet created**

```python
def test_status_before_first_start_returns_404(aigw_subprocess) -> None:
    gw_port = aigw_subprocess["port"]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from screamingface.plugins.aigw_claude_backend.plugin import (
        AigwClaudeBackendPlugin,
        AigwClaudeBackendSettings,
    )

    settings = AigwClaudeBackendSettings(gateway_url=f"http://127.0.0.1:{gw_port}")
    app = FastAPI()
    app.include_router(AigwClaudeBackendPlugin.create_router(settings, app=app))
    sf = TestClient(app)

    s = sf.get("/claude/auth/status")
    assert s.status_code == 404

    h = sf.get("/claude/health")
    assert h.status_code == 503
    assert h.json()["authenticated"] is False
```

- [ ] **Step 9: Run the integration suite**

```
cd apps/server
uv run pytest tests/e2e/test_aigw_auth_e2e.py -v --timeout=60
```
Expected: 6 passed.

- [ ] **Step 10: Commit**

```
git add apps/aigateway/src/aigateway/main.py \
        apps/aigateway/src/aigateway/core/credential_store.py \
        apps/server/tests/e2e/test_aigw_auth_e2e.py
git commit -m "test(aigw): e2e integration covering full OAuth cycle through SF proxy"
```

---

## Task 8: Electron `oauth-launcher` service + IPC channel

**Files:**
- Create: `apps/desktop/src/main/services/oauth-launcher.ts`
- Create: `apps/desktop/src/main/services/__tests__/oauth-launcher.test.ts`
- Modify: `apps/desktop/src/main/ipc/backends.ts` (or wherever `backends:authenticate` is registered — search for it first)
- Modify: `apps/desktop/src/preload/index.ts`
- Modify: `apps/desktop/src/preload/index.d.ts` (the type declarations that ship `window.electronAPI.backends`)

- [ ] **Step 1: Locate the existing `backends:authenticate` IPC handler**

```
cd /Users/sergey/work/openmind/screamingface
rg -n "backends:authenticate|electronAPI\.backends" apps/desktop/src apps/desktop/types 2>&1 | head -30
```
Note the file path that registers `backends:authenticate` and the
preload declaration. Use those locations for the parallel
`backends:authenticateOAuth` registration.

- [ ] **Step 2: Write the failing launcher unit test**

```ts
// apps/desktop/src/main/services/__tests__/oauth-launcher.test.ts
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

// Hoisted mock of electron — must be declared before importing the SUT
const openExternal = vi.fn(async () => {});
vi.mock("electron", () => ({ shell: { openExternal } }));

import { runOAuthLauncher } from "../oauth-launcher";

beforeEach(() => {
  openExternal.mockClear();
});
afterEach(() => {
  vi.useRealTimers();
});

function makeFetch(responses: Array<() => Response>) {
  const seq = [...responses];
  return vi.fn(async () => {
    const next = seq.shift();
    if (!next) throw new Error("fetch called more times than mocked");
    return next();
  });
}

describe("runOAuthLauncher", () => {
  it("opens the authorize URL and resolves on AUTHENTICATED status", async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(
          JSON.stringify({ authorize_url: "https://x/authorize", state: "s1" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      () =>
        new Response(JSON.stringify({ state: "pending" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      () =>
        new Response(JSON.stringify({ state: "authenticated" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    ]);

    const result = await runOAuthLauncher({
      sfBaseUrl: "http://127.0.0.1:1234",
      backendName: "claude",
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });

    expect(openExternal).toHaveBeenCalledWith("https://x/authorize");
    expect(result.kind).toBe("complete");
  });

  it("returns timeout when status never reaches authenticated", async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(
          JSON.stringify({ authorize_url: "https://x/authorize", state: "s1" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ...Array(20).fill(
        () =>
          new Response(JSON.stringify({ state: "pending" }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
      ),
    ]);

    const result = await runOAuthLauncher({
      sfBaseUrl: "http://127.0.0.1:1234",
      backendName: "claude",
      pollIntervalMs: 1,
      timeoutMs: 10,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    expect(result.kind).toBe("failed");
    if (result.kind === "failed") expect(result.reason).toBe("timeout");
  });

  it("short-circuits to provider_error when status is error", async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(
          JSON.stringify({ authorize_url: "https://x/authorize", state: "s1" }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      () =>
        new Response(JSON.stringify({ state: "error", error: "bad code" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    ]);
    const result = await runOAuthLauncher({
      sfBaseUrl: "http://127.0.0.1:1234",
      backendName: "claude",
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    expect(result.kind).toBe("failed");
    if (result.kind === "failed") expect(result.reason).toBe("provider_error");
  });

  it("returns gateway_error when /auth/start returns 502", async () => {
    const fetchMock = makeFetch([
      () =>
        new Response(JSON.stringify({ detail: { code: "gateway_unreachable" } }), {
          status: 502,
          headers: { "content-type": "application/json" },
        }),
    ]);
    const result = await runOAuthLauncher({
      sfBaseUrl: "http://127.0.0.1:1234",
      backendName: "claude",
      pollIntervalMs: 1,
      timeoutMs: 5_000,
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    expect(openExternal).not.toHaveBeenCalled();
    expect(result.kind).toBe("failed");
    if (result.kind === "failed") expect(result.reason).toBe("gateway_error");
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```
cd apps/desktop
npx vitest run src/main/services/__tests__/oauth-launcher.test.ts
```
Expected: ENOENT or `Cannot find module ../oauth-launcher`.

- [ ] **Step 4: Implement the launcher**

```ts
// apps/desktop/src/main/services/oauth-launcher.ts
import { shell } from "electron";

export type LauncherResult =
  | { kind: "complete" }
  | {
      kind: "failed";
      reason: "timeout" | "gateway_error" | "provider_error" | "network_error";
      message?: string;
    };

export interface LauncherOptions {
  sfBaseUrl: string;
  backendName: string;
  pollIntervalMs?: number;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export async function runOAuthLauncher(opts: LauncherOptions): Promise<LauncherResult> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const pollIntervalMs = opts.pollIntervalMs ?? 2000;
  const timeoutMs = opts.timeoutMs ?? 10 * 60 * 1000;
  const startUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/start`;
  const statusUrl = `${opts.sfBaseUrl}/${opts.backendName}/auth/status`;

  let startResp: Response;
  try {
    startResp = await fetchImpl(startUrl, { method: "POST" });
  } catch (e) {
    return { kind: "failed", reason: "network_error", message: String(e) };
  }
  if (startResp.status >= 500 || startResp.status === 502) {
    return {
      kind: "failed",
      reason: "gateway_error",
      message: `start returned ${startResp.status}`,
    };
  }
  if (!startResp.ok) {
    return {
      kind: "failed",
      reason: "gateway_error",
      message: `start returned ${startResp.status}`,
    };
  }
  const startBody = (await startResp.json()) as { authorize_url: string };
  await shell.openExternal(startBody.authorize_url);

  const deadline = Date.now() + timeoutMs;
  let networkBlips = 0;
  while (Date.now() < deadline) {
    let statusResp: Response;
    try {
      statusResp = await fetchImpl(statusUrl);
    } catch {
      networkBlips += 1;
      if (networkBlips >= 5) {
        return { kind: "failed", reason: "network_error" };
      }
      await sleep(pollIntervalMs);
      continue;
    }
    networkBlips = 0;
    if (statusResp.status === 404) {
      // profile vanished — treat as gateway error
      return { kind: "failed", reason: "gateway_error", message: "profile not found" };
    }
    if (!statusResp.ok) {
      return {
        kind: "failed",
        reason: "gateway_error",
        message: `status returned ${statusResp.status}`,
      };
    }
    const body = (await statusResp.json()) as { state: string; error?: string };
    if (body.state === "authenticated") return { kind: "complete" };
    if (body.state === "error") {
      return { kind: "failed", reason: "provider_error", message: body.error };
    }
    await sleep(pollIntervalMs);
  }
  return { kind: "failed", reason: "timeout" };
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
```

- [ ] **Step 5: Run the launcher tests**

```
cd apps/desktop
npx vitest run src/main/services/__tests__/oauth-launcher.test.ts
```
Expected: 4 passed.

- [ ] **Step 6: Wire the IPC handler**

In the IPC registration file (located in Step 1; e.g. `apps/desktop/src/main/ipc/backends.ts`), add a parallel handler beside the existing `backends:authenticate`:

```ts
import { ipcMain } from "electron";
import { runOAuthLauncher } from "../services/oauth-launcher";

ipcMain.handle("backends:authenticateOAuth", async (_event, name: string) => {
  // sfBaseUrl: read from wherever the renderer's existing /backends/status
  // calls compute it. Reuse the same helper rather than re-deriving here.
  const sfBaseUrl = getSfBaseUrl(); // existing helper
  const result = await runOAuthLauncher({ sfBaseUrl, backendName: name });
  return result;
});
```

(Use whatever existing helper produces the SF base URL; if there isn't one, hard-code `http://127.0.0.1:8000` for the first cut and refactor later — confirmed acceptable per the spec's MVP scope.)

- [ ] **Step 7: Expose on preload**

In `apps/desktop/src/preload/index.ts`, beside the existing `authenticate` export under `backends`:

```ts
authenticateOAuth: (name: string) => ipcRenderer.invoke("backends:authenticateOAuth", name),
```

In `apps/desktop/src/preload/index.d.ts` (or whichever file types `electronAPI.backends`):

```ts
backends: {
  // ...existing fields...
  authenticateOAuth: (name: string) =>
    Promise<
      | { kind: "complete" }
      | {
          kind: "failed";
          reason: "timeout" | "gateway_error" | "provider_error" | "network_error";
          message?: string;
        }
    >;
};
```

- [ ] **Step 8: Run the full desktop test suite**

```
cd apps/desktop
npx vitest run
```
Expected: existing tests pass, 4 new ones pass.

- [ ] **Step 9: Commit**

```
git add apps/desktop/src/main/services/oauth-launcher.ts \
        apps/desktop/src/main/services/__tests__/oauth-launcher.test.ts \
        apps/desktop/src/main/ipc/backends.ts \
        apps/desktop/src/preload/index.ts \
        apps/desktop/src/preload/index.d.ts
git commit -m "feat(desktop): backends:authenticateOAuth IPC + oauth-launcher service"
```

---

## Task 9: BackendStatusPanel — wire `auth_kind === "browser"` to the launcher

**Files:**
- Modify: `apps/desktop/src/renderer/src/components/server/BackendStatusPanel.tsx`
- Create: `apps/desktop/src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx`

- [ ] **Step 1: Write the failing renderer test**

```tsx
// apps/desktop/src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const authenticate = vi.fn();
const authenticateOAuth = vi.fn(async () => ({ kind: "complete" }));
const getStatus = vi.fn(async () => ({}));
const onStatusChanged = vi.fn(() => () => {});
const onAlert = vi.fn(() => () => {});

(window as any).electronAPI = {
  backends: { authenticate, authenticateOAuth, getStatus, onStatusChanged, onAlert },
};

import { BackendStatusPanel } from "../BackendStatusPanel";

beforeEach(() => {
  authenticate.mockClear();
  authenticateOAuth.mockClear();
  getStatus.mockResolvedValue({
    claude: {
      authenticated: false,
      action: "reauth",
      auth_kind: "browser",
      cli_command: null,
      help_text: "Sign in via browser",
      model: "anthropic/claude-sonnet-4-5",
    },
  });
});

describe("BackendStatusPanel auth_kind=browser", () => {
  it("renders an Authenticate button that calls authenticateOAuth", async () => {
    render(<BackendStatusPanel />);
    const btn = await screen.findByRole("button", { name: /Authenticate/i });
    fireEvent.click(btn);
    await waitFor(() => expect(authenticateOAuth).toHaveBeenCalledWith("claude"));
    expect(authenticate).not.toHaveBeenCalled();
  });

  it("shows Waiting... while launcher is in flight", async () => {
    let resolve: (v: any) => void = () => {};
    authenticateOAuth.mockImplementationOnce(
      () => new Promise((r) => (resolve = r)),
    );
    render(<BackendStatusPanel />);
    const btn = await screen.findByRole("button", { name: /Authenticate/i });
    fireEvent.click(btn);
    expect(await screen.findByText(/Waiting for browser/i)).toBeInTheDocument();
    resolve({ kind: "complete" });
  });
});

describe("BackendStatusPanel auth_kind=cli (regression)", () => {
  it("still calls authenticate(name) for CLI backends", async () => {
    getStatus.mockResolvedValue({
      claude: {
        authenticated: false,
        action: "reauth",
        auth_kind: "cli",
        cli_command: "claude auth login",
        help_text: "...",
        model: "anthropic/claude-sonnet-4-5",
      },
    });
    render(<BackendStatusPanel />);
    const btn = await screen.findByRole("button", { name: /Re-authenticate/i });
    fireEvent.click(btn);
    await waitFor(() => expect(authenticate).toHaveBeenCalledWith("claude"));
    expect(authenticateOAuth).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```
cd apps/desktop
npx vitest run src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx
```
Expected: 2 of 3 FAIL — the panel still hard-codes `authenticate(name)` regardless of `auth_kind`. Regression test should pass.

- [ ] **Step 3: Update `BackendStatusPanel.tsx`**

Locate the existing button block (`onClick={() => window.electronAPI.backends.authenticate(name)}`) and replace it with auth-kind-aware logic:

```tsx
{health.action === 'reauth' && (
  <AuthButton
    name={name}
    authKind={health.auth_kind ?? 'cli'}
    cliCommand={health.cli_command ?? undefined}
  />
)}
```

Add `AuthButton` in the same file (or a sibling file if preferred):

```tsx
function AuthButton({
  name,
  authKind,
  cliCommand,
}: {
  name: string;
  authKind: 'cli' | 'browser';
  cliCommand?: string;
}) {
  const [waiting, setWaiting] = useState(false);

  if (authKind === 'cli') {
    if (!cliCommand) return null;
    return (
      <button
        onClick={() => window.electronAPI.backends.authenticate(name)}
        className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30 transition-colors"
      >
        Re-authenticate
      </button>
    );
  }

  // browser
  return (
    <button
      disabled={waiting}
      onClick={async () => {
        setWaiting(true);
        try {
          await window.electronAPI.backends.authenticateOAuth(name);
        } finally {
          setWaiting(false);
        }
      }}
      className="rounded bg-chart-1/20 px-2 py-0.5 text-xs font-medium text-chart-1 hover:bg-chart-1/30 transition-colors disabled:opacity-60"
    >
      {waiting ? 'Waiting for browser…' : 'Authenticate'}
    </button>
  );
}
```

(If `useState` isn't already imported in this file, add it: `import { useEffect, useState } from 'react';` — the existing imports likely already include both.)

Also update the `BackendHealth` type in the same file (or its declaration site) to include the new field:

```tsx
type BackendHealth = {
  authenticated: boolean;
  action: 'healthy' | 'rate_limited' | 'reauth' | 'degraded';
  auth_kind?: 'cli' | 'browser';
  // ...existing fields...
};
```

- [ ] **Step 4: Run the renderer tests**

```
cd apps/desktop
npx vitest run src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx
```
Expected: 3 passed.

- [ ] **Step 5: Run the full desktop test suite — guard against regressions**

```
npx vitest run
```
Expected: all pass.

- [ ] **Step 6: Manual smoke test (no automation; performed by the engineer)**

1. `make aigw-dev` to boot the gateway locally.
2. `make sf-dev` to boot the SF server.
3. `make desktop-dev` to run Electron.
4. Open Settings → Backend Status. The aigw-claude-backend row should show **Authenticate**.
5. Click Authenticate. Browser opens to `https://console.anthropic.com/oauth/authorize?...`.
6. Complete OAuth in the browser. The browser shows "Authentication complete. You may close this window."
7. The button disappears within ~2s; the panel turns green.

(If you don't have a real Anthropic OAuth client yet, set `AIGATEWAY_FAKE_ANTHROPIC_OAUTH=1` and exercise the flow against the fake — this validates the desktop wiring without provider credentials.)

- [ ] **Step 7: Commit**

```
git add apps/desktop/src/renderer/src/components/server/BackendStatusPanel.tsx \
        apps/desktop/src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx
git commit -m "feat(desktop): BackendStatusPanel browser-mode authenticate button"
```

---

## Final task: end-to-end verification + PR

- [ ] **Step 1: Run the full Python test suite**

```
cd apps/server
uv run pytest -q
```
Expected: all pass.

- [ ] **Step 2: Run ruff + pyright**

```
uv run ruff check . && uv run ruff format --check .
uv run pyright src
```
Expected: clean.

- [ ] **Step 3: Run the full Electron suite**

```
cd apps/desktop
npx vitest run
```
Expected: all pass.

- [ ] **Step 4: Open the PR**

```
git push -u origin <branch>
gh pr create --title "feat: aigw-*-backend OAuth Authenticate button" --body "$(cat <<'EOF'
## Summary
- New `<prefix>/auth/start` and `<prefix>/auth/status` proxy routes on aigw-*-backend plugins, forwarding to the AI Gateway's OAuth endpoints.
- `AigwBackend.health()` now probes the gateway profile state.
- `/backends/status` carries a new `auth_kind: "cli" | "browser"` field.
- Electron `oauth-launcher` service drives the browser-OAuth cycle and reports completion to the renderer.
- BackendStatusPanel renders an Authenticate button (browser flow) or the existing Re-authenticate button (CLI flow) depending on `auth_kind`.

Spec: `docs/superpowers/specs/2026-05-07-aigw-backend-oauth-authenticate-button-design.md`
Plan: `docs/superpowers/plans/2026-05-07-aigw-backend-oauth-authenticate-button.md`
Asana: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1214600798519030

## Test plan
- [x] `apps/server`: unit tests (auth-proxy, backend.health, classify_auth_kind)
- [x] `apps/server`: 6 integration scenarios under `tests/e2e/test_aigw_auth_e2e.py`
- [x] `apps/desktop`: oauth-launcher + BackendStatusPanel vitest suites
- [ ] Manual smoke against real Anthropic OAuth (engineer to perform before merge)
EOF
)"
```

---

## Self-Review Notes

- Spec coverage: each component (auth proxy, gateway_provider, health(), auth_kind, oauth-launcher, renderer wiring) maps to a numbered task. Six integration scenarios from the spec map 1-to-1 to scenarios in Task 7. ✓
- Type consistency: `LauncherResult` is the same union shape across launcher impl / launcher tests / IPC declaration / preload type / renderer test mock. `auth_kind` value set is `"cli" | "browser"` everywhere. `gateway_provider` attribute name is consistent across `AigwBackendApiPluginBase`, `aigw_claude_backend`, `_classify_auth_kind`. ✓
- Placeholder scan: every code step shows code; every command shows expected output. The two helpers I left for the engineer to locate (`getSfBaseUrl`, the IPC registration file path) are explicitly bracketed with a `rg` command in Task 8 Step 1 to find them. ✓
