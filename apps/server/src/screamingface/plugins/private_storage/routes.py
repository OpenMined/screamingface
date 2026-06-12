"""Routes for the private-storage plugin — editable markdown entities by uuid7.

GET /private/{uuid7} returns raw markdown (text/markdown) so url4's relative-URL
resolver can feed it into a chain, identical to /data/{key}. The other endpoints
(list/create/update/delete) are JSON and drive the Private Data UI."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from screamingface.plugins.private_storage import store

__all__ = ["create_router"]


class CreateBody(BaseModel):
    content: str = ""
    label: str | None = None


class UpdateBody(BaseModel):
    content: str | None = None
    label: str | None = None


def create_router() -> APIRouter:
    router = APIRouter(tags=["private-storage"])

    @router.get("/private", response_model=None, operation_id="private_list")
    async def list_private() -> JSONResponse:
        items = await store.list_entities()
        return JSONResponse(
            content=[
                {
                    "uuid": str(e.id),
                    "label": e.label,
                    "updated_at": e.updated_at.isoformat(),
                }
                for e in items
            ]
        )

    @router.post("/private", response_model=None, operation_id="private_create")
    async def create_private(body: CreateBody) -> JSONResponse:
        entity = await store.create_entity(content=body.content, label=body.label)
        return JSONResponse(
            content={"uuid": str(entity.id), "url": f"/private/{entity.id}", "label": entity.label}
        )

    @router.get("/private/{uuid7}", response_model=None, operation_id="private_get")
    async def get_private(uuid7: str) -> Response:
        entity = await store.get_entity(uuid7)
        if entity is None:
            raise HTTPException(status_code=404, detail="Not found")
        return Response(content=entity.content, media_type="text/markdown; charset=utf-8")

    @router.put("/private/{uuid7}", response_model=None, operation_id="private_update")
    async def update_private(uuid7: str, body: UpdateBody) -> JSONResponse:
        entity = await store.update_entity(
            uuid7,
            content=body.content,
            label=body.label,
            label_set="label" in body.model_fields_set,
        )
        if entity is None:
            raise HTTPException(status_code=404, detail="Not found")
        return JSONResponse(content={"uuid": str(entity.id), "label": entity.label})

    @router.delete("/private/{uuid7}", response_model=None, operation_id="private_delete")
    async def delete_private(uuid7: str) -> Response:
        ok = await store.delete_entity(uuid7)
        if not ok:
            raise HTTPException(status_code=404, detail="Not found")
        return Response(status_code=204)

    return router
