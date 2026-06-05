"""Claude API proxy router — TERMINAL ensemble inference.

The hot path is :func:`proxy_messages`. It is now a TERMINAL endpoint: it
resolves the active url4 spec in-process and synthesizes the Anthropic
Messages response envelope (unary) / SSE stream (streaming). It no longer
forwards inference requests to the real Anthropic upstream.

- Session enrichment + save — :mod:`._session`
- URL4 ``$prompt`` / static context resolution — :mod:`._url4_context`
  (returns ``(resolved_text, error_dict)``)
- Wire-format rendering — M1's ``build_anthropic_message`` /
  ``stream_anthropic_sse`` from :mod:`frontend_base.terminal_response`.

Non-inference management routes (the ``/v1/{path}`` catchall, incl.
``POST /v1/messages/count_tokens``, and the ``/api/{path}`` passthrough)
STILL forward to the real upstream unchanged.
"""

from __future__ import annotations

import logging
import os
import ssl
from typing import TYPE_CHECKING, Any

import certifi
import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from screamingface.plugins.claude_frontend._classifier import (
    AUX_STUB_TEXT,
    is_auxiliary_request,
)
from screamingface.plugins.claude_frontend._session import SessionHook
from screamingface.plugins.claude_frontend._url4_context import (
    resolve_prompt_expression,
    resolve_static_context,
)
from screamingface.plugins.frontend_base import make_tracer, redact_headers, truncate
from screamingface.plugins.frontend_base.terminal_response import (
    build_anthropic_message,
    serialize_transcript,
    stream_anthropic_sse,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings

FORWARD_HEADERS = {
    "anthropic-version",
    "anthropic-beta",
    "x-api-key",
    "content-type",
    "authorization",
    "accept",
    "x-sf-trace-id",
}

_SENSITIVE_HEADERS = {"x-api-key", "authorization"}
_PLUGIN_NAME = "claude-frontend"

_tracer = make_tracer(_PLUGIN_NAME)


def _record_trace_id(request: Request) -> str | None:
    """Extract x-sf-trace-id header and record it on the current span."""
    trace_id = request.headers.get("x-sf-trace-id")
    _tracer.record_trace_id(trace_id)
    return trace_id


def _extract_turns(body: dict[str, Any]) -> list[tuple[str, str]]:
    """Extract conversation turns as ``(role, text)`` tuples for the ``$prompt`` blob.

    Decision A (conversation-aware): the FULL transcript is serialized, not just the
    last user turn. Each Anthropic ``messages`` entry contributes one ``(role, text)``
    tuple; list-shaped content concatenates its ``text`` blocks.
    """
    turns: list[tuple[str, str]] = []
    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            text = content if isinstance(content, str) else str(content)
        if text:
            turns.append((role, text))
    return turns


def create_router(
    settings: ClaudeFrontendSettings,
    app: Any = None,
    plugin: Any = None,
    hooks: Any = None,
) -> APIRouter:
    upstream_url = settings.upstream_url.rstrip("/")
    session_service_url = settings.session_service_url
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    logger.info("Proxy SSL context using certifi CA: %s", certifi.where())

    import socket as _sock

    def _log_dns(domain: str) -> None:
        try:
            results = _sock.getaddrinfo(domain, 443, _sock.AF_INET)
            logger.info("DNS probe for %s → %s", domain, results[0][4][0])
        except Exception as e:  # noqa: BLE001 — diagnostic only
            logger.warning("DNS probe for %s failed: %s", domain, e)

    router = APIRouter(tags=["claude-frontend"])

    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        return headers

    @router.post("/v1/messages", response_model=None, operation_id="proxy_messages")
    async def proxy_messages(request: Request) -> Response:
        """Terminal inference: resolve the active spec, synthesize the Anthropic
        response in-process, and return it. No upstream inference forward.
        """
        body = await request.json()
        is_streaming = body.get("stream", False)
        model = body.get("model", "claude-opus-4-1-20250805")
        _record_trace_id(request)

        # Auxiliary (utility-model) requests — Claude Code's title/topic/quota Haiku
        # calls — must never reach /ensemble. The classifier forces USER for any real
        # main-loop turn (identity/tools present) BEFORE the model check, so a real
        # prompt is never stubbed. Auxiliary → minimal synthetic envelope, returned
        # BEFORE session enrichment and url4 resolution (SF-241). Fail-loud: the
        # decision is logged and recorded on the span, never silent.
        if is_auxiliary_request(
            body,
            utility_models=settings.utility_models,
            enabled=settings.filter_auxiliary_requests,
        ):
            _tracer.set_attrs({"url4.classified": "auxiliary", "url4.aux_model": model})
            logger.info(
                "[E2E-TRACE] PROXY classified AUX (model=%s) → synthetic, no /ensemble | stream=%s",
                model,
                is_streaming,
            )
            if is_streaming:
                return StreamingResponse(
                    stream_anthropic_sse(AUX_STUB_TEXT, model, prompt_text=""),
                    media_type="text/event-stream",
                )
            return JSONResponse(
                content=build_anthropic_message(AUX_STUB_TEXT, model, prompt_text=""),
                status_code=200,
            )

        # Stage 1: session enrichment
        session = SessionHook.from_request(
            session_id=os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id"),
            service_url=session_service_url,
            hooks=hooks,
        )
        body = await session.enrich(body, tracer=_tracer)

        # Stage 2: url4 resolution → (resolved_text, error_dict)
        raw_expression = plugin.get_active_expression() if plugin else None
        is_prompt_spec = bool(raw_expression and "$prompt" in raw_expression)
        prompt_blob = serialize_transcript(_extract_turns(body)) if is_prompt_spec else ""

        resolved_text: str | None = None
        error_dict: dict[str, Any] | None = None
        if raw_expression and "$prompt" in raw_expression:
            # Branch on the raw value (not the ``is_prompt_spec`` bool) so pyright
            # narrows ``raw_expression`` to ``str`` here — no production ``assert``.
            resolved_text, error_dict = await resolve_prompt_expression(
                body,
                raw_expression=raw_expression,
                settings=settings,
                plugin=plugin,
                app=app,
                tracer=_tracer,
                prompt_text=prompt_blob,
            )
        elif raw_expression:
            resolved_text, error_dict = resolve_static_context(
                body,
                raw_expression=raw_expression,
                settings=settings,
                plugin=plugin,
            )

        logger.info(
            "[E2E-TRACE] PROXY received %s /v1/messages | terminal (no upstream) | stream=%s",
            request.method,
            is_streaming,
        )

        # Stage 3: error path (fake-200, branched on is_streaming) — #244 visibility
        if error_dict is not None:
            error_text = error_dict["content"][0]["text"]
            if is_streaming:
                return StreamingResponse(
                    stream_anthropic_sse(error_text, model),
                    media_type="text/event-stream",
                )
            return JSONResponse(content=error_dict, status_code=200)

        # Stage 4: success. ``resolved_text`` is None only when there is no active
        # spec — synthesize an empty envelope (no upstream call) per Decision.
        result_text = resolved_text or ""
        _tracer.set_attrs({"url4.result_length": len(result_text)})

        response_dict = build_anthropic_message(result_text, model, prompt_text=prompt_blob)

        if is_streaming:
            await session.save(response_dict, streaming=True, tracer=_tracer)

            async def gen():
                async for chunk in stream_anthropic_sse(
                    result_text, model, prompt_text=prompt_blob
                ):
                    yield chunk

            return StreamingResponse(gen(), media_type="text/event-stream")

        await session.save(response_dict, streaming=False, tracer=_tracer)
        return JSONResponse(content=response_dict, status_code=200)

    @router.get("/v1/{path:path}", response_model=None, operation_id="proxy_catchall_get")
    @router.post("/v1/{path:path}", response_model=None, operation_id="proxy_catchall_post")
    async def proxy_catchall(request: Request, path: str) -> Response:
        headers = _build_headers(request)
        url = f"{upstream_url}/v1/{path}"
        method = request.method
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        trace_id = _record_trace_id(request)
        body = await request.body()
        kwargs: dict[str, Any] = {"headers": headers}
        if body:
            kwargs["content"] = body

        _tracer.set_headers("request.headers", redact_headers(headers, _SENSITIVE_HEADERS))
        if body:
            _tracer.set_attrs({"request.body": truncate(body.decode(errors="replace"))})

        if _tracer.enabled:
            with _tracer.start_client_span(f"{method} {url}") as span:
                _tracer.set_attrs({"http.method": method, "http.url": url}, span=span)
                if trace_id:
                    _tracer.set_attrs({"sf.trace_id": trace_id}, span=span)
                _tracer.set_headers(
                    "request.headers",
                    redact_headers(headers, _SENSITIVE_HEADERS),
                    span=span,
                )
                if body:
                    _tracer.set_attrs(
                        {"request.body": truncate(body.decode(errors="replace"))},
                        span=span,
                    )
                async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                    resp = await client.request(method, url, **kwargs)
                _tracer.set_attrs(
                    {
                        "http.status_code": resp.status_code,
                        "response.body": truncate(resp.text),
                    },
                    span=span,
                )
                _tracer.set_headers("response.headers", dict(resp.headers), span=span)
        else:
            async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                resp = await client.request(method, url, **kwargs)

        _tracer.set_attrs(
            {"response.body": truncate(resp.text), "http.status_code": resp.status_code}
        )
        _tracer.set_headers("response.headers", dict(resp.headers))

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return StreamingResponse(
                iter([resp.content]),
                media_type="text/event-stream",
                status_code=resp.status_code,
            )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

    @router.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        response_model=None,
        operation_id="proxy_passthrough",
    )
    async def proxy_passthrough(request: Request, path: str) -> Response:
        """Forward /api/* requests to the real upstream (telemetry, OAuth, etc.)."""
        headers = _build_headers(request)
        url = f"{upstream_url}/api/{path}"
        method = request.method
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        _record_trace_id(request)
        _log_dns("api.anthropic.com")
        logger.info("Passthrough %s %s → upstream %s", method, f"/api/{path}", url)

        body = await request.body()
        kwargs: dict[str, Any] = {"headers": headers}
        if body:
            kwargs["content"] = body

        async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
            resp = await client.request(method, url, **kwargs)

        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type,
        )

    return router
