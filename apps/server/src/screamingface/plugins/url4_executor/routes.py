"""Routes for the url4-executor plugin — /ensemble endpoint."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from screamingface.plugins.eval_runs._hook_payloads import (
    HOOK_RUN_FAILED,
    HOOK_RUN_FINISHED,
    HOOK_RUN_STARTED,
)
from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter
from screamingface.plugins.url4_executor.formatter import format_url4_safe
from screamingface.plugins.url4_executor.highlight import tokenize
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4Binding,
    Url4ExpandedSource,
    Url4List,
    Url4RelUrl,
    Url4Url,
    parse,
)

logger = logging.getLogger(__name__)


def _ast_to_dict(node) -> dict | str:
    """Convert a Url4Node to a JSON-serializable dict."""
    if isinstance(node, Url4Url):
        return {"type": "url", "value": node.value}
    if isinstance(node, Url4RelUrl):
        return {"type": "relurl", "value": node.value}
    if isinstance(node, Url4BackendCall):
        result: dict = {"type": "backend_call", "path": node.path}
        if node.packed_context:
            result["packed_context"] = node.packed_context
        if node.name:
            result["name"] = node.name
        if node.weight is not None:
            result["weight"] = node.weight
        if node.intent is not None:
            result["intent"] = _ast_to_dict(node.intent)
        return result
    if isinstance(node, Url4ExpandedSource):
        return {"type": "expanded_source", "inner": _ast_to_dict(node.inner)}
    if isinstance(node, Url4Binding):
        return {
            "type": "binding",
            "name": node.name,
            "kind": node.kind,
            "value": _ast_to_dict(node.value),
        }
    if isinstance(node, Url4List):
        return {"type": "list", "items": [_ast_to_dict(item) for item in node.items]}
    # Url4Text
    return {"type": "text", "value": node.value}


class Url4FormatIn(BaseModel):
    q: str


def create_router(app=None) -> APIRouter:  # type: ignore[no-untyped-def]
    router = APIRouter(tags=["url4-executor"])

    @router.post(
        "/ensemble/format",
        response_model=None,
        operation_id="url4_format",
    )
    async def url4_format(body: Url4FormatIn) -> JSONResponse:
        # POST (not GET) so large expressions aren't capped by URL length.
        formatted, error = format_url4_safe(body.q)
        return JSONResponse(content={"formatted": formatted, "error": error})

    @router.get(
        "/ensemble/highlight",
        response_model=None,
        operation_id="url4_highlight",
    )
    async def url4_highlight(q: str | None = None) -> JSONResponse:
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'q' query parameter")
        try:
            tokens = tokenize(q)
        except Exception as exc:
            logger.warning("url4 highlight failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=400, detail=f"url4 parse error: {exc}")
        return JSONResponse(content={"tokens": tokens})

    @router.get(
        "/ensemble",
        response_model=None,
        operation_id="url4_resolve",
    )
    async def url4_resolve(
        request: Request,
        q: str | None = None,
        ast: bool = False,
        processor: str | None = None,
        x_sf_run_id: str | None = Header(default=None, alias="X-SF-Run-Id"),
        x_sf_run_spec: str | None = Header(default=None, alias="X-SF-Run-Spec"),
    ) -> PlainTextResponse | JSONResponse:
        if not q:
            raise HTTPException(status_code=400, detail="Missing 'q' query parameter")

        run_id: str | None = None
        if x_sf_run_id or x_sf_run_spec:
            run_id = x_sf_run_id or str(uuid.uuid4())

        env = Env.root()
        if run_id:
            env = env.child(__run_id__=run_id, __run_spec__=x_sf_run_spec or "")
            await request.app.state.hooks.emit_async(
                HOOK_RUN_STARTED,
                run_id=run_id,
                spec_name=x_sf_run_spec or "",
                url4_expression=q,
                started_at=datetime.now(UTC),
            )

        # Use EnsembleInterpreter when a processor is specified OR the
        # expression matches the fan-out shape. The ensemble interpreter
        # falls through to base Url4Interpreter behavior for non-ensemble
        # expressions, so it's safe to always use it.
        interpreter = EnsembleInterpreter(app=app, processor=processor)

        try:
            result = await interpreter.evaluate(q, env=env)
        except Exception as exc:
            logger.warning("url4 evaluation failed: %s", exc, exc_info=True)
            if run_id:
                await request.app.state.hooks.emit_async(
                    HOOK_RUN_FAILED,
                    run_id=run_id,
                    finished_at=datetime.now(UTC),
                    error=str(exc),
                )
            raise HTTPException(status_code=502, detail=f"url4 evaluation failed: {exc}")

        collected_errors = getattr(interpreter, "_collected_errors", 0)
        if run_id:
            await request.app.state.hooks.emit_async(
                HOOK_RUN_FINISHED,
                run_id=run_id,
                finished_at=datetime.now(UTC),
                collected_errors=collected_errors,
            )

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

        response: JSONResponse | PlainTextResponse
        if ast:
            source_expr, intent, _broadcast = split_intent(q)
            tree = parse(source_expr) if source_expr else None
            response = JSONResponse(
                content={
                    "ast": _ast_to_dict(tree) if tree else None,
                    "result": result,
                }
            )
        else:
            response = PlainTextResponse(content=result)

        # SF-236: surface ;foreach.on_error=collect failures so they are not
        # silently dropped downstream. HTTP stays 200 (collect mode is robust).
        if collected_errors:
            response.headers["X-SF-Collected-Errors"] = str(collected_errors)
        return response

    return router
