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
from collections.abc import Callable
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

__all__ = ["build_aigw_auth_proxy_router"]


HttpClientFactory = Callable[[float], httpx.AsyncClient]
AuthProxyRoute = Literal["start", "status", "profiles", "exchange_code", "delete", "import"]
_DEFAULT_ENABLED_ROUTES: frozenset[AuthProxyRoute] = frozenset(
    {"start", "status", "profiles", "exchange_code", "delete"}
)


class _ExchangeCodeBody(BaseModel):
    code: str
    state: str


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
    defaults: dict[str, Any] | None = None,
    enabled_routes: set[AuthProxyRoute] | frozenset[AuthProxyRoute] | None = None,
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
    routes = enabled_routes or _DEFAULT_ENABLED_ROUTES

    if "start" in routes:

        @router.post(f"{path_prefix}/auth/start")
        async def start_auth(name: str | None = None) -> dict[str, Any]:
            target = name or profile_name
            url = f"{base}/v1/auth/{gateway_provider}/profiles"
            body = _profile_body(target, profile_name, defaults)
            resp = await _post_json(url, body, base, factory, timeout_seconds)
            return resp.json()

    if "status" in routes:

        @router.get(f"{path_prefix}/auth/status")
        async def auth_status(name: str | None = None) -> dict[str, Any]:
            target = name or profile_name
            url = f"{base}/v1/auth/{gateway_provider}/profiles/{target}/status"
            resp = await _get_json(url, base, factory, timeout_seconds)
            return resp.json()

    if "profiles" in routes:

        @router.get(f"{path_prefix}/auth/profiles")
        async def list_profiles() -> dict[str, Any]:
            url = f"{base}/v1/auth/{gateway_provider}/profiles"
            resp = await _get_json(url, base, factory, timeout_seconds)
            return resp.json()

    if "import" in routes:

        @router.post(f"{path_prefix}/auth/import", status_code=201)
        async def import_profile(name: str | None = None) -> dict[str, Any]:
            target = name or profile_name
            url = f"{base}/v1/auth/{gateway_provider}/profiles/import"
            body = _profile_body(target, profile_name, defaults)
            resp = await _post_json(url, body, base, factory, timeout_seconds)
            return resp.json()

    if "exchange_code" in routes:

        @router.post(f"{path_prefix}/auth/exchange-code")
        async def exchange_code(body: _ExchangeCodeBody) -> dict[str, Any]:
            """Forward a manually-pasted authorization code to the gateway.

            Used as a fallback when the OAuth provider displays the code on
            screen (e.g. ``code=true``) instead of redirecting back. The
            gateway looks up the matching pending entry by ``state``, so we
            do not need to know which profile this targets.
            """
            url = f"{base}/v1/auth/{gateway_provider}/exchange-code"
            resp = await _post_json(url, body.model_dump(), base, factory, timeout_seconds)
            return resp.json()

    if "delete" in routes:

        @router.delete(f"{path_prefix}/auth/profiles/{{name}}", status_code=204)
        async def delete_profile(name: str) -> Response:
            url = f"{base}/v1/auth/{gateway_provider}/profiles/{name}"
            try:
                async with factory(timeout_seconds) as client:
                    resp = await client.delete(url)
            except httpx.RequestError as exc:
                raise _gateway_unreachable(base, exc)

            if resp.status_code == 204:
                return Response(status_code=204)
            _raise_for_gateway_error(resp)
            return Response(status_code=204)

    return router


async def _post_json(
    url: str,
    body: dict[str, Any],
    base: str,
    factory: HttpClientFactory,
    timeout_seconds: float,
) -> httpx.Response:
    try:
        async with factory(timeout_seconds) as client:
            resp = await client.post(url, json=body)
    except httpx.RequestError as exc:
        raise _gateway_unreachable(base, exc)
    _raise_for_gateway_error(resp)
    return resp


async def _get_json(
    url: str,
    base: str,
    factory: HttpClientFactory,
    timeout_seconds: float,
) -> httpx.Response:
    try:
        async with factory(timeout_seconds) as client:
            resp = await client.get(url)
    except httpx.RequestError as exc:
        raise _gateway_unreachable(base, exc)
    _raise_for_gateway_error(resp)
    return resp


def _profile_body(
    target: str, profile_name: str, defaults: dict[str, Any] | None
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": target}
    if defaults and target == profile_name:
        body["defaults"] = defaults
    return body


def _gateway_unreachable(base: str, exc: httpx.RequestError) -> HTTPException:
    logger.warning("aigw auth-proxy: gateway unreachable at %s: %s", base, exc)
    return HTTPException(
        status_code=502,
        detail={
            "code": "gateway_unreachable",
            "message": f"AI Gateway unreachable at {base}: {exc}",
        },
    )


def _raise_for_gateway_error(resp: httpx.Response) -> None:
    if resp.status_code >= 500:
        logger.warning("aigw auth-proxy: gateway returned %d", resp.status_code)
        raise HTTPException(
            status_code=502,
            detail={"code": "gateway_error", "upstream_status": resp.status_code},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:500]}
