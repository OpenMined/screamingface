"""SF-side control routes for AIGateway session management."""

from __future__ import annotations

import os
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .client import (
    AigwGatewayClient,
    AigwGatewayClientError,
    clear_gateway_session,
    gateway_session_state,
    parse_gateway_expires_at,
)
from .config import resolve_aigw_runtime_config
from .desktop_secret import require_desktop_secret
from .settings import AigwBaseSettings


class GatewayLoginBody(BaseModel):
    username: str
    password: str
    gateway_url: str | None = None


def create_router(app: Any) -> APIRouter:
    router = APIRouter(tags=["aigw-base"], dependencies=[Depends(require_desktop_secret)])

    @router.get("/aigateway/session")
    async def gateway_session() -> dict[str, Any]:
        config = resolve_aigw_runtime_config(app)
        state = gateway_session_state(app)
        return {
            "mode": config.mode,
            "authenticated": config.mode == "local_managed" or state.authenticated,
            "expires_at": state.expires_at.isoformat() if state.expires_at else None,
        }

    @router.post("/aigateway/session/login")
    async def gateway_login(body: GatewayLoginBody) -> dict[str, Any]:
        if body.gateway_url:
            _apply_gateway_url_override(app, body.gateway_url)
        config = resolve_aigw_runtime_config(app)
        if config.mode != "external":
            raise HTTPException(
                status_code=400,
                detail={"code": "local_managed", "message": "Gateway login is external-mode only"},
            )
        _validate_gateway_url(config.gateway_url)

        try:
            resp = await AigwGatewayClient(app).request(
                "POST",
                "/v1/auth/login",
                json={"username": body.username, "password": body.password},
                allow_unauthenticated=True,
            )
        except AigwGatewayClientError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_unreachable", "message": str(exc)},
            ) from exc

        if resp.status_code >= 500:
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_error", "upstream_status": resp.status_code},
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=_safe_json(resp))

        payload = resp.json()
        token = payload.get("token")
        if not isinstance(token, str) or not token:
            raise HTTPException(
                status_code=502,
                detail={"code": "gateway_error", "message": "Gateway login returned no token"},
            )
        state = gateway_session_state(app)
        state.set_token(token, parse_gateway_expires_at(payload.get("expires_at")))
        return {
            "authenticated": True,
            "expires_at": state.expires_at.isoformat() if state.expires_at else None,
            "token": token,
        }

    @router.post("/aigateway/session/logout")
    async def gateway_logout() -> dict[str, bool]:
        clear_gateway_session(app)
        return {"authenticated": False}

    return router


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text[:500]}


def _apply_gateway_url_override(app: Any, gateway_url: str) -> None:
    normalized = _validate_gateway_url(gateway_url)
    config = getattr(getattr(app, "state", None), "config", None)
    plugin_config = getattr(config, "plugin_config", None)
    if isinstance(plugin_config, dict):
        base = plugin_config.setdefault("aigw-base", {})
        if isinstance(base, dict):
            base["mode"] = "external"
            base["gateway_url"] = normalized

    plugins = getattr(getattr(app, "state", None), "plugins", None)
    active_plugins = getattr(plugins, "active_plugins", {})
    plugin = active_plugins.get("aigw-base") if isinstance(active_plugins, dict) else None
    settings = getattr(plugin, "settings", None)
    if isinstance(settings, AigwBaseSettings):
        settings.mode = "external"
        settings.gateway_url = normalized


def _validate_gateway_url(gateway_url: str) -> str:
    parsed = urlparse(gateway_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_gateway_url", "message": "Gateway URL must use http or https"},
        )
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_gateway_url",
                "message": "Gateway URL must not include credentials",
            },
        )
    if parsed.scheme == "http" and not _insecure_gateway_url_allowed(parsed.hostname or ""):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_gateway_url",
                "message": "External AIGateway URL must use HTTPS unless it is loopback",
            },
        )
    return gateway_url.strip().rstrip("/")


def _insecure_gateway_url_allowed(host: str) -> bool:
    if os.getenv("SF_AIGW_ALLOW_INSECURE_EXTERNAL") == "1":
        return True
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False
