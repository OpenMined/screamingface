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
from contextlib import nullcontext as _nullcontext
from typing import TYPE_CHECKING, Any

import certifi
import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from screamingface.plugins.claude_frontend._session import SessionHook
from screamingface.plugins.claude_frontend._url4_context import (
    resolve_prompt_expression,
    resolve_static_context,
)
from screamingface.plugins.llm_base.constants import PROMPT_PREVIEW_LIMIT

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


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        k: (v[:8] + "…" if k.lower() in _SENSITIVE_HEADERS and len(v) > 8 else v)
        for k, v in headers.items()
    }


def _truncate(text: str, limit: int = PROMPT_PREVIEW_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more chars)"


def _get_tracer():  # type: ignore[no-untyped-def]
    try:
        from opentelemetry import trace

        return trace.get_tracer(f"screamingface.{_PLUGIN_NAME}")
    except ImportError:
        return None


def _set_span_attrs(attrs: dict[str, Any], span=None) -> None:  # type: ignore[no-untyped-def]
    try:
        from opentelemetry import trace

        span = span or trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute("sf.plugin", _PLUGIN_NAME)
            for k, v in attrs.items():
                span.set_attribute(k, v)
    except ImportError:
        pass


def _set_span_headers(prefix: str, headers: dict[str, str], span=None) -> None:  # type: ignore[no-untyped-def]
    try:
        from opentelemetry import trace

        span = span or trace.get_current_span()
        if span and span.is_recording():
            for k, v in headers.items():
                span.set_attribute(f"{prefix}.{k}", v)
    except ImportError:
        pass


def _start_client_span(tracer, name: str):  # type: ignore[no-untyped-def]
    from opentelemetry.trace import SpanKind

    return tracer.start_as_current_span(name, kind=SpanKind.CLIENT)


def _start_client_span_detached(tracer, name: str):  # type: ignore[no-untyped-def]
    from opentelemetry.trace import SpanKind

    return tracer.start_span(name, kind=SpanKind.CLIENT)


def _record_trace_id(request: Request) -> str | None:
    """Extract x-sf-trace-id header and record it on the current span."""
    trace_id = request.headers.get("x-sf-trace-id")
    if trace_id:
        _set_span_attrs({"sf.trace_id": trace_id})
    return trace_id


def _trace_request_context(body: dict[str, Any]) -> None:
    """Create child spans for each system block and message in the final request."""
    tracer = _get_tracer()
    if not tracer:
        return

    _t = _truncate

    _set_span_attrs(
        {
            "anthropic.model": body.get("model", "?"),
            "anthropic.max_tokens": body.get("max_tokens", 0),
            "anthropic.stream": body.get("stream", False),
            "anthropic.system_block_count": len(body.get("system", []))
            if isinstance(body.get("system"), list)
            else (1 if body.get("system") else 0),
            "anthropic.message_count": len(body.get("messages", [])),
        }
    )

    system = body.get("system")
    if isinstance(system, list):
        for i, block in enumerate(system):
            with tracer.start_as_current_span(f"system[{i}]") as span:
                span.set_attribute("sf.plugin", _PLUGIN_NAME)
                if isinstance(block, dict):
                    span.set_attribute("type", block.get("type", "?"))
                    text = block.get("text", "")
                    span.set_attribute("text_length", len(text))
                    span.set_attribute("text", _t(text, 1000))
                    if "cache_control" in block:
                        span.set_attribute("cache_control", str(block["cache_control"]))
    elif isinstance(system, str):
        with tracer.start_as_current_span("system") as span:
            span.set_attribute("sf.plugin", _PLUGIN_NAME)
            span.set_attribute("text_length", len(system))
            span.set_attribute("text", _t(system, 1000))

    messages = body.get("messages", [])
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        with tracer.start_as_current_span(f"message[{i}] {role}") as span:
            span.set_attribute("sf.plugin", _PLUGIN_NAME)
            span.set_attribute("role", role)
            content = msg.get("content")
            if isinstance(content, str):
                span.set_attribute("content_length", len(content))
                span.set_attribute("content", _t(content, 1000))
            elif isinstance(content, list):
                span.set_attribute("block_count", len(content))
                for j, block in enumerate(content):
                    btype = block.get("type", "?") if isinstance(block, dict) else "?"
                    span.set_attribute(f"block[{j}].type", btype)
                    if btype == "text":
                        text = block.get("text", "")
                        span.set_attribute(f"block[{j}].text_length", len(text))
                        span.set_attribute(f"block[{j}].text", _t(text, 1000))
                    elif btype == "thinking":
                        thinking = block.get("thinking", "")
                        span.set_attribute(f"block[{j}].thinking_length", len(thinking))
                        span.set_attribute(f"block[{j}].thinking", _t(thinking, 1000))
                        span.set_attribute(f"block[{j}].has_signature", "signature" in block)
                    elif btype == "tool_use":
                        span.set_attribute(f"block[{j}].tool_name", block.get("name", "?"))
                        span.set_attribute(f"block[{j}].tool_id", block.get("id", "?"))
                        inp = json.dumps(block.get("input", {}))
                        span.set_attribute(f"block[{j}].input", _t(inp, 1000))
                    elif btype == "tool_result":
                        span.set_attribute(f"block[{j}].tool_use_id", block.get("tool_use_id", "?"))
                        span.set_attribute(f"block[{j}].is_error", block.get("is_error", False))
                        rc = block.get("content", "")
                        if isinstance(rc, str):
                            span.set_attribute(f"block[{j}].content", _t(rc, 1000))
                        elif isinstance(rc, list):
                            span.set_attribute(f"block[{j}].content", _t(json.dumps(rc), 1000))


def _parse_sse_response(raw: str) -> dict[str, Any] | None:
    """Reconstruct an Anthropic Messages response from SSE stream data."""
    response: dict[str, Any] = {}
    content_blocks: list[dict[str, Any]] = []
    current_block: dict[str, Any] = {}

    for line in raw.split("\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        data_str = line[6:]
        if data_str == "[DONE]":
            break
        try:
            event = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")
        if etype == "message_start":
            msg = event.get("message", {})
            response.update(
                {
                    "id": msg.get("id"),
                    "type": msg.get("type", "message"),
                    "role": msg.get("role", "assistant"),
                    "model": msg.get("model"),
                    "usage": msg.get("usage", {}),
                }
            )
        elif etype == "content_block_start":
            current_block = dict(event.get("content_block", {}))
        elif etype == "content_block_delta":
            delta = event.get("delta", {})
            dtype = delta.get("type")
            if dtype == "text_delta":
                current_block.setdefault("text", "")
                current_block["text"] += delta.get("text", "")
            elif dtype == "thinking_delta":
                current_block.setdefault("thinking", "")
                current_block["thinking"] += delta.get("thinking", "")
            elif dtype == "signature_delta":
                current_block.setdefault("signature", "")
                current_block["signature"] += delta.get("signature", "")
            elif dtype == "input_json_delta":
                current_block.setdefault("_input_json", "")
                current_block["_input_json"] += delta.get("partial_json", "")
        elif etype == "content_block_stop":
            if "_input_json" in current_block:
                try:
                    current_block["input"] = json.loads(current_block.pop("_input_json"))
                except json.JSONDecodeError:
                    current_block["input"] = {}
                    current_block.pop("_input_json", None)
            content_blocks.append(current_block)
            current_block = {}
        elif etype == "message_delta":
            delta = event.get("delta", {})
            if "stop_reason" in delta:
                response["stop_reason"] = delta["stop_reason"]
            usage = event.get("usage", {})
            if usage:
                existing_usage = response.get("usage", {})
                existing_usage.update(usage)
                response["usage"] = existing_usage

    if not response:
        return None

    response["content"] = content_blocks
    return response


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
        body = await session.enrich(body, tracer=_get_tracer())

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
                    tracer=_get_tracer(),
                    last_user_text=last_user_text,
                    embed_context=_embed_context,
                    _start_client_span=_start_client_span,
                    _set_span_attrs=_set_span_attrs,
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
        tracer = _get_tracer()
        if tracer:
            with tracer.start_as_current_span("anthropic.request_body") as body_span:
                body_span.set_attribute("sf.plugin", _PLUGIN_NAME)
                body_span.set_attribute(
                    "description",
                    "Final request body sent to Anthropic API (after url4 injection)",
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

        _set_span_attrs({"request.body": _truncate(json.dumps(body))})
        _set_span_headers("request.headers", _redact_headers(headers))

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
                tracer=tracer,
                trace_id=trace_id,
                session=session,
            )
        return await _forward_unary(
            url=url,
            headers=headers,
            body=body,
            timeout=timeout,
            ssl_ctx=ssl_ctx,
            tracer=tracer,
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
        tracer = _get_tracer()
        trace_id = _record_trace_id(request)
        body = await request.body()
        kwargs: dict[str, Any] = {"headers": headers}
        if body:
            kwargs["content"] = body

        _set_span_headers("request.headers", _redact_headers(headers))
        if body:
            _set_span_attrs({"request.body": _truncate(body.decode(errors="replace"))})

        if tracer:
            with _start_client_span(tracer, f"{method} {url}") as span:
                _set_span_attrs({"http.method": method, "http.url": url}, span)
                if trace_id:
                    _set_span_attrs({"sf.trace_id": trace_id}, span)
                _set_span_headers("request.headers", _redact_headers(headers), span)
                if body:
                    _set_span_attrs(
                        {"request.body": _truncate(body.decode(errors="replace"))},
                        span,
                    )
                async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                    resp = await client.request(method, url, **kwargs)
                _set_span_attrs(
                    {
                        "http.status_code": resp.status_code,
                        "response.body": _truncate(resp.text),
                    },
                    span,
                )
                _set_span_headers("response.headers", dict(resp.headers), span)
        else:
            async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                resp = await client.request(method, url, **kwargs)

        _set_span_attrs(
            {"response.body": _truncate(resp.text), "http.status_code": resp.status_code}
        )
        _set_span_headers("response.headers", dict(resp.headers))

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
    tracer: Any,
    trace_id: str | None,
    session: SessionHook,
) -> StreamingResponse:
    """Stream Anthropic's SSE response through, saving the session turn on completion."""
    client = httpx.AsyncClient(timeout=timeout, verify=ssl_ctx)
    upstream_span = (
        _start_client_span_detached(tracer, "anthropic.POST /v1/messages") if tracer else None
    )
    if upstream_span:
        _set_span_attrs({"sf.plugin": _PLUGIN_NAME}, upstream_span)
        _set_span_attrs({"http.method": "POST", "http.url": url}, upstream_span)
        if trace_id:
            _set_span_attrs({"sf.trace_id": trace_id}, upstream_span)
        _set_span_headers("request.headers", _redact_headers(headers), upstream_span)
        _set_span_attrs({"request.body": _truncate(json.dumps(body))}, upstream_span)
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
                    _set_span_attrs({"http.status_code": resp.status_code}, upstream_span)
                    _set_span_headers("response.headers", dict(resp.headers), upstream_span)
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
                    _set_span_attrs({"response.body": _truncate(raw)}, upstream_span)
                _set_span_attrs({"response.body": _truncate(raw)})
                if session.enabled:
                    response_data = _parse_sse_response(raw)
                    if response_data:
                        await session.save(response_data, streaming=True, tracer=_get_tracer())
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
    tracer: Any,
    trace_id: str | None,
    session: SessionHook,
) -> JSONResponse:
    """Non-streaming POST, parse JSON, save session turn."""
    span_ctx = _start_client_span(tracer, f"POST {url}") if tracer else _nullcontext()
    with span_ctx as span:
        if tracer and span:
            _set_span_attrs({"http.method": "POST", "http.url": url}, span)
            if trace_id:
                _set_span_attrs({"sf.trace_id": trace_id}, span)
            _set_span_headers("request.headers", _redact_headers(headers), span)
            _set_span_attrs({"request.body": _truncate(json.dumps(body))}, span)
        async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
            resp = await client.post(url, json=body, headers=headers)
        if tracer and span:
            _set_span_attrs(
                {
                    "http.status_code": resp.status_code,
                    "response.body": _truncate(resp.text),
                },
                span,
            )
            _set_span_headers("response.headers", dict(resp.headers), span)

    _set_span_attrs({"response.body": _truncate(resp.text), "http.status_code": resp.status_code})
    _set_span_headers("response.headers", dict(resp.headers))
    logger.info("[E2E-TRACE] PROXY response status=%d", resp.status_code)

    response_data = resp.json()
    await session.save(response_data, streaming=False, tracer=_get_tracer())
    return JSONResponse(content=response_data, status_code=resp.status_code)
