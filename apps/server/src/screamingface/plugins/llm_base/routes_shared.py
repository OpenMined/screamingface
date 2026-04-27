"""Shared FastAPI router factory for ``*_backend_api`` plugins.

Before this module existed, every direct-API plugin (claude, codex,
gemini, ollama) carried its own ~400-line ``routes.py`` that was 85%
byte-identical to its siblings. The only real differences were:

- the URL prefix (``/claude`` vs ``/codex`` vs …)
- the default model fallback
- the backend instance
- the URL4 interpreter class
- an OTEL span attribute prefix

:func:`build_backend_api_router` captures those four differences in a
:class:`BackendApiConfig` dataclass and generates the whole router.

Plugin ``routes.py`` files shrink to a ~10-line function that builds
the config and calls this factory.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from screamingface.plugins.backend_api_base.models import RunRequest, RunResponse
from screamingface.plugins.llm_base.backend_base import Backend
from screamingface.plugins.llm_base.constants import (
    CLI_ONLY_FIELD_DEFAULTS,
    CLI_ONLY_FIELDS,
    DEFAULT_MAX_TOKENS,
    PROMPT_PREVIEW_LIMIT,
    STDOUT_PREVIEW_LIMIT,
)
from screamingface.plugins.llm_base.errors import (
    AuthError,
    BackendError,
    CredentialNotFoundError,
)
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart, extract_text

logger = logging.getLogger(__name__)


__all__ = ["BackendApiConfig", "build_backend_api_router"]


@dataclass
class BackendApiConfig:
    """Per-provider wiring that drives the shared router factory.

    Attributes:
        name: Plugin name, e.g. ``"claude-backend-api"``. Used as the
            router tag and as the OTEL ``sf.plugin`` attribute value.
        path_prefix: URL prefix without trailing slash, e.g. ``"/claude"``.
            Every generated route lives under this prefix.
        default_model: Fallback model when neither request nor settings
            specify one.
        backend: The :class:`Backend` instance (per-plugin singleton).
        settings: The plugin's settings object (duck-typed: must have
            ``default_model``, ``timeout_seconds``, ``profiles``).
        app: The FastAPI application. Passed into the URL4 interpreter.
        build_interpreter: Callable returning a new URL4 interpreter
            for this backend. Invoked with no arguments — capture
            ``app``/``settings``/``backend`` in the closure.
        span_prefix: Short provider name used as span-attribute prefix
            (e.g. ``"claude"`` produces ``claude.exit_code``). Usually
            the first segment of ``name``.
        operation_id_prefix: Used to name OpenAPI operation IDs. If
            unset, derived from ``name`` by stripping the
            ``-backend-api`` suffix and replacing hyphens with
            underscores.
    """

    name: str
    path_prefix: str
    default_model: str
    backend: Backend
    settings: Any
    app: Any
    build_interpreter: Callable[[], Any]
    span_prefix: str
    operation_id_prefix: str | None = None

    def __post_init__(self) -> None:
        if self.operation_id_prefix is None:
            self.operation_id_prefix = self.name.replace("-backend-api", "").replace("-", "_")


def build_backend_api_router(cfg: BackendApiConfig) -> APIRouter:
    """Produce a FastAPI router with the four canonical backend-API endpoints.

    Endpoints:

    - ``GET  {prefix}/health``
    - ``POST {prefix}/run``
    - ``GET  {prefix}?q=<expr>`` — evaluate a url4 expression
    - ``GET/POST {prefix}/{{profile_name}}`` — profile-based execution
    """
    router = APIRouter(tags=[cfg.name])
    prefix = cfg.path_prefix
    op = cfg.operation_id_prefix
    backend = cfg.backend
    settings = cfg.settings

    @router.get(f"{prefix}/health", response_model=None, operation_id=f"{op}_health")
    async def health() -> JSONResponse:
        model = settings.default_model or cfg.default_model
        status = await backend.health(model=model)
        http_status = 200 if status.authenticated else 503
        return JSONResponse(
            content={
                "authenticated": status.authenticated,
                "model": model,
                "tokens_remaining": status.tokens_remaining,
                "requests_remaining": status.requests_remaining,
                "rate_limit": status.rate_limit,
                "error": status.error,
            },
            status_code=http_status,
        )

    async def _execute(
        request: RunRequest,
    ) -> JSONResponse | StreamingResponse:
        if request.output_format == "stream-json":
            raise HTTPException(
                status_code=501,
                detail=(
                    f"stream-json output is not yet implemented in {cfg.name}. "
                    f"Use output_format='text' or 'json'."
                ),
            )
        if request.files:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"The 'files' field is not supported by {cfg.name} "
                    f"(no sandbox to write to). Include file contents "
                    f"directly in the prompt instead."
                ),
            )

        _record_ignored_fields(request, cfg.name)

        timeout = request.timeout_seconds or settings.timeout_seconds
        model = request.model or settings.default_model or cfg.default_model

        system_parts: list[str] = []
        if request.system_prompt:
            system_parts.append(request.system_prompt)
        if request.append_system_prompt:
            system_parts.append(request.append_system_prompt)
        system = "\n\n".join(system_parts) if system_parts else None

        messages = [CoreMessage(role="user", content=[TextPart(text=request.prompt)])]

        start = time.monotonic()
        try:
            result = await backend.run(
                messages,
                model=model,
                system=system,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=None,
                timeout_seconds=timeout,
            )
            duration = time.monotonic() - start
            stdout = extract_text(result)
            parsed: dict | list | str | None = None
            if request.output_format == "json" and stdout.strip():
                try:
                    parsed = json.loads(stdout)
                except json.JSONDecodeError:
                    parsed = None

            resp = RunResponse(
                exit_code=0,
                stdout=stdout,
                stderr="",
                duration_seconds=round(duration, 3),
                result=parsed,
            )
            _record_span_success(result, duration, stdout, cfg.name, cfg.span_prefix)
            return JSONResponse(content=resp.model_dump(by_alias=True))

        except (CredentialNotFoundError, AuthError) as exc:
            duration = time.monotonic() - start
            logger.warning("%s auth failure: %s", cfg.name, exc)
            resp = RunResponse(
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_seconds=round(duration, 3),
                result=None,
            )
            return JSONResponse(content=resp.model_dump(by_alias=True), status_code=500)
        except BackendError as exc:
            duration = time.monotonic() - start
            logger.warning("%s backend error: %s", cfg.name, exc)
            status = 429 if exc.status == 429 else 502
            resp = RunResponse(
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_seconds=round(duration, 3),
                result=None,
            )
            return JSONResponse(content=resp.model_dump(by_alias=True), status_code=status)

    @router.post(f"{prefix}/run", response_model=None, operation_id=f"{op}_run")
    async def run_endpoint(request: RunRequest) -> JSONResponse | StreamingResponse:
        _reject_cli_only_fields(request, cfg.name)
        return await _execute(request)

    @router.get(prefix, response_model=None, operation_id=f"{op}_url4")
    async def url4(q: str) -> PlainTextResponse:
        interpreter = cfg.build_interpreter()
        try:
            result = await interpreter.evaluate(q)
        except (CredentialNotFoundError, AuthError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except BackendError as exc:
            status = 429 if exc.status == 429 else 502
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        except Exception as exc:
            logger.warning("%s url4 evaluation failed: %s", cfg.name, exc, exc_info=True)
            raise HTTPException(
                status_code=502,
                detail=f"url4 evaluation failed: {exc}",
            ) from exc

        _record_url4_span(q, result, cfg.name)
        return PlainTextResponse(content=result)

    async def _handle_profile(
        profile_name: str,
        prompt: str,
        context: str | None = None,
        raw_context: str | None = None,
    ) -> JSONResponse | StreamingResponse | PlainTextResponse:
        # Local imports to avoid llm-base depending on url4_executor at
        # module-load time (url4_executor depends on backend plugins in
        # its own setup).
        from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
        from screamingface.plugins.url4_executor.url4 import resolve_str

        prof = settings.profiles.get(profile_name)
        if not prof:
            raise HTTPException(status_code=404, detail=f"Unknown profile: {profile_name!r}")

        is_url4 = False
        url4_interpreter = Url4Interpreter(app=cfg.app)
        stripped = prompt.strip()
        if stripped.startswith("(") and "!" in stripped:
            try:
                prompt = await url4_interpreter.evaluate(stripped)
                is_url4 = True
            except Exception as exc:
                logger.warning("url4 prompt resolution failed: %s", exc, exc_info=True)
                raise HTTPException(
                    status_code=502,
                    detail=f"url4 prompt resolution failed: {exc}",
                ) from exc

        resolved_context = ""
        if raw_context:
            resolved_context = raw_context
        elif not is_url4:
            context_expr = context or prof.context
            if context_expr:
                try:
                    resolved_context = await resolve_str(context_expr, cfg.app)
                except Exception as exc:
                    logger.warning("Context resolution failed: %s", exc, exc_info=True)
                    raise HTTPException(
                        status_code=502,
                        detail=f"Context resolution failed: {exc}",
                    ) from exc

        full_prompt = f"{resolved_context}\n\n{prompt}" if resolved_context else prompt

        run_request = RunRequest(
            prompt=full_prompt,
            model=prof.model,
            system_prompt=prof.system_prompt,
            append_system_prompt=prof.append_system_prompt,
            output_format=prof.output_format,
            json_schema=prof.json_schema,
            max_budget_usd=prof.max_budget_usd,
            effort=prof.effort,
            tools=prof.tools,
            allowed_tools=prof.allowed_tools,
            disallowed_tools=prof.disallowed_tools,
            mcp_config=prof.mcp_config,
            permission_mode=prof.permission_mode,
            add_dirs=prof.add_dirs,
            fallback_model=prof.fallback_model,
            dangerously_skip_permissions=prof.dangerously_skip_permissions,
            no_session_persistence=prof.no_session_persistence,
            timeout_seconds=prof.timeout_seconds,
        )
        result = await _execute(run_request)

        if is_url4 and isinstance(result, JSONResponse):
            body = json.loads(bytes(result.body).decode())
            stdout = body.get("so") or body.get("stdout") or ""
            return PlainTextResponse(content=stdout)
        return result

    @router.get(
        f"{prefix}/{{profile_name}}",
        response_model=None,
        operation_id=f"{op}_profile_get",
    )
    async def profile_get(
        profile_name: str,
        prompt: str,
        context: str | None = None,
        raw_context: str | None = None,
    ) -> JSONResponse | StreamingResponse | PlainTextResponse:
        return await _handle_profile(profile_name, prompt, context, raw_context)

    @router.post(
        f"{prefix}/{{profile_name}}",
        response_model=None,
        operation_id=f"{op}_profile_post",
    )
    async def profile_post(
        profile_name: str,
        prompt: str,
        context: str | None = None,
        raw_context: str | None = None,
    ) -> JSONResponse | StreamingResponse | PlainTextResponse:
        return await _handle_profile(profile_name, prompt, context, raw_context)

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reject_cli_only_fields(request: RunRequest, plugin_name: str) -> None:
    """Raise HTTP 422 when a direct API request sets CLI-only fields.

    Direct ``*_backend_api`` plugins talk to provider HTTP APIs — they
    have no CLI subprocess that could honor sandbox flags, MCP configs,
    or tool allow/deny lists. Silently dropping these fields used to
    leave callers thinking their toggles took effect. Reject explicitly
    instead so the surprise is visible at the boundary.

    Profile-driven paths (``GET/POST /<plugin>/<profile_name>``) bypass
    this check so existing ``sf.json`` profiles keep working.
    """
    offending = [
        f for f in CLI_ONLY_FIELDS if getattr(request, f, None) != CLI_ONLY_FIELD_DEFAULTS[f]
    ]
    if not offending:
        return
    raise HTTPException(
        status_code=422,
        detail=(
            f"{plugin_name} does not accept CLI-only fields: "
            f"{', '.join(offending)}. These flags only apply to the "
            f"matching CLI tool (e.g. claude-cli) — direct API backends "
            f"have no subprocess to honor them. Remove the field(s) or "
            f"call the CLI-frontend plugin instead."
        ),
    )


def _record_ignored_fields(request: RunRequest, plugin_name: str) -> None:
    """Record which CLI-only fields were present on an OTEL span."""
    try:
        from opentelemetry import trace
    except ImportError:
        return

    span = trace.get_current_span()
    if not (span and span.is_recording()):
        return

    attr_prefix = plugin_name.replace("-", "_")
    for field_name in CLI_ONLY_FIELDS:
        value = getattr(request, field_name, None)
        if value:  # truthy — non-empty list/str or True
            span.set_attribute(f"{attr_prefix}.ignored_field.{field_name}", True)


def _record_span_success(
    result: CoreMessage,
    duration: float,
    stdout: str,
    plugin_name: str,
    span_prefix: str,
) -> None:
    """Record success-path attributes on the current OTEL span."""
    try:
        from opentelemetry import trace
    except ImportError:
        return

    span = trace.get_current_span()
    if not (span and span.is_recording()):
        return

    span.set_attribute("sf.plugin", plugin_name)
    span.set_attribute(f"{span_prefix}.exit_code", 0)
    span.set_attribute(f"{span_prefix}.duration_seconds", round(duration, 3))
    span.set_attribute(f"{span_prefix}.stdout_length", len(stdout))
    preview = stdout[:STDOUT_PREVIEW_LIMIT]
    if len(stdout) > STDOUT_PREVIEW_LIMIT:
        preview += f"\n... ({len(stdout) - STDOUT_PREVIEW_LIMIT} more chars)"
    span.set_attribute(f"{span_prefix}.stdout_preview", preview)

    if result.provider_metadata:
        for key, value in result.provider_metadata.items():
            try:
                span.set_attribute(key, _otel_attr_value(value))
            except Exception:
                pass


def _record_url4_span(q: str, result: str, plugin_name: str) -> None:
    """Record url4-endpoint attributes on the current OTEL span."""
    try:
        from opentelemetry import trace
    except ImportError:
        return

    span = trace.get_current_span()
    if not (span and span.is_recording()):
        return

    span.set_attribute("sf.plugin", plugin_name)
    span.set_attribute("url4.expression", q[:500])
    span.set_attribute("url4.result_length", len(result))
    preview = result[:PROMPT_PREVIEW_LIMIT]
    if len(result) > PROMPT_PREVIEW_LIMIT:
        preview += f"\n... ({len(result) - PROMPT_PREVIEW_LIMIT} more chars)"
    span.set_attribute("url4.response_body", preview)


def _otel_attr_value(value: Any) -> Any:
    """Coerce a value to something OTEL spans accept."""
    if isinstance(value, str | bool | int | float):
        return value
    return json.dumps(value)
