"""Routes for the data-store plugin — store and retrieve blobs by key.

The :class:`BlobStore` itself lives in :mod:`.storage`; the per-app
instance is attached to ``app.state.blob_store`` by
:meth:`DataStorePlugin.setup`. These handlers reach it via
``request.app.state.blob_store``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

__all__ = ["create_router"]


def create_router() -> APIRouter:
    router = APIRouter(tags=["data-store"])

    @router.post("/data", response_model=None, operation_id="data_store_create")
    async def create_blob(request: Request) -> JSONResponse:
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="Empty body")
        content_type = request.headers.get("content-type", "application/octet-stream")
        key = request.app.state.blob_store.store(body, content_type)

        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("sf.plugin", "data-store")
                span.set_attribute("data.key", key)
                span.set_attribute("data.size", len(body))
        except ImportError:
            pass

        return JSONResponse(content={"key": key, "url": f"/data/{key}"})

    @router.get("/data/{key}", response_model=None, operation_id="data_store_get")
    async def get_blob_route(key: str, request: Request) -> Response:
        entry = request.app.state.blob_store.get(key)
        if entry is None:
            raise HTTPException(status_code=404, detail="Not found")
        body, content_type = entry

        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("sf.plugin", "data-store")
                span.set_attribute("data.key", key)
                span.set_attribute("data.size", len(body))
                span.set_attribute("data.content_type", content_type)
                preview = body[:2000].decode(errors="replace")
                if len(body) > 2000:
                    preview += f"\n... ({len(body) - 2000} more bytes)"
                span.set_attribute("data.body_preview", preview)
        except ImportError:
            pass

        return Response(content=body, media_type=content_type)

    return router
