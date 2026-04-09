"""Codex (OpenAI Responses API) proxy router — streaming and non-streaming."""

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
    from screamingface.plugins.codex_frontend.plugin import CodexFrontendSettings

# Headers to forward from the Codex CLI request to the upstream API.
FORWARD_HEADERS = {
    "content-type",
    "authorization",
    "accept",
    "x-sf-trace-id",
    "openai-organization",
    "openai-project",
}

_SENSITIVE_HEADERS = {"authorization"}
_PLUGIN_NAME = "codex-frontend"


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
    trace_id = request.headers.get("x-sf-trace-id")
    if trace_id:
        _set_span_attrs({"sf.trace_id": trace_id})
    return trace_id


# ---------------------------------------------------------------------------
# OpenAI Responses API helpers
# ---------------------------------------------------------------------------


def _extract_last_user_text(body: dict[str, Any]) -> str | None:
    """Extract the user's actual prompt from a Responses API request.

    The Responses API ``input`` field can be:
    - A plain string (simple prompt)
    - A list of message dicts with role/content
    """
    inp = body.get("input")
    if isinstance(inp, str):
        return inp
    if isinstance(inp, list):
        for msg in reversed(inp):
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "user":
                continue
            content = msg.get("content")
            if isinstance(content, str):
                return content
    return None


def _replace_user_text(body: dict[str, Any], new_text: str) -> None:
    """Replace the user's text in a Responses API request body."""
    inp = body.get("input")
    if isinstance(inp, str):
        body["input"] = new_text
        return
    if isinstance(inp, list):
        for i in range(len(inp) - 1, -1, -1):
            msg = inp[i]
            if isinstance(msg, dict) and msg.get("role") == "user":
                if isinstance(msg.get("content"), str):
                    inp[i]["content"] = new_text
                    return
        # No user message found — append
        inp.append({"role": "user", "content": new_text})


def _inject_system_context(body: dict[str, Any], text: str) -> None:
    """Inject text into the Responses API ``instructions`` field."""
    existing = body.get("instructions")
    if existing:
        body["instructions"] = existing + "\n\n" + text
    else:
        body["instructions"] = text


def _embed_context(
    body: dict[str, Any],
    resolved_context: str,
    settings: CodexFrontendSettings,
) -> None:
    """Embed resolved url4 context into the request body per settings."""
    if settings.embed_target == "user":
        last_user_text = _extract_last_user_text(body)
        if last_user_text:
            if settings.embed_mode == "concat":
                combined = f"{last_user_text}\n\n{resolved_context}"
            else:
                combined = resolved_context
            _replace_user_text(body, combined)
    else:  # system
        wrapped = f"{settings.system_prompt}\n\n{resolved_context}"
        _inject_system_context(body, wrapped)


def _parse_sse_response(raw: str) -> dict[str, Any] | None:
    """Reconstruct an OpenAI Responses API response from SSE stream data.

    OpenAI streaming uses ``response.created``, ``response.output_item.*``,
    ``response.content_part.*``, ``response.output_text.*``, and
    ``response.completed`` events.
    """
    response: dict[str, Any] = {}
    output_items: list[dict[str, Any]] = []
    current_item: dict[str, Any] = {}
    current_text = ""

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

        etype = event.get("type", "")

        if etype == "response.created":
            resp_data = event.get("response", {})
            response.update(
                {
                    "id": resp_data.get("id"),
                    "object": "response",
                    "model": resp_data.get("model"),
                    "status": resp_data.get("status"),
                }
            )
        elif etype == "response.output_item.added":
            current_item = event.get("item", {})
            current_text = ""
        elif etype == "response.output_text.delta":
            current_text += event.get("delta", "")
        elif etype == "response.output_item.done":
            item = event.get("item", current_item)
            if current_text and item.get("type") == "message":
                item["content"] = [{"type": "output_text", "text": current_text}]
            output_items.append(item)
            current_item = {}
            current_text = ""
        elif etype == "response.completed":
            resp_data = event.get("response", {})
            response.update(
                {
                    "status": resp_data.get("status", "completed"),
                    "usage": resp_data.get("usage", {}),
                }
            )

    if not response:
        return None

    response["output"] = output_items
    return response


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_router(
    settings: CodexFrontendSettings,
    app: Any = None,
    plugin: Any = None,
    hooks: Any = None,
) -> APIRouter:
    upstream_url = settings.upstream_url.rstrip("/")
    session_service_url = settings.session_service_url
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    router = APIRouter(tags=["codex-frontend"])

    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        if "authorization" not in headers:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                headers["authorization"] = f"Bearer {api_key}"
        return headers

    @router.post("/v1/responses", response_model=None, operation_id="proxy_responses")
    async def proxy_responses(request: Request) -> Response:
        body = await request.json()

        # --- Session enrichment ---
        session_id = os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id")
        original_user_msg = None
        if session_id and session_service_url and hooks:
            original_user_msg = _extract_last_user_text(body)
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
        raw_expression = plugin.get_active_expression() if plugin else None

        if raw_expression and "$prompt" in raw_expression:
            last_user_text = _extract_last_user_text(body)
            if last_user_text:
                try:
                    backend_url = settings.backend_url.rstrip("/") if settings.backend_url else None

                    if backend_url:
                        blob_url_target = f"{backend_url}/data"
                        async with httpx.AsyncClient(
                            timeout=httpx.Timeout(30.0), verify=False
                        ) as dc:
                            blob_resp = await dc.post(
                                blob_url_target,
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

                    if backend_url:
                        ens_url = f"{backend_url}/ensemble"
                        async with httpx.AsyncClient(
                            timeout=httpx.Timeout(300.0), verify=False
                        ) as ec:
                            ens_resp = await ec.get(ens_url, params={"q": substituted})
                            ens_resp.raise_for_status()
                            final_text = ens_resp.text
                    else:
                        from screamingface.plugins.url4_executor.interpreter import (
                            Url4Interpreter,
                        )

                        interpreter = Url4Interpreter(app=app)
                        final_text = await interpreter.evaluate(substituted)

                    if final_text:
                        _embed_context(body, final_text, settings)
                except Exception as exc:
                    logger.warning("$prompt substitution failed", exc_info=True)
                    error_response = {
                        "id": f"sf_error_{id(exc):x}",
                        "object": "response",
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": f"[url4 error] {exc.__class__.__name__}: {exc}",
                                    }
                                ],
                            }
                        ],
                        "status": "failed",
                    }
                    return JSONResponse(content=error_response, status_code=200)
        elif raw_expression:
            try:
                resolved_context = plugin.resolve_context() if plugin else None
            except Exception as exc:
                logger.warning("Static context resolution failed", exc_info=True)
                error_response = {
                    "id": f"sf_error_{id(exc):x}",
                    "object": "response",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": f"[url4 error] {exc.__class__.__name__}: {exc}",
                                }
                            ],
                        }
                    ],
                    "status": "failed",
                }
                return JSONResponse(content=error_response, status_code=200)
            if resolved_context:
                _embed_context(body, resolved_context, settings)

        # --- Forward to upstream ---
        headers = _build_headers(request)
        qs = str(request.url.query)
        url = f"{upstream_url}/v1/responses"
        if qs:
            url = f"{url}?{qs}"
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)

        _record_trace_id(request)
        _set_span_attrs({"request.body": _truncate(json.dumps(body))})
        _set_span_headers("request.headers", _redact_headers(headers))

        is_streaming = body.get("stream", False)

        logger.info(
            "PROXY >>> forwarding to %s | stream=%s | model=%s",
            url,
            is_streaming,
            body.get("model", "?"),
        )

        if is_streaming:
            client = httpx.AsyncClient(timeout=timeout, verify=ssl_ctx)
            tracer = _get_tracer()
            upstream_span = (
                _start_client_span_detached(tracer, "openai.POST /v1/responses") if tracer else None
            )

            async def stream_response():
                chunks: list[bytes] = []
                try:
                    async with client.stream("POST", url, json=body, headers=headers) as resp:
                        if upstream_span:
                            _set_span_attrs({"http.status_code": resp.status_code}, upstream_span)
                        async for chunk in resp.aiter_bytes():
                            chunks.append(chunk)
                            yield chunk
                except Exception as exc:
                    logger.error("STREAM >>> ERROR: %s", exc, exc_info=True)
                    raise
                finally:
                    if chunks:
                        raw = b"".join(chunks).decode(errors="replace")
                        _set_span_attrs({"response.body": _truncate(raw)})

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

            return StreamingResponse(stream_response(), media_type="text/event-stream")
        else:
            async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                resp = await client.post(url, json=body, headers=headers)

            _set_span_attrs(
                {
                    "response.body": _truncate(resp.text),
                    "http.status_code": resp.status_code,
                }
            )

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
        """Forward any other /v1/* requests to upstream."""
        headers = _build_headers(request)
        url = f"{upstream_url}/v1/{path}"
        method = request.method
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)

        body = await request.body()
        kwargs: dict[str, Any] = {"headers": headers}
        if body:
            kwargs["content"] = body

        async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
            resp = await client.request(method, url, **kwargs)

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return StreamingResponse(
                iter([resp.content]),
                media_type="text/event-stream",
                status_code=resp.status_code,
            )
        if "json" in content_type:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type,
        )

    return router
