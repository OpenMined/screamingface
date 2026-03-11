"""Routes for the claude-cli plugin."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from screamingface.plugins.claude_cli.models import ClaudeRunRequest, ClaudeRunResponse
from screamingface.plugins.claude_cli.runner import build_args, run_claude, stream_claude

if TYPE_CHECKING:
    from screamingface.plugins.claude_cli.plugin import ClaudeCliSettings


def create_router(settings: ClaudeCliSettings) -> APIRouter:
    router = APIRouter(tags=["claude-cli"])

    @router.post("/claude/run", response_model=None, operation_id="claude_run")
    async def claude_run(request: ClaudeRunRequest) -> JSONResponse | StreamingResponse:
        temp_dir: str | None = None
        try:
            # Write files to temp dir if provided
            if request.files:
                td = tempfile.mkdtemp(prefix="claude_cli_")
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
            except asyncio.TimeoutError:
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

    return router


def _cleanup(temp_dir: str | None) -> None:
    if temp_dir is None:
        return
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)
