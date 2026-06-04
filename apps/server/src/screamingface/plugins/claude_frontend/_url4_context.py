"""URL4 context resolution helpers used by ``proxy_messages``.

Two resolution paths live here:

- **``$prompt`` substitution** (:func:`resolve_prompt_expression`) —
  the active spec contains the ``$prompt`` sentinel. The user's last
  message text is stored as a blob, the sentinel is substituted with
  the blob URL, the full expression is evaluated through url4, and
  the result is embedded back into the outgoing request.

- **Static resolution** (:func:`resolve_static_context`) — the active
  spec has no ``$prompt``. The plugin's cached resolved context is
  embedded directly.

Both paths return ``None`` on success (request body is mutated in
place) and a :class:`JSONResponse` error on failure — the proxy
short-circuits with that response instead of forwarding. Error
responses are shaped as fake-200 Anthropic messages so Claude Code
surfaces the error text in the chat UI.

Extracted from ``proxy.py`` during SF-107.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

import httpx
from fastapi.responses import JSONResponse

from screamingface.plugins.llm_base.constants import PROMPT_PREVIEW_LIMIT

logger = logging.getLogger(__name__)


__all__ = ["resolve_prompt_expression", "resolve_static_context"]


def _truncate(text: str, limit: int = PROMPT_PREVIEW_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more chars)"


def _build_error_response(
    body: dict[str, Any],
    *,
    spec_name: str,
    header: str,
    raw_expression: str,
    substituted: str | None,
    exc: Exception,
) -> JSONResponse:
    """Build a fake-200 Anthropic response whose text is the url4 error."""
    tb_str = "".join(traceback.format_exception(exc))
    lines: list[str] = [
        f"[url4 error] {header} for spec '{spec_name}'",
        "",
        f"Expression: {_truncate(raw_expression, 200)}",
    ]
    if substituted is not None:
        lines.append(f"Substituted: {_truncate(substituted, 200)}")
    lines += [
        "",
        f"Error: {exc.__class__.__name__}: {exc}",
        "",
        "Traceback:",
        tb_str,
    ]
    return JSONResponse(
        content={
            "id": f"sf_error_{id(exc):x}",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "\n".join(lines)}],
            "model": body.get("model", "unknown"),
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
        status_code=200,
    )


async def _store_prompt_blob(
    text: str,
    *,
    app: Any,
    backend_url: str | None,
    tracer: Any,
) -> str:
    """Store the user prompt text as a blob and return its key.

    ``tracer`` is a :class:`frontend_base.ProxyTracer`.

    Prefers the in-process BlobStore on ``app.state.blob_store`` whenever
    available — the HTTP path (``backend_url`` is set) only fires when
    there's no in-process app reference. This avoids self-loops where the
    proxy talks back to its own SF over HTTP and a stale ``backend_url``
    (wrong port, wrong host) breaks the round-trip with a 404.
    """
    if app is not None and getattr(getattr(app, "state", None), "blob_store", None) is not None:
        return app.state.blob_store.store(text.encode("utf-8"), "text/plain; charset=utf-8")

    if backend_url:
        blob_url_target = f"{backend_url}/data"
        with tracer.start_client_span("POST /data"):
            tracer.set_attrs({"http.method": "POST", "http.url": blob_url_target})
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), verify=False) as dc:
                blob_resp = await dc.post(
                    blob_url_target,
                    content=text.encode("utf-8"),
                    headers={"content-type": "text/plain; charset=utf-8"},
                )
                blob_resp.raise_for_status()
                blob_key = blob_resp.json()["key"]
            tracer.set_attrs(
                {
                    "http.status_code": blob_resp.status_code,
                    "data.key": blob_key,
                    "data.size": len(text),
                }
            )
        return blob_key

    raise RuntimeError(
        "_store_prompt_blob requires either an in-process app with blob_store "
        "or a non-empty backend_url"
    )


async def _resolve_expression(
    expression: str,
    *,
    app: Any,
    backend_url: str | None,
    tracer: Any,
) -> str:
    """Evaluate a url4 expression and return the final text.

    Resolves from the *same locus* where :func:`_store_prompt_blob` wrote the
    prompt blob, so the ``/data/{key}`` lookup always hits the store that holds
    it:

    - In-process whenever this ``app`` owns the blob store (``app.state``
      ``.blob_store``) — the interpreter is the same one ``GET /ensemble`` uses.
    - Otherwise the blob was POSTed to the main server, so resolve via that
      server's ``GET /ensemble`` over HTTP.

    The guard mirrors :func:`_store_prompt_blob` exactly; diverging the two is
    what caused store/resolve to target different stores (a 404 on ``/data``).
    """
    if app is not None and getattr(getattr(app, "state", None), "blob_store", None) is not None:
        from screamingface.plugins.url4_executor.interpreter import Url4Interpreter

        interpreter = Url4Interpreter(app=app)
        return await interpreter.evaluate(expression)

    if backend_url:
        ens_url = f"{backend_url}/ensemble"
        with tracer.start_client_span("GET /ensemble"):
            tracer.set_attrs(
                {
                    "http.method": "GET",
                    "http.url": ens_url,
                    "url4.expression": _truncate(expression, 500),
                }
            )
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0), verify=False) as ec:
                ens_resp = await ec.get(ens_url, params={"q": expression})
                ens_resp.raise_for_status()
                final_text = ens_resp.text
            tracer.set_attrs(
                {
                    "http.status_code": ens_resp.status_code,
                    "url4.result_length": len(final_text),
                    "url4.response_body": _truncate(final_text),
                }
            )
        return final_text

    raise RuntimeError(
        "_resolve_expression requires either an in-process app with blob_store "
        "or a non-empty backend_url"
    )


async def resolve_prompt_expression(
    body: dict[str, Any],
    *,
    raw_expression: str,
    settings: Any,
    plugin: Any,  # noqa: ARG001 — reserved for future plugin-scoped hooks
    app: Any,
    tracer: Any,
    last_user_text: str,
    embed_context: Any,
) -> JSONResponse | None:
    """Substitute ``$prompt``, resolve, embed the result back into body.

    ``tracer`` is a :class:`frontend_base.ProxyTracer`. Returns ``None``
    on success (body mutated in place) or a :class:`JSONResponse` if
    anything in the pipeline raises; the proxy uses that return value
    to short-circuit with a fake-200 error response.
    """
    substituted: str | None = None
    with tracer.start_current_span("url4.$prompt") as prompt_span:
        try:
            if prompt_span and prompt_span.is_recording():
                tracer.set_attrs(
                    {
                        "url4.raw_expression": raw_expression,
                        "url4.user_text_length": len(last_user_text),
                    },
                    span=prompt_span,
                )

            backend_url = settings.backend_url.rstrip("/") if settings.backend_url else None

            blob_key = await _store_prompt_blob(
                last_user_text,
                app=app,
                backend_url=backend_url,
                tracer=tracer,
            )
            blob_url = f"/data/{blob_key}"
            substituted = raw_expression.replace("$prompt", blob_url)

            if prompt_span and prompt_span.is_recording():
                tracer.set_attrs(
                    {
                        "url4.blob_url": blob_url,
                        "url4.substituted_expression": _truncate(substituted),
                    },
                    span=prompt_span,
                )

            final_text = await _resolve_expression(
                substituted,
                app=app,
                backend_url=backend_url,
                tracer=tracer,
            )

            if prompt_span and prompt_span.is_recording():
                tracer.set_attrs(
                    {
                        "url4.final_text_length": len(final_text),
                        "url4.final_text_preview": _truncate(final_text, 1000),
                        "url4.status": "ok",
                    },
                    span=prompt_span,
                )

            if final_text:
                embed_context(body, final_text, settings)
                logger.info(
                    "$prompt: blob=%s resolved %d chars → target=%s mode=%s",
                    blob_key,
                    len(final_text),
                    settings.embed_target,
                    settings.embed_mode,
                )
            return None

        except Exception as exc:
            if prompt_span and prompt_span.is_recording():
                prompt_span.set_attribute("url4.status", "error")
                prompt_span.set_attribute("url4.error", str(exc))
                prompt_span.record_exception(exc)
            logger.warning("$prompt substitution failed", exc_info=True)
            return _build_error_response(
                body,
                spec_name=settings.active_spec or "unknown",
                header="Resolution failed",
                raw_expression=raw_expression,
                substituted=substituted,
                exc=exc,
            )


def resolve_static_context(
    body: dict[str, Any],
    *,
    raw_expression: str,
    settings: Any,
    plugin: Any,
    embed_context: Any,
) -> JSONResponse | None:
    """No ``$prompt`` — use plugin-cached resolved context.

    Reads the plugin's cached context **non-blocking** (``get_cached_context``):
    it returns immediately with cached text or ``None`` and warms in the
    background, so the chat is never blocked on a (potentially 5-minute)
    ensemble resolve. The trade-off: a cold spec resolves on a *subsequent*
    request, not the first one.
    """
    try:
        resolved_context = plugin.get_cached_context() if plugin else None
    except Exception as exc:
        logger.warning("Static context resolution failed", exc_info=True)
        return _build_error_response(
            body,
            spec_name=settings.active_spec or "unknown",
            header="Static context resolution failed",
            raw_expression=raw_expression,
            substituted=None,
            exc=exc,
        )

    if resolved_context:
        embed_context(body, resolved_context, settings)
        logger.info(
            "Injected cached url4 context (%d chars) embed_target=%s embed_mode=%s",
            len(resolved_context),
            settings.embed_target,
            settings.embed_mode,
        )
    return None
