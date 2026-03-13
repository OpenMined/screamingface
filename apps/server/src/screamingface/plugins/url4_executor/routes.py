"""Routes for the url4-executor plugin — url4 context resolution endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from screamingface.plugins.url4_executor.url4 import Url4List, Url4Url, parse, resolve_str

logger = logging.getLogger(__name__)


def _ast_to_dict(node) -> dict | str:
    """Convert a Url4Node to a JSON-serializable dict."""
    if isinstance(node, Url4Url):
        return {"type": "url", "value": node.value}
    if isinstance(node, Url4List):
        return {"type": "list", "items": [_ast_to_dict(item) for item in node.items]}
    # Url4Text
    return {"type": "text", "value": node.value}


def create_router() -> APIRouter:
    router = APIRouter(tags=["url4-executor"])

    @router.get("/url4", response_model=None, operation_id="url4_resolve")
    async def url4_resolve(
        context: str | None = None, ast: bool = False
    ) -> PlainTextResponse | JSONResponse:
        if not context:
            raise HTTPException(status_code=400, detail="Missing 'context' query parameter")

        try:
            if ast:
                tree = parse(context)
                result = await resolve_str(context)
                return JSONResponse(content={"ast": _ast_to_dict(tree), "result": result})
            else:
                result = await resolve_str(context)
                return PlainTextResponse(content=result)
        except Exception as exc:
            logger.warning("url4 resolution failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"url4 resolution failed: {exc}")

    return router
