"""Claude API proxy router — streaming and non-streaming support."""

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


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        k: (v[:8] + "…" if k.lower() in _SENSITIVE_HEADERS and len(v) > 8 else v)
        for k, v in headers.items()
    }


def _truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more chars)"


def _get_tracer():  # type: ignore[no-untyped-def]
    try:
        from opentelemetry import trace

        return trace.get_tracer("screamingface.proxy")
    except ImportError:
        return None


def _set_span_attrs(attrs: dict[str, Any], span=None) -> None:  # type: ignore[no-untyped-def]
    try:
        from opentelemetry import trace

        span = span or trace.get_current_span()
        if span and span.is_recording():
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
    """Extract x-sf-trace-id (injected by mitmproxy addon) and record it on the current OTEL span."""
    trace_id = request.headers.get("x-sf-trace-id")
    if trace_id:
        _set_span_attrs({"sf.trace_id": trace_id})
    return trace_id


def create_router(settings: ClaudeFrontendSettings) -> APIRouter:
    upstream_url = settings.upstream_url.rstrip("/")
    api_key_env = settings.api_key_env
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    logger.info("Proxy SSL context using certifi CA: %s", certifi.where())

    # Diagnostic: check DNS override at request time
    import socket as _sock

    def _log_dns(domain: str) -> None:
        try:
            results = _sock.getaddrinfo(domain, 443, _sock.AF_INET)
            logger.info("DNS probe for %s → %s", domain, results[0][4][0])
        except Exception as e:
            logger.warning("DNS probe for %s failed: %s", domain, e)

    router = APIRouter(tags=["claude-frontend"])

    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        if "x-api-key" not in headers and "authorization" not in headers:
            api_key = os.environ.get(api_key_env, "")
            if api_key:
                headers["x-api-key"] = api_key
        return headers

    @router.post("/v1/messages", response_model=None, operation_id="proxy_messages")
    async def proxy_messages(request: Request) -> Response:
        body = await request.json()

        headers = _build_headers(request)
        # Preserve query params (e.g. ?beta=true) that Claude Code sends
        qs = str(request.url.query)
        url = f"{upstream_url}/v1/messages"
        if qs:
            url = f"{url}?{qs}"
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        tracer = _get_tracer()

        # Record mitmproxy trace ID on the server span
        trace_id = _record_trace_id(request)

        # Server span: just record the raw request body
        _set_span_attrs({"request.body": _truncate(json.dumps(body))})
        _set_span_headers("request.headers", _redact_headers(headers))

        is_streaming = body.get("stream", False)
        logger.info(
            "PROXY >>> forwarding to %s | stream=%s | system_prompt_len=%s | msg_count=%s | trace=%s",
            url,
            is_streaming,
            len(json.dumps(body.get("system", ""))) if body.get("system") else 0,
            len(body.get("messages", [])),
            trace_id,
        )
        logger.info("[E2E-TRACE] PROXY received %s /v1/messages | forwarding to %s", request.method, url)

        if is_streaming:
            client = httpx.AsyncClient(timeout=timeout, verify=ssl_ctx)
            upstream_span = _start_client_span_detached(tracer, f"POST {url}") if tracer else None
            if upstream_span:
                _set_span_attrs({"http.method": "POST", "http.url": url}, upstream_span)
                if trace_id:
                    _set_span_attrs({"sf.trace_id": trace_id}, upstream_span)
                _set_span_headers("request.headers", _redact_headers(headers), upstream_span)
                _set_span_attrs({"request.body": _truncate(json.dumps(body))}, upstream_span)

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
                            _set_span_headers(
                                "response.headers",
                                dict(resp.headers),
                                upstream_span,
                            )
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
                    if upstream_span:
                        upstream_span.end()
                    await client.aclose()
                    logger.info("STREAM >>> client closed")

            return StreamingResponse(stream_response(), media_type="text/event-stream")
        else:
            if tracer:
                with _start_client_span(tracer, f"POST {url}") as span:
                    _set_span_attrs({"http.method": "POST", "http.url": url}, span)
                    if trace_id:
                        _set_span_attrs({"sf.trace_id": trace_id}, span)
                    _set_span_headers("request.headers", _redact_headers(headers), span)
                    _set_span_attrs({"request.body": _truncate(json.dumps(body))}, span)
                    async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                        resp = await client.post(url, json=body, headers=headers)
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
                    resp = await client.post(url, json=body, headers=headers)
            _set_span_attrs(
                {
                    "response.body": _truncate(resp.text),
                    "http.status_code": resp.status_code,
                },
            )
            _set_span_headers("response.headers", dict(resp.headers))
            logger.info("[E2E-TRACE] PROXY response status=%d", resp.status_code)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

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
            {
                "response.body": _truncate(resp.text),
                "http.status_code": resp.status_code,
            },
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
        """Forward /api/* requests to the real upstream (Claude Code telemetry, OAuth, etc.)."""
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
