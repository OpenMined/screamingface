"""Gemini (Google AI) proxy router — streaming and non-streaming.

The Gemini API uses ``/v1beta/models/{model}:generateContent`` and
``/v1beta/models/{model}:streamGenerateContent`` endpoints.

The proxy intercepts these requests, injects url4 context, and forwards
to the upstream Google AI API.
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

from screamingface.plugins.frontend_base import make_tracer, redact_headers, truncate

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from screamingface.plugins.gemini_frontend.plugin import GeminiFrontendSettings

FORWARD_HEADERS = {
    "content-type",
    "authorization",
    "accept",
    "x-goog-api-key",
    "x-goog-api-client",
    "x-sf-trace-id",
}

_SENSITIVE_HEADERS = {"authorization", "x-goog-api-key"}
_PLUGIN_NAME = "gemini-frontend"

_tracer = make_tracer(_PLUGIN_NAME)


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return redact_headers(headers, _SENSITIVE_HEADERS)


def _truncate(text: str, limit: int | None = None) -> str:
    return truncate(text) if limit is None else truncate(text, limit=limit)


def _set_span_attrs(attrs: dict[str, Any]) -> None:
    _tracer.set_attrs(attrs)


# ---------------------------------------------------------------------------
# Gemini API helpers
# ---------------------------------------------------------------------------


def _extract_last_user_text(body: dict[str, Any]) -> str | None:
    """Extract user's text from Gemini generateContent request.

    Gemini uses ``contents: [{role: "user", parts: [{text: "..."}]}]``.
    """
    contents = body.get("contents")
    if not isinstance(contents, list):
        return None
    for msg in reversed(contents):
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "user":
            continue
        parts = msg.get("parts", [])
        for part in reversed(parts):
            if isinstance(part, dict) and "text" in part:
                return part["text"]
    return None


def _replace_user_text(body: dict[str, Any], new_text: str) -> None:
    """Replace user's text in a Gemini request body."""
    contents = body.get("contents", [])
    for i in range(len(contents) - 1, -1, -1):
        msg = contents[i]
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        parts = msg.get("parts", [])
        for j in range(len(parts) - 1, -1, -1):
            if isinstance(parts[j], dict) and "text" in parts[j]:
                parts[j]["text"] = new_text
                return


def _inject_system_context(body: dict[str, Any], text: str) -> None:
    """Inject text into Gemini's systemInstruction field."""
    existing = body.get("systemInstruction")
    if existing and isinstance(existing, dict):
        parts = existing.get("parts", [])
        parts.append({"text": text})
    else:
        body["systemInstruction"] = {"parts": [{"text": text}]}


def _embed_context(
    body: dict[str, Any],
    resolved_context: str,
    settings: GeminiFrontendSettings,
) -> None:
    if settings.embed_target == "user":
        last_user_text = _extract_last_user_text(body)
        if last_user_text:
            if settings.embed_mode == "concat":
                combined = f"{last_user_text}\n\n{resolved_context}"
            else:
                combined = resolved_context
            _replace_user_text(body, combined)
    else:
        wrapped = f"{settings.system_prompt}\n\n{resolved_context}"
        _inject_system_context(body, wrapped)


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_router(
    settings: GeminiFrontendSettings,
    app: Any = None,
    plugin: Any = None,
    hooks: Any = None,
) -> APIRouter:
    upstream_url = settings.upstream_url.rstrip("/")
    session_service_url = settings.session_service_url
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    router = APIRouter(tags=["gemini-frontend"])

    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        if "x-goog-api-key" not in headers and "authorization" not in headers:
            api_key = os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")
            if api_key:
                headers["x-goog-api-key"] = api_key
        return headers

    @router.api_route(
        "/v1beta/models/{model_path:path}",
        methods=["GET", "POST"],
        response_model=None,
        operation_id="proxy_gemini",
    )
    async def proxy_gemini(request: Request, model_path: str) -> Response:
        url = f"{upstream_url}/v1beta/models/{model_path}"
        # Preserve query string (contains API key for some auth modes)
        qs = str(request.url.query)
        if qs:
            url = f"{url}?{qs}"

        headers = _build_headers(request)
        method = request.method
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)

        _set_span_attrs({"http.url": url, "http.method": method})

        if method == "GET":
            async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                resp = await client.get(url, headers=headers)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

        # POST — likely generateContent or streamGenerateContent
        body = await request.json()

        # --- Session enrichment ---
        session_id = os.environ.get("_SF_SESSION_ID") or request.headers.get("x-session-id")
        if session_id and session_service_url and hooks:
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
                logger.warning(
                    "Session enrichment failed for %s",
                    session_id,
                    exc_info=True,
                )

        # --- URL4 context injection ---
        raw_expression = plugin.get_active_expression() if plugin else None

        if raw_expression and "$prompt" in raw_expression:
            last_user_text = _extract_last_user_text(body)
            if last_user_text:
                try:
                    backend_url = settings.backend_url.rstrip("/") if settings.backend_url else None
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
                            last_user_text.encode("utf-8"),
                            "text/plain; charset=utf-8",
                        )

                    substituted = raw_expression.replace("$prompt", f"/data/{blob_key}")

                    if backend_url:
                        async with httpx.AsyncClient(
                            timeout=httpx.Timeout(300.0), verify=False
                        ) as ec:
                            ens_resp = await ec.get(
                                f"{backend_url}/ensemble",
                                params={"q": substituted},
                            )
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
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": f"[url4 error] {exc.__class__.__name__}: {exc}"}
                                    ],
                                    "role": "model",
                                },
                                "finishReason": "STOP",
                            }
                        ]
                    }
                    return JSONResponse(content=error_response, status_code=200)
        elif raw_expression:
            try:
                resolved_context = plugin.resolve_context() if plugin else None
            except Exception as exc:
                logger.warning("Static context resolution failed", exc_info=True)
                error_response = {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": f"[url4 error] {exc.__class__.__name__}: {exc}"}
                                ],
                                "role": "model",
                            },
                            "finishReason": "STOP",
                        }
                    ]
                }
                return JSONResponse(content=error_response, status_code=200)
            if resolved_context:
                _embed_context(body, resolved_context, settings)

        # --- Forward to upstream ---
        is_streaming = "streamGenerateContent" in model_path

        logger.info(
            "PROXY >>> forwarding to %s | stream=%s",
            url,
            is_streaming,
        )

        if is_streaming:
            client = httpx.AsyncClient(timeout=timeout, verify=ssl_ctx)

            async def stream_response():
                chunks: list[bytes] = []
                try:
                    async with client.stream("POST", url, json=body, headers=headers) as resp:
                        async for chunk in resp.aiter_bytes():
                            chunks.append(chunk)
                            yield chunk
                except Exception as exc:
                    logger.error("STREAM >>> ERROR: %s", exc, exc_info=True)
                    raise
                finally:
                    await client.aclose()

            return StreamingResponse(stream_response(), media_type="application/json")
        else:
            async with httpx.AsyncClient(timeout=timeout, verify=ssl_ctx) as client:
                resp = await client.post(url, json=body, headers=headers)

            _set_span_attrs(
                {
                    "http.status_code": resp.status_code,
                    "response.body": _truncate(resp.text),
                }
            )

            return JSONResponse(content=resp.json(), status_code=resp.status_code)

    @router.api_route(
        "/v1beta/{path:path}",
        methods=["GET", "POST"],
        response_model=None,
        operation_id="proxy_catchall",
    )
    async def proxy_catchall(request: Request, path: str) -> Response:
        headers = _build_headers(request)
        url = f"{upstream_url}/v1beta/{path}"
        qs = str(request.url.query)
        if qs:
            url = f"{url}?{qs}"
        method = request.method
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)

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
