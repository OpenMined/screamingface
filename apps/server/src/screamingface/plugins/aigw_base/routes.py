"""SF-side control routes for AIGateway session management."""

from __future__ import annotations

from typing import Any

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


class GatewayLoginBody(BaseModel):
    username: str
    password: str


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
        config = resolve_aigw_runtime_config(app)
        if config.mode != "external":
            raise HTTPException(
                status_code=400,
                detail={"code": "local_managed", "message": "Gateway login is external-mode only"},
            )

        try:
            resp = await AigwGatewayClient(app).request(
                "POST",
                "/v1/auth/login",
                json=body.model_dump(),
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
