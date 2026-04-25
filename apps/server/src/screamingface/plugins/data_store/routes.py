"""Routes for the data-store plugin — store and retrieve blobs by key.

The storage itself lives in :mod:`.storage` so other plugins can use
``store_blob`` / ``get_blob`` without reaching into a ``.routes``
module (routes are FastAPI implementation detail, not public API).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from screamingface.plugins.data_store.storage import get_blob, store_blob

# Re-export for back-compat: older callers imported ``store_blob`` /
# ``get_blob`` from this module directly. New code should import from
# :mod:`.storage`.
__all__ = ["create_router", "get_blob", "store_blob"]


def create_router() -> APIRouter:
    router = APIRouter(tags=["data-store"])

    @router.post("/data", response_model=None, operation_id="data_store_create")
    async def create_blob(request: Request) -> JSONResponse:
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="Empty body")
        content_type = request.headers.get("content-type", "application/octet-stream")
        key = store_blob(body, content_type)

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
    async def get_blob_route(key: str) -> Response:
        entry = get_blob(key)
        if entry is None:
            raise HTTPException(status_code=404, detail="Not found")
        body, content_type = entry

        # Add truncated body preview to the current OTEL span (auto-created by FastAPI)
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
