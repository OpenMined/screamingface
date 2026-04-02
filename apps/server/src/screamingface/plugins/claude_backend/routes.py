"""Routes for the claude-backend plugin."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from screamingface.plugins.claude_backend.models import ClaudeRunRequest, ClaudeRunResponse
from screamingface.plugins.claude_backend.runner import build_args, run_claude, stream_claude
from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
from screamingface.plugins.url4_executor.url4 import resolve_str

if TYPE_CHECKING:
    from screamingface.plugins.claude_backend.plugin import ClaudeBackendSettings

logger = logging.getLogger(__name__)


def create_router(settings: ClaudeBackendSettings, app: Any = None) -> APIRouter:
    router = APIRouter(tags=["claude-backend"])

    async def _execute_claude(
        request: ClaudeRunRequest,
    ) -> JSONResponse | StreamingResponse:
        temp_dir: str | None = None
        try:
            # Write files to temp dir if provided
            if request.files:
                td = tempfile.mkdtemp(prefix="claude_backend_")
                temp_dir = td
                for f in request.files:
                    if ".." in f.filename:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Path traversal not allowed in filename: {f.filename}",
                        )
                    dest = Path(td) / f.filename
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(f.content)

            timeout = request.timeout_seconds or settings.timeout_seconds
            args = build_args(request, settings, temp_dir)

            # Streaming mode
            if request.output_format == "stream-json":

                async def sse_stream():
                    try:
                        async for line in stream_claude(args, request.prompt, timeout):
                            yield f"data: {line.rstrip()}\n\n"
                    finally:
                        _cleanup(temp_dir)

                return StreamingResponse(sse_stream(), media_type="text/event-stream")

            # Non-streaming mode
            try:
                exit_code, stdout, stderr, duration = await run_claude(
                    args, request.prompt, timeout
                )
            except TimeoutError:
                raise HTTPException(status_code=504, detail="Claude CLI timed out")

            result = None
            if request.output_format == "json" and exit_code == 0 and stdout.strip():
                try:
                    result = json.loads(stdout)
                except json.JSONDecodeError:
                    result = None

            resp = ClaudeRunResponse(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=round(duration, 3),
                result=result,
            )

            # Record response on OTEL span
            try:
                from opentelemetry import trace

                span = trace.get_current_span()
                if span and span.is_recording():
                    span.set_attribute("sf.plugin", "claude-backend")
                    span.set_attribute("claude.exit_code", exit_code)
                    span.set_attribute("claude.duration_seconds", round(duration, 3))
                    span.set_attribute("claude.stdout_length", len(stdout))
                    preview = stdout[:1000]
                    if len(stdout) > 1000:
                        preview += f"\n... ({len(stdout) - 1000} more chars)"
                    span.set_attribute("claude.stdout_preview", preview)
                    if stderr:
                        span.set_attribute("claude.stderr_preview", stderr[:500])
            except ImportError:
                pass

            return JSONResponse(content=resp.model_dump(by_alias=True))
        finally:
            if request.output_format != "stream-json":
                _cleanup(temp_dir)

    @router.post("/claude/run", response_model=None, operation_id="claude_run")
    async def claude_run(request: ClaudeRunRequest) -> JSONResponse | StreamingResponse:
        return await _execute_claude(request)

    @router.get("/claude", response_model=None, operation_id="claude_url4")
    async def claude_url4(q: str) -> PlainTextResponse:
        """Evaluate a url4 expression through the Claude CLI."""
        from screamingface.plugins.claude_backend.interpreter import ClaudeInterpreter

        interpreter = ClaudeInterpreter(app=app, settings=settings)
        try:
            result = await interpreter.evaluate(q)
        except Exception as exc:
            logger.warning("Claude url4 evaluation failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=502, detail=f"Claude url4 evaluation failed: {exc}")
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

        # Check if prompt is url4 syntax — if so, resolve via base interpreter
        is_url4 = False
        interpreter = Url4Interpreter(app=app)
        stripped = prompt.strip()
        if stripped.startswith("(") and "!" in stripped:
            try:
                prompt = await interpreter.evaluate(stripped)
                is_url4 = True
            except Exception as exc:
                logger.warning("url4 prompt resolution failed: %s", exc, exc_info=True)
                raise HTTPException(status_code=502, detail=f"url4 prompt resolution failed: {exc}")

        # raw_context is already resolved — use directly, skip url4
        # context is a url4 expression — resolve via url4 engine
        resolved_context = ""
        if raw_context:
            resolved_context = raw_context
        elif not is_url4:
            # Skip context resolution when prompt was url4 (it already includes context)
            context_expr = context or prof.context
            if context_expr:
                try:
                    resolved_context = await resolve_str(context_expr, app)
                except Exception as exc:
                    logger.warning("Context resolution failed: %s", exc, exc_info=True)
                    raise HTTPException(status_code=502, detail=f"Context resolution failed: {exc}")

        full_prompt = f"{resolved_context}\n\n{prompt}" if resolved_context else prompt

        run_request = ClaudeRunRequest(
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
        result = await _execute_claude(run_request)

        # url4 mode — return just stdout as plain text
        if is_url4 and isinstance(result, JSONResponse):
            body = json.loads(bytes(result.body).decode())
            stdout = body.get("so") or body.get("stdout") or ""
            return PlainTextResponse(content=stdout)

        return result

    @router.get("/claude/{profile_name}", response_model=None, operation_id="claude_profile_get")
    async def claude_profile_get(
        profile_name: str,
        prompt: str,
        context: str | None = None,
        raw_context: str | None = None,
    ) -> JSONResponse | StreamingResponse | PlainTextResponse:
        return await _handle_profile(profile_name, prompt, context, raw_context)

    @router.post("/claude/{profile_name}", response_model=None, operation_id="claude_profile_post")
    async def claude_profile_post(
        profile_name: str,
        prompt: str,
        context: str | None = None,
        raw_context: str | None = None,
    ) -> JSONResponse | StreamingResponse | PlainTextResponse:
        return await _handle_profile(profile_name, prompt, context, raw_context)

    return router


def _cleanup(temp_dir: str | None) -> None:
    if temp_dir is None:
        return
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)
