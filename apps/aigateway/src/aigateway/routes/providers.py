"""Credential-provider discovery derived from the loaded plugin registry."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..core.auth.middleware import CurrentAccount

router = APIRouter()


@router.get("/v1/providers")
async def list_providers(request: Request, _current: CurrentAccount) -> dict[str, object]:
    """List enabled model providers whose credentials a caller can manage."""

    rows: list[dict[str, object]] = []
    for plugin in request.app.state.providers.all():
        auth_methods = tuple(method for method in plugin.available_auth_modes() if method != "none")
        if not auth_methods or not plugin.register_models():
            continue
        rows.append(
            {
                "object": "provider",
                "id": plugin.custom_llm_provider,
                "display_name": plugin.provider_display_name,
                "auth_methods": list(auth_methods),
            }
        )
    rows.sort(key=lambda row: str(row["id"]))
    return {"object": "list", "data": rows}


__all__ = ["router"]
