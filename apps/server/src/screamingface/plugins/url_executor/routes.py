"""Routes for the url-executor plugin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from screamingface.plugins.url_executor.decoder import build_dispatch_body, decode_prompt
from screamingface.plugins.url_executor.dispatch import BACKEND_MAP, dispatch_request
from screamingface.plugins.url_executor.preview import render_preview_html

if TYPE_CHECKING:
    from screamingface.plugins.url_executor.plugin import UrlExecutorSettings


def create_router(settings: UrlExecutorSettings) -> APIRouter:
    router = APIRouter(tags=["url-executor"])

    async def _handle(
        request: Request, backend: str, action: str | None
    ) -> HTMLResponse | JSONResponse | StreamingResponse:
        if backend not in BACKEND_MAP:
            raise HTTPException(status_code=404, detail=f"Unknown backend: {backend!r}")

        _, default_action, _ = BACKEND_MAP[backend]
        action = action or default_action

        params = dict(request.query_params)

        # Decode prompt
        try:
            prompt = decode_prompt(params, settings.max_prompt_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # Browser preview: Accept: text/html and no execute header
        accept = request.headers.get("accept", "")
        execute_header = request.headers.get("x-sf-execute", "").lower() == "true"

        if (
            settings.show_preview_html
            and settings.require_execute_header
            and "text/html" in accept
            and not execute_header
        ):
            body = build_dispatch_body(params, prompt)
            html = render_preview_html(backend, action, body)
            return HTMLResponse(content=html)

        # Build body and dispatch
        stream = params.get("stream", "").lower() in ("1", "true")
        body = build_dispatch_body(params, prompt)

        try:
            return await dispatch_request(request.app, backend, action, body, stream=stream)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.get("/x/{backend}", response_model=None, operation_id="url_exec")
    async def url_exec(
        request: Request, backend: str
    ) -> HTMLResponse | JSONResponse | StreamingResponse:
        return await _handle(request, backend, action=None)

    @router.get(
        "/x/{backend}/{action}", response_model=None, operation_id="url_exec_with_action"
    )
    async def url_exec_with_action(
        request: Request, backend: str, action: str
    ) -> HTMLResponse | JSONResponse | StreamingResponse:
        return await _handle(request, backend, action=action)

    return router
