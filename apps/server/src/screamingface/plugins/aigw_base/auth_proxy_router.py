"""Auth-proxy router for aigw-*-backend plugins.

Four routes per backend:

- ``POST   {prefix}/auth/start`` — start an OAuth cycle; returns the
  upstream provider authorize URL.
- ``GET    {prefix}/auth/status`` — read the gateway-side profile state.
- ``GET    {prefix}/auth/profiles`` — list profiles the gateway knows
  about for this provider.
- ``DELETE {prefix}/auth/profiles/{name}`` — delete a named profile.

All forward to the aigateway's ``/v1/auth/{provider}/...`` endpoints.
The SF server never sees the OAuth callback or the upstream token —
the gateway owns all credential state.

The ``start`` and ``status`` routes accept an optional ``?name=<profile>``
query param to target a specific profile. When omitted, requests fall
back to the SF-configured default profile name.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, cast

import httpx
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .client import AigwGatewayClient, AigwGatewayClientError

logger = logging.getLogger(__name__)

__all__ = ["build_aigw_auth_proxy_router"]


HttpClientFactory = Callable[[float], httpx.AsyncClient]


class _ExchangeCodeBody(BaseModel):
    code: str
    state: str


class _StartConnectionBody(BaseModel):
    label: str | None = None


class _AigwCallbackBridge(Protocol):
    async def prepare_redirect_uri(self, *, gateway_provider: str) -> str | None: ...

    def register_state(self, *, state: str, gateway_provider: str, redirect_uri: str) -> None: ...

    def release_redirect_uri(self, redirect_uri: str) -> None: ...

    def unregister_state(self, state: str) -> None: ...


def _default_http_factory(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout))


def build_aigw_auth_proxy_router(
    *,
    path_prefix: str,
    gateway_url: str,
    gateway_provider: str,
    profile_name: str,
    app: Any = None,
    http_client_factory: HttpClientFactory | None = None,
    timeout_seconds: float = 10.0,
    defaults: dict[str, Any] | None = None,
) -> APIRouter:
    """Build the SF-side proxy routes that drive the gateway OAuth flow.

    ``profile_name`` is the *default* profile name used when the client
    does not specify ``?name=<profile>`` on the request. Each route still
    targets a single profile per call.

    ``defaults``, if provided and non-empty, is forwarded as the ``defaults``
    field on the gateway's ``POST /v1/auth/{provider}/profiles`` body — but
    only when creating the SF-configured default profile (i.e. when the
    request targets ``profile_name``). Explicitly-named profiles get no
    defaults forwarded; the user can PATCH them on the gateway directly.
    """
    router = APIRouter(tags=[f"{path_prefix.lstrip('/')}-auth"])
    base = gateway_url.rstrip("/")
    factory = http_client_factory or _default_http_factory

    @router.post(f"{path_prefix}/auth/start")
    async def start_auth(name: str | None = None) -> JSONResponse:
        target = name or profile_name
        path = f"/v1/auth/{gateway_provider}/profiles"
        body: dict[str, Any] = {"name": target}
        # Forward SF-configured defaults only when creating the configured
        # default profile. For other names we send no defaults.
        if defaults and target == profile_name:
            body["defaults"] = defaults
        resp, content = await _gateway_json_with_callback_bridge(
            app,
            factory,
            timeout_seconds,
            "POST",
            base,
            path,
            gateway_provider,
            json=body,
        )
        return JSONResponse(content=content, status_code=resp.status_code)

    @router.get(f"{path_prefix}/auth/status")
    async def auth_status(name: str | None = None) -> dict[str, Any]:
        target = name or profile_name
        path = f"/v1/auth/{gateway_provider}/profiles/{target}/status"
        try:
            resp = await _gateway_request(app, factory, timeout_seconds, "GET", base, path)
        except httpx.RequestError as exc:
            logger.warning("aigw auth-proxy: gateway unreachable at %s: %s", base, exc)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "gateway_unreachable",
                    "message": f"AI Gateway unreachable at {base}: {exc}",
                },
            ) from exc

        if resp.status_code >= 500:
            logger.warning("aigw auth-proxy: gateway returned %d", resp.status_code)
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_error", "upstream_status": resp.status_code},
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))
        return resp.json()

    @router.get(f"{path_prefix}/auth/profiles")
    async def list_profiles() -> dict[str, Any]:
        path = f"/v1/auth/{gateway_provider}/profiles"
        try:
            resp = await _gateway_request(app, factory, timeout_seconds, "GET", base, path)
        except httpx.RequestError as exc:
            logger.warning("aigw auth-proxy: gateway unreachable at %s: %s", base, exc)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "gateway_unreachable",
                    "message": f"AI Gateway unreachable at {base}: {exc}",
                },
            ) from exc

        if resp.status_code >= 500:
            logger.warning("aigw auth-proxy: gateway returned %d", resp.status_code)
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_error", "upstream_status": resp.status_code},
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))
        return resp.json()

    @router.post(f"{path_prefix}/auth/exchange-code")
    async def exchange_code(body: _ExchangeCodeBody) -> JSONResponse:
        """Forward a manually-pasted authorization code to the gateway.

        Used as a fallback when the OAuth provider displays the code on
        screen (e.g. ``code=true``) instead of redirecting back. The
        gateway looks up the matching pending entry by ``state``, so we
        do not need to know which profile this targets.
        """
        path = f"/v1/auth/{gateway_provider}/exchange-code"
        try:
            resp = await _gateway_request(
                app,
                factory,
                timeout_seconds,
                "POST",
                base,
                path,
                json=body.model_dump(),
            )
        except httpx.RequestError as exc:
            logger.warning("aigw auth-proxy: gateway unreachable at %s: %s", base, exc)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "gateway_unreachable",
                    "message": f"AI Gateway unreachable at {base}: {exc}",
                },
            ) from exc

        if resp.status_code >= 500:
            logger.warning("aigw auth-proxy: gateway returned %d", resp.status_code)
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_error", "upstream_status": resp.status_code},
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

    @router.delete(f"{path_prefix}/auth/profiles/{{name}}", status_code=204)
    async def delete_profile(name: str) -> Response:
        path = f"/v1/auth/{gateway_provider}/profiles/{name}"
        try:
            resp = await _gateway_request(app, factory, timeout_seconds, "DELETE", base, path)
        except httpx.RequestError as exc:
            logger.warning("aigw auth-proxy: gateway unreachable at %s: %s", base, exc)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "gateway_unreachable",
                    "message": f"AI Gateway unreachable at {base}: {exc}",
                },
            ) from exc

        if resp.status_code == 204:
            return Response(status_code=204)
        if resp.status_code >= 500:
            logger.warning("aigw auth-proxy: gateway returned %d", resp.status_code)
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_error", "upstream_status": resp.status_code},
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))
        return Response(status_code=204)

    @router.get(f"{path_prefix}/auth/connections")
    async def list_connections() -> dict[str, Any]:
        path = f"/v1/oauth/connections?provider={gateway_provider}"
        return await _gateway_json(app, factory, timeout_seconds, base, path)

    @router.post(f"{path_prefix}/auth/connections", status_code=201)
    async def start_connection(body: _StartConnectionBody) -> JSONResponse:
        payload: dict[str, Any] = {"provider": gateway_provider}
        if body.label:
            payload["label"] = body.label
        resp, content = await _gateway_json_with_callback_bridge(
            app,
            factory,
            timeout_seconds,
            "POST",
            base,
            "/v1/oauth/connections",
            gateway_provider,
            json=payload,
        )
        return JSONResponse(content=content, status_code=resp.status_code)

    @router.get(f"{path_prefix}/auth/connections/{{connection_id}}")
    async def get_connection(connection_id: str) -> dict[str, Any]:
        path = f"/v1/oauth/connections/{connection_id}"
        connection = await _gateway_json(app, factory, timeout_seconds, base, path)
        _ensure_gateway_provider(connection, gateway_provider)
        return connection

    @router.delete(f"{path_prefix}/auth/connections/{{connection_id}}", status_code=204)
    async def delete_connection(connection_id: str) -> Response:
        await _gateway_connection_json(
            app,
            factory,
            timeout_seconds,
            base,
            connection_id,
            gateway_provider,
        )
        resp = await _gateway_response(
            app,
            factory,
            timeout_seconds,
            "DELETE",
            base,
            f"/v1/oauth/connections/{connection_id}",
        )
        if resp.status_code == 204:
            return Response(status_code=204)
        return Response(status_code=resp.status_code)

    @router.post(f"{path_prefix}/auth/connections/{{connection_id}}/refresh")
    async def refresh_connection(connection_id: str) -> JSONResponse:
        await _gateway_connection_json(
            app,
            factory,
            timeout_seconds,
            base,
            connection_id,
            gateway_provider,
        )
        resp = await _gateway_response(
            app,
            factory,
            timeout_seconds,
            "POST",
            base,
            f"/v1/oauth/connections/{connection_id}/refresh",
        )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

    return router


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:500]}


def _callback_bridge(app: Any) -> Any:
    return getattr(getattr(app, "state", None), "aigw_callback_bridge", None)


async def _gateway_json_with_callback_bridge(
    app: Any,
    factory: HttpClientFactory,
    timeout_seconds: float,
    method: str,
    base: str,
    path: str,
    gateway_provider: str,
    *,
    json: dict[str, Any],
) -> tuple[httpx.Response, Any]:
    bridge, redirect_uri = await _prepare_callback_redirect_uri(app, gateway_provider)
    if redirect_uri is not None:
        json["redirect_uri"] = redirect_uri
    try:
        resp = await _gateway_response(
            app,
            factory,
            timeout_seconds,
            method,
            base,
            path,
            json=json,
        )
        content = resp.json()
    except Exception:
        _release_callback_redirect_uri(bridge, redirect_uri)
        raise
    _register_callback_state(bridge, content, gateway_provider, redirect_uri)
    return resp, content


async def _prepare_callback_redirect_uri(
    app: Any,
    gateway_provider: str,
) -> tuple[Any, str | None]:
    bridge = _callback_bridge(app)
    prepare_raw = getattr(bridge, "prepare_redirect_uri", None)
    if not callable(prepare_raw):
        return bridge, None
    prepare = cast(Callable[..., Awaitable[str | None]], prepare_raw)
    try:
        redirect_uri = await prepare(gateway_provider=gateway_provider)
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "oauth_callback_unavailable",
                "message": "Local OAuth callback port is unavailable",
            },
        ) from exc
    if isinstance(redirect_uri, str) and redirect_uri:
        return bridge, redirect_uri
    return bridge, None


def _register_callback_state(
    bridge: Any,
    content: Any,
    gateway_provider: str,
    redirect_uri: str | None,
) -> None:
    if bridge is None or redirect_uri is None:
        return
    state = content.get("state") if isinstance(content, dict) else None
    if not isinstance(state, str) or not state:
        _release_callback_redirect_uri(bridge, redirect_uri)
        return
    register = getattr(bridge, "register_state", None)
    if not callable(register):
        _release_callback_redirect_uri(bridge, redirect_uri)
        return
    try:
        register(state=state, gateway_provider=gateway_provider, redirect_uri=redirect_uri)
    except Exception as exc:
        _release_callback_redirect_uri(bridge, redirect_uri)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "oauth_callback_unavailable",
                "message": "Local OAuth callback port is unavailable",
            },
        ) from exc


def _release_callback_redirect_uri(bridge: Any, redirect_uri: str | None) -> None:
    if bridge is None or redirect_uri is None:
        return
    release = getattr(bridge, "release_redirect_uri", None)
    if callable(release):
        release(redirect_uri)


async def _gateway_request(
    app: Any,
    factory: HttpClientFactory,
    timeout_seconds: float,
    method: str,
    base: str,
    path: str,
    *,
    json: Any = None,
) -> httpx.Response:
    if app is not None:
        try:
            return await AigwGatewayClient(app, http_client_factory=factory).request(
                method,
                path,
                json=json,
                timeout_seconds=timeout_seconds,
            )
        except AigwGatewayClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    url = f"{base}{path}"
    async with factory(timeout_seconds) as client:
        return await client.request(method, url, json=json)


async def _gateway_response(
    app: Any,
    factory: HttpClientFactory,
    timeout_seconds: float,
    method: str,
    base: str,
    path: str,
    *,
    json: Any = None,
) -> httpx.Response:
    try:
        resp = await _gateway_request(
            app,
            factory,
            timeout_seconds,
            method,
            base,
            path,
            json=json,
        )
    except httpx.RequestError as exc:
        logger.warning("aigw auth-proxy: gateway unreachable at %s: %s", base, exc)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "gateway_unreachable",
                "message": f"AI Gateway unreachable at {base}: {exc}",
            },
        ) from exc

    if resp.status_code >= 500:
        logger.warning("aigw auth-proxy: gateway returned %d", resp.status_code)
        raise HTTPException(
            status_code=502,
            detail={"code": "gateway_error", "upstream_status": resp.status_code},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))
    return resp


async def _gateway_json(
    app: Any,
    factory: HttpClientFactory,
    timeout_seconds: float,
    base: str,
    path: str,
) -> dict[str, Any]:
    return (await _gateway_response(app, factory, timeout_seconds, "GET", base, path)).json()


async def _gateway_connection_json(
    app: Any,
    factory: HttpClientFactory,
    timeout_seconds: float,
    base: str,
    connection_id: str,
    gateway_provider: str,
) -> dict[str, Any]:
    connection = await _gateway_json(
        app,
        factory,
        timeout_seconds,
        base,
        f"/v1/oauth/connections/{connection_id}",
    )
    _ensure_gateway_provider(connection, gateway_provider)
    return connection


def _ensure_gateway_provider(connection: dict[str, Any], gateway_provider: str) -> None:
    if connection.get("provider") != gateway_provider:
        raise HTTPException(status_code=404, detail={"code": "connection_not_found"})
