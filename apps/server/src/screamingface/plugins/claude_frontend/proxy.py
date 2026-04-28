"""Claude API proxy router — streaming and non-streaming support.

The hot path is :func:`proxy_messages`. Its three responsibilities are
implemented as focused helpers and orchestrated from a thin handler:

- Session enrichment + save — :mod:`._session`
- URL4 ``$prompt`` / static context resolution — :mod:`._url4_context`
- Upstream forwarding (streaming + non-streaming) — inline below

All tracing, SSE reconstruction, and message-surgery utilities live in
this file (they're small and specific to the Anthropic wire format).
"""

from __future__ import annotations

import json
import logging
import os
import ssl
from typing import TYPE_CHECKING, Any

import certifi
import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from screamingface.plugins.claude_frontend._observability import trace_request_context
from screamingface.plugins.claude_frontend._session import SessionHook
from screamingface.plugins.claude_frontend._sse import parse_sse_response
from screamingface.plugins.claude_frontend._url4_context import (
    resolve_prompt_expression,
    resolve_static_context,
)
from screamingface.plugins.frontend_base import make_tracer, redact_headers, truncate

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

# Always-on request dumps are noisy; opt-in via env var.
_DEBUG_DUMP_ENV = "SF_PROXY_DEBUG_DUMP"

_tracer = make_tracer(_PLUGIN_NAME)


def _record_trace_id(request: Request) -> str | None:
    """Extract x-sf-trace-id header and record it on the current span."""
    trace_id = request.headers.get("x-sf-trace-id")
    _tracer.record_trace_id(trace_id)
    return trace_id


def _trace_request_context(body: dict[str, Any]) -> None:
    """Thin wrapper preserving the existing call site name."""
    trace_request_context(body, _tracer)


def _extract_last_user_text(messages: list[dict[str, Any]]) -> str | None:
    """Extract the user's actual prompt from the last user message.

    Claude Code packs ``<system-reminder>`` blocks (MCP instructions,
    skills, etc.) inside user messages alongside the real prompt. We
    skip any text block starting with ``<system-reminder>``.
    """
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            if content.lstrip().startswith("<system-reminder>"):
                return None
            return content
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict)
                and b.get("type") == "text"
                and not b.get("text", "").lstrip().startswith("<system-reminder>")
            ]
            return texts[-1] if texts else None
    return None


def _replace_last_user_message(messages: list[dict[str, Any]], new_text: str) -> None:
    """Replace only the user's actual text in the last user message.

    Preserves ``<system-reminder>`` blocks, ``cache_control`` markers,
    ``tool_result`` blocks, and any other content blocks.
    """
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") != "user":
            continue
        content = messages[i].get("content")
        if isinstance(content, str):
            messages[i] = {"role": "user", "content": new_text}
            return
        if isinstance(content, list):
            for j in range(len(content) - 1, -1, -1):
                block = content[j]
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and not block.get("text", "").lstrip().startswith("<system-reminder>")
                ):
                    content[j] = {"type": "text", "text": new_text}
                    return
            content.append({"type": "text", "text": new_text})
        return


def _inject_system_context(body: dict[str, Any], text: str) -> None:
    existing = body.get("system")
    if existing is None:
        body["system"] = [{"type": "text", "text": text}]
    elif isinstance(existing, str):
        body["system"] = existing + "\n\n" + text
    elif isinstance(existing, list):
        existing.append({"type": "text", "text": text})


def _embed_context(
    body: dict[str, Any],
    resolved_context: str,
    settings: ClaudeFrontendSettings,
) -> None:
    """Embed resolved url4 context per plugin settings."""
    if settings.embed_target == "user":
        messages = body.get("messages", [])
        last_user_text = _extract_last_user_text(messages)
        if last_user_text:
            if settings.embed_mode == "concat":
                combined = f"{last_user_text}\n\n{resolved_context}"
            else:
                combined = resolved_context
            _replace_last_user_message(messages, combined)
    else:
        wrapped = f"{settings.system_prompt}\n\n{resolved_context}"
        _inject_system_context(body, wrapped)


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
        if "x-api-key" not in headers and "authorization" not in headers:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                headers["x-api-key"] = api_key
        return headers

    @router.post("/v1/messages", response_model=None, operation_id="proxy_messages")
    async def proxy_messages(request: Request) -> Response:
        body = await request.json()

        # Stage 1: session enrichment
        session = SessionHook.from_request(
            session_id=os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id"),
            service_url=session_service_url,
            hooks=hooks,
        )
        body = await session.enrich(body, tracer=_tracer)

        # Stage 2: url4 context injection (either path may short-circuit)
        raw_expression = plugin.get_active_expression() if plugin else None
        if raw_expression and "$prompt" in raw_expression:
            last_user_text = _extract_last_user_text(body.get("messages", []))
            if last_user_text:
                short_circuit = await resolve_prompt_expression(
                    body,
                    raw_expression=raw_expression,
                    settings=settings,
                    plugin=plugin,
                    app=app,
                    tracer=_tracer,
                    last_user_text=last_user_text,
                    embed_context=_embed_context,
                )
                if short_circuit is not None:
                    return short_circuit
        elif raw_expression:
            short_circuit = resolve_static_context(
                body,
                raw_expression=raw_expression,
                settings=settings,
                plugin=plugin,
                embed_context=_embed_context,
            )
            if short_circuit is not None:
                return short_circuit

        # Stage 3: trace the final body and forward to Anthropic
        if _tracer.enabled:
            with _tracer.start_current_span("anthropic.request_body") as body_span:
                _tracer.set_attrs(
                    {
                        "description": "Final request body sent to Anthropic API "
                        "(after url4 injection)",
                    },
                    span=body_span,
                )
                _trace_request_context(body)
        else:
            _trace_request_context(body)

        headers = _build_headers(request)
        qs = str(request.url.query)
        url = f"{upstream_url}/v1/messages"
        if qs:
            url = f"{url}?{qs}"
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        trace_id = _record_trace_id(request)

        _tracer.set_attrs({"request.body": truncate(json.dumps(body))})
        _tracer.set_headers("request.headers", redact_headers(headers, _SENSITIVE_HEADERS))

        is_streaming = body.get("stream", False)
        _maybe_dump_request(body)
        logger.info(
            "PROXY >>> forwarding to %s | stream=%s | sys_len=%s | msgs=%s | trace=%s",
            url,
            is_streaming,
            len(json.dumps(body.get("system", ""))) if body.get("system") else 0,
            len(body.get("messages", [])),
            trace_id,
        )
        logger.info(
            "[E2E-TRACE] PROXY received %s /v1/messages | forwarding to %s",
            request.method,
            url,
        )

        if is_streaming:
            return await _forward_streaming(
                url=url,
                headers=headers,
                body=body,
                timeout=timeout,
                ssl_ctx=ssl_ctx,
                trace_id=trace_id,
                session=session,
            )
        return await _forward_unary(
            url=url,
            headers=headers,
            body=body,
            timeout=timeout,
            ssl_ctx=ssl_ctx,
            trace_id=trace_id,
            session=session,
        )

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


# ---------------------------------------------------------------------------
# Stage 3 helpers — upstream forwarding
# ---------------------------------------------------------------------------


def _maybe_dump_request(body: dict[str, Any]) -> None:
    """Dump the outgoing request body to /tmp for debugging — opt-in."""
    if not os.environ.get(_DEBUG_DUMP_ENV):
        return
    import tempfile
    from pathlib import Path

    debug_dir = Path(tempfile.gettempdir()) / "sf-proxy-debug"
    debug_dir.mkdir(exist_ok=True)
    debug_file = debug_dir / "last_request.json"
    debug_file.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    logger.info("PROXY >>> dumped request body to %s", debug_file)


async def _forward_streaming(
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: httpx.Timeout,
    ssl_ctx: ssl.SSLContext,
    trace_id: str | None,
    session: SessionHook,
) -> StreamingResponse:
    """Stream Anthropic's SSE response through, saving the session turn on completion."""
    client = httpx.AsyncClient(timeout=timeout, verify=ssl_ctx)
    upstream_span = _tracer.start_client_span_detached("anthropic.POST /v1/messages")
    if upstream_span:
        _tracer.set_attrs({"http.method": "POST", "http.url": url}, span=upstream_span)
        if trace_id:
            _tracer.set_attrs({"sf.trace_id": trace_id}, span=upstream_span)
        _tracer.set_headers(
            "request.headers", redact_headers(headers, _SENSITIVE_HEADERS), span=upstream_span
        )
        _tracer.set_attrs({"request.body": truncate(json.dumps(body))}, span=upstream_span)
        logger.info("TRACE: created upstream span %s", upstream_span.get_span_context().span_id)

    async def stream_response():
        chunks: list[bytes] = []
        try:
            logger.info("STREAM >>> opening upstream connection to Anthropic")
            async with client.stream("POST", url, json=body, headers=headers) as resp:
                logger.info(
                    "STREAM >>> upstream responded: status=%s content-type=%s",
                    resp.status_code,
                    resp.headers.get("content-type", "?"),
                )
                if upstream_span:
                    _tracer.set_attrs({"http.status_code": resp.status_code}, span=upstream_span)
                    _tracer.set_headers("response.headers", dict(resp.headers), span=upstream_span)
                chunk_count = 0
                async for chunk in resp.aiter_bytes():
                    chunk_count += 1
                    chunks.append(chunk)
                    if chunk_count <= 3:
                        logger.info(
                            "STREAM >>> chunk #%d (%d bytes): %s",
                            chunk_count,
                            len(chunk),
                            chunk[:200],
                        )
                    yield chunk
                logger.info(
                    "STREAM >>> finished: %d chunks, %d total bytes",
                    chunk_count,
                    sum(len(c) for c in chunks),
                )
                logger.info("[E2E-TRACE] PROXY response status=%d", resp.status_code)
        except Exception as exc:
            logger.error("STREAM >>> ERROR during streaming: %s", exc, exc_info=True)
            raise
        finally:
            if chunks:
                raw = b"".join(chunks).decode(errors="replace")
                if upstream_span:
                    _tracer.set_attrs({"response.body": truncate(raw)}, span=upstream_span)
                _tracer.set_attrs({"response.body": truncate(raw)})
                if session.enabled:
                    response_data = parse_sse_response(raw)
                    if response_data:
                        await session.save(response_data, streaming=True, tracer=_tracer)
            if upstream_span:
                upstream_span.end()
            await client.aclose()
            logger.info("STREAM >>> client closed")

    return StreamingResponse(stream_response(), media_type="text/event-stream")


async def _forward_unary(
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: httpx.Timeout,
    ssl_ctx: ssl.SSLContext,
    trace_id: str | None,
    session: SessionHook,
) -> JSONResponse:
    """Non-streaming POST, parse JSON, save session turn."""
    with _tracer.start_client_span(f"POST {url}") as span:
        if span:
            _tracer.set_attrs({"http.method": "POST", "http.url": url}, span=span)
            if trace_id:
                _tracer.set_attrs({"sf.trace_id": trace_id}, span=span)
            _tracer.set_headers(
                "request.headers", redact_headers(headers, _SENSITIVE_HEADERS), span=span
            )
            _tracer.set_attrs({"request.body": truncate(json.dumps(body))}, span=span)
        async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
            resp = await client.post(url, json=body, headers=headers)
        if span:
            _tracer.set_attrs(
                {
                    "http.status_code": resp.status_code,
                    "response.body": truncate(resp.text),
                },
                span=span,
            )
            _tracer.set_headers("response.headers", dict(resp.headers), span=span)

    _tracer.set_attrs({"response.body": truncate(resp.text), "http.status_code": resp.status_code})
    _tracer.set_headers("response.headers", dict(resp.headers))
    logger.info("[E2E-TRACE] PROXY response status=%d", resp.status_code)

    response_data = resp.json()
    await session.save(response_data, streaming=False, tracer=_tracer)
    return JSONResponse(content=response_data, status_code=resp.status_code)
