"""Routes for the url4-executor plugin — /ensemble endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.highlight import tokenize
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
from screamingface.plugins.url4_executor.url4 import Url4List, Url4RelUrl, Url4Url, parse

logger = logging.getLogger(__name__)


def _ast_to_dict(node) -> dict | str:
    """Convert a Url4Node to a JSON-serializable dict."""
    if isinstance(node, Url4Url):
        return {"type": "url", "value": node.value}
    if isinstance(node, Url4RelUrl):
        return {"type": "relurl", "value": node.value}
    if isinstance(node, Url4List):
        return {"type": "list", "items": [_ast_to_dict(item) for item in node.items]}
    # Url4Text
    return {"type": "text", "value": node.value}


def create_router(app=None) -> APIRouter:  # type: ignore[no-untyped-def]
    router = APIRouter(tags=["url4-executor"])

    @router.get("/ensemble/highlight", response_model=None, operation_id="url4_highlight")
    async def url4_highlight(q: str | None = None) -> JSONResponse:
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'q' query parameter")
        try:
            tokens = tokenize(q)
        except Exception as exc:
            logger.warning("url4 highlight failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=400, detail=f"url4 parse error: {exc}")
        return JSONResponse(content={"tokens": tokens})

    @router.get("/ensemble", response_model=None, operation_id="url4_resolve")
    async def url4_resolve(
        q: str | None = None,
        ast: bool = False,
    ) -> PlainTextResponse | JSONResponse:
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'q' query parameter")

        interpreter = Url4Interpreter(app=app)

        try:
            result = await interpreter.evaluate(q)
        except Exception as exc:
            logger.warning("url4 evaluation failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"url4 evaluation failed: {exc}")

        # Record result on the FastAPI auto-instrumented span
        from screamingface.plugins.url4_executor._tracing import set_span_attrs

        preview = result[:4000]
        if len(result) > 4000:
            preview += f"\n... ({len(result) - 4000} more chars)"
        set_span_attrs(
            {
                "url4.expression": q[:500],
                "url4.result_length": len(result),
                "url4.response_body": preview,
            }
        )

        if ast:
            source_expr, intent = split_intent(q)
            tree = parse(source_expr) if source_expr else None
            return JSONResponse(
                content={
                    "ast": _ast_to_dict(tree) if tree else None,
                    "result": result,
                }
            )
        return PlainTextResponse(content=result)

    return router
