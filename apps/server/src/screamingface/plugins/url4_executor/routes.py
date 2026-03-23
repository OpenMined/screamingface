"""Routes for the url4-executor plugin — url4 expression resolution endpoint."""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.highlight import tokenize
from screamingface.plugins.url4_executor.url4 import Url4List, Url4Url, parse, resolve_str

logger = logging.getLogger(__name__)

_DISPATCH_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)


def _append_context(backend_url: str, context: str) -> str:
    """Append resolved context as a &context= query param to the backend URL."""
    parsed = urlparse(backend_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params["context"] = [context]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


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

    @router.get("/url4/highlight", response_model=None, operation_id="url4_highlight")
    async def url4_highlight(q: str | None = None) -> JSONResponse:
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'q' query parameter")
        try:
            tokens = tokenize(q)
        except Exception as exc:
            logger.warning("url4 highlight failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=400, detail=f"url4 parse error: {exc}")
        return JSONResponse(content={"tokens": tokens})

    @router.get("/url4", response_model=None, operation_id="url4_resolve")
    async def url4_resolve(
        q: str | None = None,
        ast: bool = False,
    ) -> PlainTextResponse | JSONResponse:
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'q' query parameter")

        source_expr, intent = split_intent(q)

        resolved = ""
        if source_expr:
            try:
                resolved = await resolve_str(source_expr)
            except Exception as exc:
                logger.warning("url4 resolution failed: %s", exc, exc_info=True)
                raise HTTPException(status_code=502, detail=f"url4 resolution failed: {exc}")

        # No intent (or empty intent) — return resolved text as before
        if not intent:
            if ast:
                tree = parse(source_expr)
                return JSONResponse(content={"ast": _ast_to_dict(tree), "result": resolved})
            return PlainTextResponse(content=resolved)

        # Intent is a backend URL — dispatch resolved content to it
        if not intent.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400,
                detail="Intent must be a backend URL (http:// or https://)",
            )

        dispatch_url = _append_context(intent, resolved) if resolved else intent

        try:
            async with httpx.AsyncClient(timeout=_DISPATCH_TIMEOUT, verify=False) as client:
                resp = await client.get(dispatch_url)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Backend request timed out")
        except Exception as exc:
            logger.warning("Backend dispatch failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Backend dispatch failed: {exc}")

        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Backend returned {resp.status_code}: {resp.text[:500]}",
            )

        if ast:
            tree = parse(source_expr) if source_expr else None
            return JSONResponse(
                content={
                    "ast": _ast_to_dict(tree) if tree else None,
                    "result": resolved,
                    "intent": intent,
                    "response": resp.text,
                }
            )
        return PlainTextResponse(content=resp.text)

    return router
