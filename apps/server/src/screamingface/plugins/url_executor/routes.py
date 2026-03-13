"""Routes for the url-executor plugin — url4 context resolution endpoint."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from screamingface.core.url4 import resolve

if TYPE_CHECKING:
    from screamingface.plugins.url_executor.plugin import UrlExecutorSettings

logger = logging.getLogger(__name__)


def create_router(settings: UrlExecutorSettings) -> APIRouter:
    router = APIRouter(tags=["url-executor"])

    @router.get("/url4", response_model=None, operation_id="url4_resolve")
    async def url4_resolve(request: Request) -> PlainTextResponse:
        context = request.query_params.get("context")
        if not context:
            raise HTTPException(status_code=400, detail="Missing 'context' query parameter")

        try:
            result = await resolve(context)
        except Exception as exc:
            logger.warning("url4 resolution failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"url4 resolution failed: {exc}")

        return PlainTextResponse(content=result)

    return router
