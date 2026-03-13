"""Claude API proxy router — streaming and non-streaming support."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from screamingface.plugins.claude_proxy.plugin import ClaudeProxySettings

FORWARD_HEADERS = {
    "anthropic-version",
    "anthropic-beta",
    "x-api-key",
    "content-type",
    "authorization",
    "accept",
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


def create_router(settings: ClaudeProxySettings) -> APIRouter:
    upstream_url = settings.upstream_url.rstrip("/")
    api_key_env = settings.api_key_env

    router = APIRouter(tags=["claude-proxy"])

    async def _resolve_url4(request: Request, body: dict[str, Any]) -> str | None:
        """Resolve the url4 config and return the result text, or None to skip."""
        url4config = getattr(request.app.state, "config", None)
        if url4config is not None:
            url4config = url4config.url4config
        if not url4config:
            logger.info("ENRICH >>> SKIPPED (no url4config)")
            return None

        # Only resolve on the first turn — subsequent turns are passed through.
        messages = body.get("messages", [])
        roles = [m.get("role") for m in messages]
        has_assistant = any(r == "assistant" for r in roles)
        logger.info(
            "ENRICH >>> msg_count=%d roles=%s has_assistant=%s", len(messages), roles, has_assistant
        )
        if has_assistant:
            logger.info("ENRICH >>> SKIPPED (conversation already has assistant messages)")
            return None

        try:
            from screamingface.core.url4 import resolve

            # Extract the user's prompt from the last user message
            user_prompt = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        user_prompt = content
                    elif isinstance(content, list):
                        user_prompt = " ".join(
                            block.get("text", "")
                            for block in content
                            if isinstance(block, dict) and block.get("type") == "text"
                        )
                    break

            # Strip <system-reminder>...</system-reminder> tags injected by
            # Claude Code — they're metadata, not the user's actual prompt.
            user_prompt = re.sub(
                r"<system-reminder>.*?</system-reminder>",
                "",
                user_prompt,
                flags=re.DOTALL,
            ).strip()

            # Replace template placeholders
            config = request.app.state.config
            port = str(config.server.port)
            templated = url4config.replace("{prompt}", quote(user_prompt, safe=""))
            templated = templated.replace("{port}", port)
            logger.info("url4 resolve — prompt: %s", user_prompt[:200])

            result = await asyncio.wait_for(resolve(templated), timeout=120.0)
            logger.info("url4 resolve — result: %s", result[:200])
            return result
        except Exception:
            logger.warning("url4 resolution failed, falling through to Anthropic", exc_info=True)
            return None

    def _check_host(request: Request) -> None:
        intercept_domains: set[str] | None = getattr(request.app.state, "intercept_domains", None)
        if intercept_domains is None:
            return
        host = request.headers.get("host", "").split(":")[0]
        if host not in intercept_domains:
            raise HTTPException(status_code=404)

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
        _check_host(request)
        body = await request.json()

        # If url4 resolves, return the result directly — no second LLM call.
        url4_result = await _resolve_url4(request, body)
        if url4_result is not None:
            import uuid

            synthetic = {
                "id": f"msg_sf_{uuid.uuid4().hex[:24]}",
                "type": "message",
                "role": "assistant",
                "model": body.get("model", "url4"),
                "content": [{"type": "text", "text": url4_result}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
            logger.info("PROXY >>> returning url4 result directly (no Anthropic call)")
            return JSONResponse(content=synthetic, status_code=200)

        headers = _build_headers(request)
        # Preserve query params (e.g. ?beta=true) that Claude Code sends
        qs = str(request.url.query)
        url = f"{upstream_url}/v1/messages"
        if qs:
            url = f"{url}?{qs}"
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        tracer = _get_tracer()

        # Server span: just record the raw request body
        _set_span_attrs({"request.body": _truncate(json.dumps(body))})
        _set_span_headers("request.headers", _redact_headers(headers))

        is_streaming = body.get("stream", False)
        logger.info(
            "PROXY >>> forwarding to %s | stream=%s | system_prompt_len=%s | msg_count=%s",
            url,
            is_streaming,
            len(json.dumps(body.get("system", ""))) if body.get("system") else 0,
            len(body.get("messages", [])),
        )

        if is_streaming:
            client = httpx.AsyncClient(timeout=timeout)
            upstream_span = _start_client_span_detached(tracer, f"POST {url}") if tracer else None
            if upstream_span:
                _set_span_attrs({"http.method": "POST", "http.url": url}, upstream_span)
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
                    _set_span_headers("request.headers", _redact_headers(headers), span)
                    _set_span_attrs({"request.body": _truncate(json.dumps(body))}, span)
                    async with httpx.AsyncClient(timeout=timeout) as client:
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
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=body, headers=headers)
            _set_span_attrs(
                {"response.body": _truncate(resp.text), "http.status_code": resp.status_code},
            )
            _set_span_headers("response.headers", dict(resp.headers))
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

    @router.get("/v1/{path:path}", response_model=None, operation_id="proxy_catchall_get")
    @router.post("/v1/{path:path}", response_model=None, operation_id="proxy_catchall_post")
    async def proxy_catchall(request: Request, path: str) -> Response:
        _check_host(request)
        headers = _build_headers(request)
        url = f"{upstream_url}/v1/{path}"
        method = request.method
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        tracer = _get_tracer()

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
                _set_span_headers("request.headers", _redact_headers(headers), span)
                if body:
                    _set_span_attrs(
                        {"request.body": _truncate(body.decode(errors="replace"))},
                        span,
                    )
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.request(method, url, **kwargs)
                _set_span_attrs(
                    {"http.status_code": resp.status_code, "response.body": _truncate(resp.text)},
                    span,
                )
                _set_span_headers("response.headers", dict(resp.headers), span)
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(method, url, **kwargs)

        _set_span_attrs(
            {"response.body": _truncate(resp.text), "http.status_code": resp.status_code},
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

    return router
