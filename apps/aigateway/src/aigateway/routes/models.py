from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request) -> dict:
    """OpenAI-compatible model listing, aggregated from all loaded provider plugins."""
    registry = request.app.state.providers
    data = []
    for plugin in registry.all():
        for entry in plugin.register_models():
            data.append(
                {
                    "id": entry.model_name,
                    "object": "model",
                    "owned_by": plugin.custom_llm_provider,
                }
            )
    return {"object": "list", "data": data}
