from __future__ import annotations

from fastapi import APIRouter, Request

from ..core.auth.middleware import CurrentAccount
from ..core.model_capabilities import model_row

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request, _current: CurrentAccount) -> dict:
    """OpenAI-compatible model listing, aggregated from all loaded provider plugins.

    Each row carries the OME-479 locked hybrid summary (canonical dispatchable
    ``id`` + effective ``supported_parameters``/``supported_tools`` + literal
    ``reject`` + a same-origin detail URL), composed from each plugin's own
    provider-local rule set.
    """
    registry = request.app.state.providers
    data = [
        model_row(plugin, entry) for plugin in registry.all() for entry in plugin.register_models()
    ]
    # OME-879: dynamically admitted models (deployment-lifetime, app.state only)
    # join the listing after the seeded catalog. The admit route never stores a
    # seeded id here, so no row can appear twice.
    for model_id, entry in request.app.state.admitted_models.items():
        plugin = registry.get(model_id.split("/", 1)[0])
        if plugin is not None:
            data.append(model_row(plugin, entry))
    return {"object": "list", "data": data}
