"""POST /v1/chat/completions — proxies to litellm.acompletion.

Streaming and non-streaming both supported. We pass the request body
through verbatim; LiteLLM's `get_llm_provider` does the model-prefix →
provider routing. The OAuth bridge (registered as a litellm input
callback in main.py) injects per-provider headers right before dispatch.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import litellm
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    body = await request.json()

    if not isinstance(body, dict) or "model" not in body or "messages" not in body:
        raise HTTPException(status_code=400, detail="model and messages are required")

    if body.get("stream"):
        return StreamingResponse(_stream(body), media_type="text/event-stream")

    response = await litellm.acompletion(**body)
    return response.model_dump() if hasattr(response, "model_dump") else response


async def _stream(body: dict[str, Any]):
    try:
        stream = await litellm.acompletion(**body)
        async for chunk in stream:
            payload = chunk.model_dump() if hasattr(chunk, "model_dump") else chunk
            yield f"data: {json.dumps(payload)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        logger.exception("stream failed")
        err = {"error": {"message": str(exc), "type": type(exc).__name__}}
        yield f"data: {json.dumps(err)}\n\n"
