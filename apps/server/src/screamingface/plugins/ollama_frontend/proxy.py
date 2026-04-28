"""Ollama /api/chat proxy router — streaming (NDJSON) and non-streaming support."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from screamingface.plugins.frontend_base import make_tracer, redact_headers, truncate

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from screamingface.plugins.ollama_frontend.plugin import OllamaFrontendSettings

FORWARD_HEADERS = {
    "content-type",
    "authorization",
    "accept",
    "x-sf-trace-id",
}

_SENSITIVE_HEADERS = {"authorization"}
_PLUGIN_NAME = "ollama-frontend"

_tracer = make_tracer(_PLUGIN_NAME)


def _record_trace_id(request: Request) -> str | None:
    trace_id = request.headers.get("x-sf-trace-id")
    _tracer.record_trace_id(trace_id)
    return trace_id


def _trace_request_context(body: dict[str, Any]) -> None:
    """Record request-level attributes and per-message child spans."""
    if not _tracer.enabled:
        return

    messages = body.get("messages", [])

    _tracer.set_attrs(
        {
            "ollama.model": body.get("model", "?"),
            "ollama.stream": body.get("stream", True),
            "ollama.messages_count": len(messages),
            "ollama.has_tools": bool(body.get("tools")),
        }
    )

    for i, msg in enumerate(messages):
        role = msg.get("role", "?") if isinstance(msg, dict) else "?"
        with _tracer.start_current_span(f"message[{i}] {role}") as span:
            _tracer.set_attrs({"role": role}, span=span)
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    _tracer.set_attrs(
                        {"content_length": len(content), "content": truncate(content, limit=1000)},
                        span=span,
                    )
                tool_calls = msg.get("tool_calls") or []
                if tool_calls:
                    _tracer.set_attrs({"tool_calls_count": len(tool_calls)}, span=span)


def _parse_ndjson_response(raw: str) -> dict[str, Any] | None:
    """Reconstruct a single Ollama /api/chat response from NDJSON stream.

    Concatenates ``message.content`` across chunks; keeps the final chunk's
    metadata (model, created_at, done_reason, usage fields).
    """
    final: dict[str, Any] = {}
    content_acc = ""
    role = "assistant"

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg = event.get("message") or {}
        if isinstance(msg, dict):
            role = msg.get("role", role)
            content_acc += msg.get("content", "") or ""

        if event.get("done"):
            final = dict(event)

    if not final:
        return None

    final["message"] = {"role": role, "content": content_acc}
    return final


def _extract_last_user_text(messages: list[dict[str, Any]]) -> str | None:
    """Return the text of the last ``role == "user"`` message, or None."""
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        return None
    return None


def _replace_last_user_message(messages: list[dict[str, Any]], new_text: str) -> None:
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, dict) and msg.get("role") == "user":
            messages[i] = {"role": "user", "content": new_text}
            return


def _inject_system_message(messages: list[dict[str, Any]], text: str, mode: str) -> None:
    """Ensure messages[0] is a system message with *text* applied per *mode*.

    - No existing system message → insert ``{"role":"system","content":text}`` at index 0.
    - Existing system, mode="concat" → prepend ``text + "\\n\\n"`` to content.
    - Existing system, mode="replace" → replace content with ``text``.
    """
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        existing = messages[0].get("content", "") or ""
        if mode == "replace":
            messages[0]["content"] = text
        else:
            messages[0]["content"] = f"{text}\n\n{existing}" if existing else text
    else:
        messages.insert(0, {"role": "system", "content": text})


def _embed_context(
    body: dict[str, Any],
    resolved_context: str,
    settings: OllamaFrontendSettings,
) -> None:
    """Embed resolved url4 context into the Ollama request body per settings."""
    messages = body.setdefault("messages", [])
    if settings.embed_target == "user":
        last_user_text = _extract_last_user_text(messages)
        if last_user_text is not None:
            combined = (
                resolved_context
                if settings.embed_mode == "replace"
                else f"{resolved_context}\n\n{last_user_text}"
            )
            _replace_last_user_message(messages, combined)
    else:  # system
        wrapped = f"{settings.system_prompt}\n\n{resolved_context}"
        _inject_system_message(messages, wrapped, settings.embed_mode)


def create_router(
    settings: OllamaFrontendSettings,
    app: Any = None,
    plugin: Any = None,
    hooks: Any = None,
) -> APIRouter:
    upstream_url = settings.upstream_url.rstrip("/")
    session_service_url = settings.session_service_url

    router = APIRouter(tags=["ollama-frontend"])

    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        # Optional bearer-token fallback from env
        if "authorization" not in headers:
            api_key = os.environ.get("OLLAMA_API_KEY", "")
            if api_key:
                headers["authorization"] = f"Bearer {api_key}"
        return headers

    @router.post("/api/chat", response_model=None, operation_id="proxy_chat")
    async def proxy_chat(request: Request) -> Response:
        body = await request.json()

        # --- Session enrichment (before url4 injection) ---
        session_id = os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id")
        original_user_msg = None
        if session_id and session_service_url and hooks:
            msgs = body.get("messages", [])
            if msgs:
                original_user_msg = msgs[-1].copy() if isinstance(msgs[-1], dict) else msgs[-1]
            with _tracer.start_current_span("session.enrich_request"):
                _tracer.set_attrs(
                    {"session.id": session_id, "session.service_url": session_service_url}
                )
                try:
                    results = await hooks.emit_async(
                        "session.enrich_request",
                        body=body,
                        session_id=session_id,
                        session_service_url=session_service_url,
                    )
                    modified = False
                    for result in results:
                        if result is not None:
                            body = result
                            modified = True
                            break
                    _tracer.set_attrs({"session.modified": modified})
                except Exception:
                    logger.warning("Session enrichment failed for %s", session_id, exc_info=True)

        # --- URL4 context injection ---
        raw_expression = plugin.get_active_expression() if plugin else None

        if raw_expression and "$prompt" in raw_expression:
            messages = body.get("messages", [])
            last_user_text = _extract_last_user_text(messages)
            if last_user_text:
                substituted = raw_expression  # fallback for error formatting
                with _tracer.start_current_span("url4.$prompt") as prompt_span:
                    try:
                        if prompt_span and prompt_span.is_recording():
                            prompt_span.set_attribute("sf.plugin", _PLUGIN_NAME)
                            prompt_span.set_attribute("url4.raw_expression", raw_expression)
                            prompt_span.set_attribute("url4.user_text_length", len(last_user_text))

                        backend_url = (
                            settings.backend_url.rstrip("/") if settings.backend_url else None
                        )

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
                            blob_key = request.app.state.blob_store.store(
                                last_user_text.encode("utf-8"), "text/plain; charset=utf-8"
                            )

                        blob_url = f"/data/{blob_key}"
                        substituted = raw_expression.replace("$prompt", blob_url)

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
                            prompt_span.set_attribute("url4.blob_url", blob_url)
                            prompt_span.set_attribute(
                                "url4.substituted_expression", truncate(substituted)
                            )
                            prompt_span.set_attribute("url4.final_text_length", len(final_text))
                            prompt_span.set_attribute(
                                "url4.final_text_preview", truncate(final_text, 1000)
                            )
                            prompt_span.set_attribute("url4.status", "ok")

                        if final_text:
                            _embed_context(body, final_text, settings)
                            logger.info(
                                "$prompt: blob=%s resolved %d chars → target=%s mode=%s",
                                blob_key,
                                len(final_text),
                                settings.embed_target,
                                settings.embed_mode,
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
                        error_text = (
                            f"[url4 error] Resolution failed for spec '{spec_name}'\n\n"
                            f"Expression: {truncate(raw_expression, 200)}\n"
                            f"Substituted: {truncate(substituted, 200)}\n\n"
                            f"Error: {exc.__class__.__name__}: {exc}\n\n"
                            f"Traceback:\n{tb_str}"
                        )
                        error_response = {
                            "model": body.get("model", "unknown"),
                            "created_at": "1970-01-01T00:00:00Z",
                            "message": {"role": "assistant", "content": error_text},
                            "done": True,
                            "done_reason": "stop",
                        }
                        return JSONResponse(content=error_response, status_code=200)
        elif raw_expression:
            try:
                resolved_context = plugin.resolve_context() if plugin else None
            except Exception as exc:
                import traceback as _tb

                logger.warning("Static context resolution failed", exc_info=True)
                tb_str = "".join(_tb.format_exception(exc))
                spec_name = settings.active_spec or "unknown"
                error_text = (
                    f"[url4 error] Static context resolution failed for spec '{spec_name}'\n\n"
                    f"Expression: {truncate(raw_expression, 200)}\n\n"
                    f"Error: {exc.__class__.__name__}: {exc}\n\n"
                    f"Traceback:\n{tb_str}"
                )
                error_response = {
                    "model": body.get("model", "unknown"),
                    "created_at": "1970-01-01T00:00:00Z",
                    "message": {"role": "assistant", "content": error_text},
                    "done": True,
                    "done_reason": "stop",
                }
                return JSONResponse(content=error_response, status_code=200)
            if resolved_context:
                _embed_context(body, resolved_context, settings)
                logger.info(
                    "Injected url4 context (%d chars) target=%s mode=%s",
                    len(resolved_context),
                    settings.embed_target,
                    settings.embed_mode,
                )

        # Trace the FINAL request body
        if _tracer.enabled:
            with _tracer.start_current_span("ollama.request_body") as body_span:
                _tracer.set_attrs(
                    {"description": "Final request body sent to Ollama (after url4 injection)"},
                    span=body_span,
                )
                _trace_request_context(body)
        else:
            _trace_request_context(body)

        headers = _build_headers(request)
        qs = str(request.url.query)
        url = f"{upstream_url}/api/chat"
        if qs:
            url = f"{url}?{qs}"
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        trace_id = _record_trace_id(request)

        _tracer.set_attrs({"request.body": truncate(json.dumps(body))})
        _tracer.set_headers("request.headers", redact_headers(headers, _SENSITIVE_HEADERS))

        # Ollama defaults stream=true when not specified
        is_streaming = body.get("stream", True)
        logger.info(
            "PROXY >>> ollama %s | stream=%s | msgs=%d | trace=%s",
            url,
            is_streaming,
            len(body.get("messages", [])),
            trace_id,
        )

        if is_streaming:
            client = httpx.AsyncClient(timeout=timeout)
            upstream_span = _tracer.start_client_span_detached("ollama.POST /api/chat")
            if upstream_span:
                _tracer.set_attrs({"http.method": "POST", "http.url": url}, span=upstream_span)
                if trace_id:
                    _tracer.set_attrs({"sf.trace_id": trace_id}, span=upstream_span)
                _tracer.set_headers(
                    "request.headers",
                    redact_headers(headers, _SENSITIVE_HEADERS),
                    span=upstream_span,
                )
                _tracer.set_attrs({"request.body": truncate(json.dumps(body))}, span=upstream_span)

            async def stream_response():
                chunks: list[bytes] = []
                try:
                    async with client.stream("POST", url, json=body, headers=headers) as resp:
                        if upstream_span:
                            _tracer.set_attrs(
                                {"http.status_code": resp.status_code}, span=upstream_span
                            )
                            _tracer.set_headers(
                                "response.headers", dict(resp.headers), span=upstream_span
                            )
                        async for chunk in resp.aiter_bytes():
                            chunks.append(chunk)
                            yield chunk
                except Exception as exc:
                    logger.error("STREAM >>> error: %s", exc, exc_info=True)
                    raise
                finally:
                    if chunks:
                        raw = b"".join(chunks).decode(errors="replace")
                        if upstream_span:
                            _tracer.set_attrs({"response.body": truncate(raw)}, span=upstream_span)
                        _tracer.set_attrs({"response.body": truncate(raw)})

                        # Session save
                        if session_id and session_service_url and hooks and original_user_msg:
                            response_data = _parse_ndjson_response(raw)
                            if response_data:
                                with _tracer.start_current_span("session.save_response"):
                                    _tracer.set_attrs(
                                        {
                                            "session.id": session_id,
                                            "session.service_url": session_service_url,
                                            "session.streaming": True,
                                        }
                                    )
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

            return StreamingResponse(stream_response(), media_type="application/x-ndjson")

        # Non-streaming
        if _tracer.enabled:
            with _tracer.start_client_span(f"POST {url}") as span:
                _tracer.set_attrs({"http.method": "POST", "http.url": url}, span=span)
                if trace_id:
                    _tracer.set_attrs({"sf.trace_id": trace_id}, span=span)
                _tracer.set_headers(
                    "request.headers", redact_headers(headers, _SENSITIVE_HEADERS), span=span
                )
                _tracer.set_attrs({"request.body": truncate(json.dumps(body))}, span=span)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=body, headers=headers)
                _tracer.set_attrs(
                    {"http.status_code": resp.status_code, "response.body": truncate(resp.text)},
                    span=span,
                )
                _tracer.set_headers("response.headers", dict(resp.headers), span=span)
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=body, headers=headers)

        _tracer.set_attrs(
            {"response.body": truncate(resp.text), "http.status_code": resp.status_code}
        )
        _tracer.set_headers("response.headers", dict(resp.headers))

        response_data = resp.json()
        if session_id and session_service_url and hooks and original_user_msg:
            with _tracer.start_current_span("session.save_response"):
                _tracer.set_attrs(
                    {
                        "session.id": session_id,
                        "session.service_url": session_service_url,
                        "session.streaming": False,
                    }
                )
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

    @router.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        response_model=None,
        operation_id="proxy_passthrough",
    )
    async def proxy_passthrough(request: Request, path: str) -> Response:
        """Forward any other /api/* path (tags, show, pull, embeddings, …) unchanged."""
        # /api/chat is matched by the dedicated handler above due to route order.
        headers = _build_headers(request)
        url = f"{upstream_url}/api/{path}"
        method = request.method
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)
        _record_trace_id(request)
        logger.info("Passthrough %s /api/%s → %s", method, path, url)

        body = await request.body()
        kwargs: dict[str, Any] = {"headers": headers}
        if body:
            kwargs["content"] = body

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, **kwargs)

        content_type = resp.headers.get("content-type", "")
        if "application/x-ndjson" in content_type:
            return StreamingResponse(
                iter([resp.content]),
                media_type="application/x-ndjson",
                status_code=resp.status_code,
            )
        if "json" in content_type:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type or None,
        )

    return router
