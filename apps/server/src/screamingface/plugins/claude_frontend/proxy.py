"""Claude API proxy router — streaming and non-streaming support."""

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


_PLUGIN_NAME = "claude-frontend"


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
    """Create child spans for each system block and message in the final request to Anthropic."""
    tracer = _get_tracer()
    if not tracer:
        return

    _t = _truncate  # alias for readability

    # Request-level attributes on the current (server) span
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

    # System blocks
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

    # Messages — each as a child span with role, content preview, and block breakdown
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
    """Reconstruct an Anthropic Messages response from SSE stream data.

    Parses message_start, content_block_start/delta/stop, and message_delta
    events to build a response dict equivalent to a non-streaming response.
    """
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

    Claude Code packs system-reminder blocks (MCP instructions, skills, etc.)
    as text blocks inside the user message alongside the real prompt.  We only
    want the user's text — skip any block whose text starts with
    ``<system-reminder>``.

    Returns None only if the last user message has no eligible text blocks
    (pure tool_result submission with no user text).
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
    ``tool_result`` blocks, and any other content blocks — only the last
    non-system-reminder text block is swapped.
    """
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") != "user":
            continue
        content = messages[i].get("content")

        # String shorthand — replace directly
        if isinstance(content, str):
            messages[i] = {"role": "user", "content": new_text}
            return

        # Array of blocks — find and replace only the user's text block
        if isinstance(content, list):
            # Walk backwards to find the last non-system-reminder text block
            for j in range(len(content) - 1, -1, -1):
                block = content[j]
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and not block.get("text", "").lstrip().startswith("<system-reminder>")
                ):
                    content[j] = {"type": "text", "text": new_text}
                    return

            # No eligible text block found — append as new block
            content.append({"type": "text", "text": new_text})
        return


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
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                headers["x-api-key"] = api_key
        return headers

    @router.post("/v1/messages", response_model=None, operation_id="proxy_messages")
    async def proxy_messages(request: Request) -> Response:
        body = await request.json()

        # --- Session enrichment (before url4 injection) ---
        # Prefer env-var session ID (per-session proxy) over header (legacy)
        session_id = os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id")
        original_user_msg = None
        if session_id and session_service_url and hooks:
            msgs = body.get("messages", [])
            if msgs:
                original_user_msg = msgs[-1].copy() if isinstance(msgs[-1], dict) else msgs[-1]
            try:
                results = await hooks.emit_async(
                    "session.enrich_request",
                    body=body,
                    session_id=session_id,
                    session_service_url=session_service_url,
                )
                for result in results:
                    if result is not None:
                        body = result
                        break
            except Exception:
                logger.warning("Session enrichment failed for %s", session_id, exc_info=True)

        # --- URL4 context injection ---
        # If the active spec contains $prompt, substitute the user's last message
        # text inline (quoted for url4 grammar), resolve the full expression via
        # the url4-executor, and replace the last user message with the result.
        # Otherwise fall back to the original behavior (append to system prompt).
        raw_expression = plugin.get_active_expression() if plugin else None

        if raw_expression and "$prompt" in raw_expression:
            messages = body.get("messages", [])
            last_user_text = _extract_last_user_text(messages)
            if last_user_text:
                tracer = _get_tracer()
                span_ctx = (
                    tracer.start_as_current_span("url4.$prompt") if tracer else _nullcontext()
                )
                with span_ctx as prompt_span:
                    try:
                        if prompt_span and prompt_span.is_recording():
                            prompt_span.set_attribute("sf.plugin", _PLUGIN_NAME)
                            prompt_span.set_attribute("url4.raw_expression", raw_expression)
                            prompt_span.set_attribute("url4.user_text_length", len(last_user_text))

                        # Determine backend: HTTP to main server, or in-process
                        backend_url = (
                            settings.backend_url.rstrip("/") if settings.backend_url else None
                        )

                        # Store user prompt as blob on the backend server
                        if backend_url:
                            async with httpx.AsyncClient(
                                timeout=httpx.Timeout(30.0), verify=False
                            ) as dc:
                                blob_resp = await dc.post(
                                    f"{backend_url}/data",
                                    content=last_user_text.encode("utf-8"),
                                    headers={"content-type": "text/plain; charset=utf-8"},
                                )
                                blob_resp.raise_for_status()
                                blob_key = blob_resp.json()["key"]
                        else:
                            from screamingface.plugins.data_store.routes import store_blob

                            blob_key = store_blob(
                                last_user_text.encode("utf-8"), "text/plain; charset=utf-8"
                            )

                        blob_url = f"/data/{blob_key}"
                        substituted = raw_expression.replace("$prompt", blob_url)

                        if prompt_span and prompt_span.is_recording():
                            prompt_span.set_attribute("url4.blob_url", blob_url)
                            prompt_span.set_attribute(
                                "url4.substituted_expression", _truncate(substituted)
                            )

                        # Resolve the full expression via /ensemble endpoint
                        if backend_url:
                            async with httpx.AsyncClient(
                                timeout=httpx.Timeout(300.0), verify=False
                            ) as ec:
                                ens_resp = await ec.get(
                                    f"{backend_url}/ensemble", params={"q": substituted}
                                )
                                ens_resp.raise_for_status()
                                final_text = ens_resp.text
                        else:
                            from screamingface.plugins.url4_executor.interpreter import (
                                Url4Interpreter,
                            )

                            interpreter = Url4Interpreter(app=app)
                            final_text = await interpreter.evaluate(substituted)

                        if prompt_span and prompt_span.is_recording():
                            prompt_span.set_attribute("url4.final_text_length", len(final_text))
                            prompt_span.set_attribute(
                                "url4.final_text_preview", _truncate(final_text, 1000)
                            )
                            prompt_span.set_attribute("url4.status", "ok")

                        if final_text:
                            combined = f"{last_user_text}\n\n{final_text}"
                            _replace_last_user_message(messages, combined)
                            logger.info(
                                "$prompt: blob=%s resolved %d chars → appended to user message",
                                blob_key,
                                len(final_text),
                            )
                    except Exception as exc:
                        if prompt_span and prompt_span.is_recording():
                            prompt_span.set_attribute("url4.status", "error")
                            prompt_span.set_attribute("url4.error", str(exc))
                            prompt_span.record_exception(exc)
                        import traceback as _tb

                        logger.warning("$prompt substitution failed", exc_info=True)
                        tb_str = "".join(_tb.format_exception(exc))
                        spec_name = settings.active_spec or "unknown"
                        error_lines = [
                            f"[url4 error] Resolution failed for spec '{spec_name}'",
                            "",
                            f"Expression: {_truncate(raw_expression, 200)}",
                            f"Substituted: {_truncate(substituted, 200)}"
                            if "substituted" in dir()
                            else "",
                            "",
                            f"Error: {exc.__class__.__name__}: {exc}",
                            "",
                            "Traceback:",
                            tb_str,
                        ]
                        error_response = {
                            "id": f"sf_error_{id(exc):x}",
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "text", "text": "\n".join(error_lines)}],
                            "model": body.get("model", "unknown"),
                            "stop_reason": "end_turn",
                            "stop_sequence": None,
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        }
                        return JSONResponse(content=error_response, status_code=200)
        elif raw_expression:
            # No $prompt — resolve statically and append to system prompt
            try:
                resolved_context = plugin.resolve_context() if plugin else None
            except Exception as exc:
                import traceback as _tb

                logger.warning("Static context resolution failed", exc_info=True)
                tb_str = "".join(_tb.format_exception(exc))
                spec_name = settings.active_spec or "unknown"
                error_lines = [
                    f"[url4 error] Static context resolution failed for spec '{spec_name}'",
                    "",
                    f"Expression: {_truncate(raw_expression, 200)}",
                    "",
                    f"Error: {exc.__class__.__name__}: {exc}",
                    "",
                    "Traceback:",
                    tb_str,
                ]
                error_response = {
                    "id": f"sf_error_{id(exc):x}",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "\n".join(error_lines)}],
                    "model": body.get("model", "unknown"),
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
                return JSONResponse(content=error_response, status_code=200)
            if resolved_context:
                wrapped = (
                    "Please be accurate and keep this information "
                    "constantly in your context:\n\n" + resolved_context
                )
                existing = body.get("system")
                if existing is None:
                    body["system"] = [{"type": "text", "text": wrapped}]
                elif isinstance(existing, str):
                    body["system"] = existing + "\n\n" + wrapped
                elif isinstance(existing, list):
                    existing.append({"type": "text", "text": wrapped})
                logger.info(
                    "Injected cached url4 context (%d chars) into system prompt",
                    len(resolved_context),
                )

        # Trace the FINAL request body (after all modifications) as child spans.
        # This is exactly what gets sent to api.anthropic.com.
        tracer = _get_tracer()
        if tracer:
            with tracer.start_as_current_span("anthropic.request_body") as body_span:
                body_span.set_attribute("sf.plugin", _PLUGIN_NAME)
                body_span.set_attribute(
                    "description", "Final request body sent to Anthropic API (after url4 injection)"
                )
                _trace_request_context(body)
        else:
            _trace_request_context(body)

        headers = _build_headers(request)
        # Preserve query params (e.g. ?beta=true) that Claude Code sends
        qs = str(request.url.query)
        url = f"{upstream_url}/v1/messages"
        if qs:
            url = f"{url}?{qs}"
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        tracer = _get_tracer()

        # Record trace ID on the server span
        trace_id = _record_trace_id(request)

        # Server span: just record the raw request body
        _set_span_attrs({"request.body": _truncate(json.dumps(body))})
        _set_span_headers("request.headers", _redact_headers(headers))

        is_streaming = body.get("stream", False)
        # Debug: dump full request body to temp file for inspection
        import tempfile
        from pathlib import Path

        debug_dir = Path(tempfile.gettempdir()) / "sf-proxy-debug"
        debug_dir.mkdir(exist_ok=True)
        debug_file = debug_dir / "last_request.json"
        debug_file.write_text(json.dumps(body, indent=2, ensure_ascii=False))
        logger.info("PROXY >>> dumped request body to %s", debug_file)
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
            client = httpx.AsyncClient(timeout=timeout, verify=ssl_ctx)
            upstream_span = (
                _start_client_span_detached(tracer, "anthropic.POST /v1/messages")
                if tracer
                else None
            )
            if upstream_span:
                _set_span_attrs({"sf.plugin": _PLUGIN_NAME}, upstream_span)
                _set_span_attrs({"http.method": "POST", "http.url": url}, upstream_span)
                if trace_id:
                    _set_span_attrs({"sf.trace_id": trace_id}, upstream_span)
                _set_span_headers("request.headers", _redact_headers(headers), upstream_span)
                _set_span_attrs({"request.body": _truncate(json.dumps(body))}, upstream_span)
                logger.info(
                    "TRACE: created upstream span %s", upstream_span.get_span_context().span_id
                )

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

                        # --- Session save (streaming) ---
                        if session_id and session_service_url and hooks and original_user_msg:
                            response_data = _parse_sse_response(raw)
                            if response_data:
                                try:
                                    await hooks.emit_async(
                                        "session.save_response",
                                        session_id=session_id,
                                        session_service_url=session_service_url,
                                        user_message_body=original_user_msg,
                                        response_body=response_data,
                                    )
                                except Exception:
                                    logger.warning(
                                        "Session save (stream) failed for %s",
                                        session_id,
                                        exc_info=True,
                                    )

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

            # --- Session save (non-streaming) ---
            response_data = resp.json()
            if session_id and session_service_url and hooks and original_user_msg:
                try:
                    await hooks.emit_async(
                        "session.save_response",
                        session_id=session_id,
                        session_service_url=session_service_url,
                        user_message_body=original_user_msg,
                        response_body=response_data,
                    )
                except Exception:
                    logger.warning("Session save failed for %s", session_id, exc_info=True)

            return JSONResponse(content=response_data, status_code=resp.status_code)

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
