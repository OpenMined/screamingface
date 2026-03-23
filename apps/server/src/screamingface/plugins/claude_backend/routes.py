"""Routes for the claude-backend plugin."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from screamingface.plugins.claude_backend.models import ClaudeRunRequest, ClaudeRunResponse
from screamingface.plugins.claude_backend.runner import build_args, run_claude, stream_claude

if TYPE_CHECKING:
    from screamingface.plugins.claude_backend.plugin import ClaudeBackendSettings

logger = logging.getLogger(__name__)


def create_router(settings: ClaudeBackendSettings) -> APIRouter:
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
            return JSONResponse(content=resp.model_dump(by_alias=True))
        finally:
            if request.output_format != "stream-json":
                _cleanup(temp_dir)

    @router.post("/claude/run", response_model=None, operation_id="claude_run")
    async def claude_run(request: ClaudeRunRequest) -> JSONResponse | StreamingResponse:
        return await _execute_claude(request)

    async def _handle_profile(
        profile_name: str,
        prompt: str,
        context: str | None = None,
    ) -> JSONResponse | StreamingResponse:
        prof = settings.profiles.get(profile_name)
        if not prof:
            raise HTTPException(status_code=404, detail=f"Unknown profile: {profile_name!r}")

        # Resolve context via url4 engine
        resolved_context = ""
        context_expr = context or prof.context
        if context_expr:
            from screamingface.plugins.url4_executor.url4 import resolve_str

            try:
                resolved_context = await resolve_str(context_expr)
            except Exception as exc:
                logger.warning("Context resolution failed: %s", exc, exc_info=True)
                raise HTTPException(status_code=502, detail=f"Context resolution failed: {exc}")

        full_prompt = f"{resolved_context}\n\n{prompt}" if resolved_context else prompt

        request = ClaudeRunRequest(
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
        return await _execute_claude(request)

    @router.get("/claude/{profile_name}", response_model=None, operation_id="claude_profile_get")
    async def claude_profile_get(
        profile_name: str,
        prompt: str,
        context: str | None = None,
    ) -> JSONResponse | StreamingResponse:
        return await _handle_profile(profile_name, prompt, context)

    @router.post("/claude/{profile_name}", response_model=None, operation_id="claude_profile_post")
    async def claude_profile_post(
        profile_name: str,
        prompt: str,
        context: str | None = None,
    ) -> JSONResponse | StreamingResponse:
        return await _handle_profile(profile_name, prompt, context)

    return router


def _cleanup(temp_dir: str | None) -> None:
    if temp_dir is None:
        return
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)
