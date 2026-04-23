"""Routes for codex-backend-api.

Mirrors claude-backend-api route shapes at the ``/codex`` prefix:

- ``POST /codex/run`` -- execute a prompt through OpenAI
- ``GET /codex?q=`` -- evaluate a url4 expression through OpenAI
- ``GET /codex/{profile_name}`` -- profile-based execution
- ``POST /codex/{profile_name}`` -- profile-based execution

Same CLI-only field dropping, same error mapping, same wire-format
request/response shapes as claude-backend-api.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from screamingface.plugins.codex_backend_api.backend import OpenAIBackend
from screamingface.plugins.codex_backend_api.models import (
    RunRequest,
    RunResponse,
)
from screamingface.plugins.llm_base.errors import (
    AuthError,
    BackendError,
    CredentialNotFoundError,
)
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
from screamingface.plugins.url4_executor.url4 import resolve_str

if TYPE_CHECKING:
    from screamingface.plugins.codex_backend_api.plugin import CodexBackendApiSettings

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "o4-mini"

# The six fields we silently ignore because they're subprocess-only.
_CLI_ONLY_FIELDS = (
    "add_dirs",
    "mcp_config",
    "permission_mode",
    "dangerously_skip_permissions",
    "no_session_persistence",
    "tools",
    "allowed_tools",
    "disallowed_tools",
)


def create_router(settings: CodexBackendApiSettings, app: Any = None) -> APIRouter:
    router = APIRouter(tags=["codex-backend-api"])

    _backend = OpenAIBackend()

    @router.get("/codex/health", response_model=None, operation_id="codex_health")
    async def codex_health() -> JSONResponse:
        """Check Codex backend health: OAuth validity and rate limits."""
        model = settings.default_model or "o4-mini"
        status = await _backend.health(model=model)
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
                    "stream-json output is not yet implemented in "
                    "codex-backend-api. Use output_format='text' or 'json'."
                ),
            )

        if request.files:
            raise HTTPException(
                status_code=400,
                detail=(
                    "The 'files' field is not supported by "
                    "codex-backend-api (no sandbox to write to). "
                    "Include file contents directly in the prompt instead."
                ),
            )

        _record_ignored_fields(request)

        timeout = request.timeout_seconds or settings.timeout_seconds
        model = request.model or settings.default_model or _DEFAULT_MODEL

        system_parts: list[str] = []
        if request.system_prompt:
            system_parts.append(request.system_prompt)
        if request.append_system_prompt:
            system_parts.append(request.append_system_prompt)
        system = "\n\n".join(system_parts) if system_parts else None

        messages = [CoreMessage(role="user", content=[TextPart(text=request.prompt)])]

        start = time.monotonic()
        try:
            result = await _backend.run(
                messages,
                model=model,
                system=system,
                max_tokens=16000,
                temperature=None,
                timeout_seconds=timeout,
            )
            duration = time.monotonic() - start
            stdout = _extract_text(result)
            parsed_result: dict | list | str | None = None
            if request.output_format == "json" and stdout.strip():
                try:
                    parsed_result = json.loads(stdout)
                except json.JSONDecodeError:
                    parsed_result = None

            resp = RunResponse(
                exit_code=0,
                stdout=stdout,
                stderr="",
                duration_seconds=round(duration, 3),
                result=parsed_result,
            )
            _record_span_success(result, duration, stdout)
            return JSONResponse(content=resp.model_dump(by_alias=True))

        except (CredentialNotFoundError, AuthError) as exc:
            duration = time.monotonic() - start
            logger.warning("codex-backend-api auth failure: %s", exc)
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
            logger.warning("codex-backend-api backend error: %s", exc)
            status = 429 if exc.status == 429 else 502
            resp = RunResponse(
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_seconds=round(duration, 3),
                result=None,
            )
            return JSONResponse(content=resp.model_dump(by_alias=True), status_code=status)

    @router.post("/codex/run", response_model=None, operation_id="codex_run")
    async def codex_run(
        request: RunRequest,
    ) -> JSONResponse | StreamingResponse:
        return await _execute(request)

    @router.get("/codex", response_model=None, operation_id="codex_url4")
    async def codex_url4(q: str) -> PlainTextResponse:
        """Evaluate a url4 expression through the OpenAI API."""
        from screamingface.plugins.codex_backend_api.interpreter import (
            CodexBackendApiInterpreter,
        )

        interpreter = CodexBackendApiInterpreter(app=app, settings=settings, backend=_backend)
        try:
            result = await interpreter.evaluate(q)
        except (CredentialNotFoundError, AuthError) as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        except BackendError as exc:
            status = 429 if exc.status == 429 else 502
            raise HTTPException(status_code=status, detail=str(exc))
        except Exception as exc:
            logger.warning("url4 evaluation failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"url4 evaluation failed: {exc}")

        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute("sf.plugin", "codex-backend-api")
                span.set_attribute("url4.expression", q[:500])
                span.set_attribute("url4.result_length", len(result))
                preview = result[:4000]
                if len(result) > 4000:
                    preview += f"\n... ({len(result) - 4000} more chars)"
                span.set_attribute("url4.response_body", preview)
        except ImportError:
            pass

        return PlainTextResponse(content=result)

    async def _handle_profile(
        profile_name: str,
        prompt: str,
        context: str | None = None,
        raw_context: str | None = None,
    ) -> JSONResponse | StreamingResponse | PlainTextResponse:
        prof = settings.profiles.get(profile_name)
        if not prof:
            raise HTTPException(status_code=404, detail=f"Unknown profile: {profile_name!r}")

        is_url4 = False
        url4_interpreter = Url4Interpreter(app=app)
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
                )

        resolved_context = ""
        if raw_context:
            resolved_context = raw_context
        elif not is_url4:
            context_expr = context or prof.context
            if context_expr:
                try:
                    resolved_context = await resolve_str(context_expr, app)
                except Exception as exc:
                    logger.warning("Context resolution failed: %s", exc, exc_info=True)
                    raise HTTPException(
                        status_code=502,
                        detail=f"Context resolution failed: {exc}",
                    )

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
        "/codex/{profile_name}",
        response_model=None,
        operation_id="codex_profile_get",
    )
    async def codex_profile_get(
        profile_name: str,
        prompt: str,
        context: str | None = None,
        raw_context: str | None = None,
    ) -> JSONResponse | StreamingResponse | PlainTextResponse:
        return await _handle_profile(profile_name, prompt, context, raw_context)

    @router.post(
        "/codex/{profile_name}",
        response_model=None,
        operation_id="codex_profile_post",
    )
    async def codex_profile_post(
        profile_name: str,
        prompt: str,
        context: str | None = None,
        raw_context: str | None = None,
    ) -> JSONResponse | StreamingResponse | PlainTextResponse:
        return await _handle_profile(profile_name, prompt, context, raw_context)

    return router


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _extract_text(msg: CoreMessage) -> str:
    """Pull concatenated text out of an assistant CoreMessage."""
    if isinstance(msg.content, str):
        return msg.content
    chunks: list[str] = []
    for part in msg.content:
        if isinstance(part, TextPart):
            chunks.append(part.text)
    return "".join(chunks)


def _record_ignored_fields(request: RunRequest) -> None:
    """Record which CLI-only fields were present so the drop is observable."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if not (span and span.is_recording()):
            return
        for field_name in _CLI_ONLY_FIELDS:
            value = getattr(request, field_name, None)
            if value:
                span.set_attribute(f"codex_backend_api.ignored_field.{field_name}", True)
    except ImportError:
        pass


def _record_span_success(result: CoreMessage, duration: float, stdout: str) -> None:
    """Record success-path attributes on the OTEL span."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if not (span and span.is_recording()):
            return
        span.set_attribute("sf.plugin", "codex-backend-api")
        span.set_attribute("codex.exit_code", 0)
        span.set_attribute("codex.duration_seconds", round(duration, 3))
        span.set_attribute("codex.stdout_length", len(stdout))
        preview = stdout[:1000]
        if len(stdout) > 1000:
            preview += f"\n... ({len(stdout) - 1000} more chars)"
        span.set_attribute("codex.stdout_preview", preview)
        if result.provider_metadata:
            for key, value in result.provider_metadata.items():
                try:
                    span.set_attribute(key, _otel_attr_value(value))
                except Exception:
                    pass
    except ImportError:
        pass


def _otel_attr_value(value: Any) -> Any:
    """Coerce a value to something OTEL spans accept as an attribute."""
    if isinstance(value, str | bool | int | float):
        return value
    return json.dumps(value)
