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

    return router


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:500]}
