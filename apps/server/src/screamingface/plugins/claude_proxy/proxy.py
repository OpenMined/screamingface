
"""Claude API proxy router — streaming and non-streaming support."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

if TYPE_CHECKING:
    from screamingface.plugins.claude_proxy.plugin import ClaudeProxySettings

FORWARD_HEADERS = {
    "anthropic-version",
    "anthropic-beta",
    "x-api-key",
    "content-type",
    "authorization",
    "accept",
}


def create_router(settings: ClaudeProxySettings) -> APIRouter:
    upstream_url = settings.upstream_url.rstrip("/")
    api_key_env = settings.api_key_env

    router = APIRouter(tags=["claude-proxy"])

    def _build_headers(request: Request) -> dict[str, str]:
        headers = {}
        for key in FORWARD_HEADERS:
            value = request.headers.get(key)
            if value:
                headers[key] = value
        # Auth fallback: inject API key from env if client didn't provide one
        if "x-api-key" not in headers and "authorization" not in headers:
            api_key = os.environ.get(api_key_env, "")
            if api_key:
                headers["x-api-key"] = api_key
        return headers

    @router.post("/v1/messages", response_model=None, operation_id="proxy_messages")
    async def proxy_messages(request: Request) -> Response:
        body = await request.json()
        headers = _build_headers(request)
        url = f"{upstream_url}/v1/messages"

        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)

        if body.get("stream"):
            client = httpx.AsyncClient(timeout=timeout)

            async def stream_response():
                try:
                    async with client.stream("POST", url, json=body, headers=headers) as resp:
                        async for chunk in resp.aiter_bytes():
                            yield chunk
                finally:
                    await client.aclose()

            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream",
            )
        else:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=body, headers=headers)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)

    @router.get("/v1/{path:path}", response_model=None, operation_id="proxy_catchall_get")
    @router.post("/v1/{path:path}", response_model=None, operation_id="proxy_catchall_post")
    async def proxy_catchall(request: Request, path: str) -> Response:
        headers = _build_headers(request)
        url = f"{upstream_url}/v1/{path}"
        method = request.method

        timeout = httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0)

        body = await request.body()
        kwargs: dict[str, Any] = {"headers": headers}
        if body:
            kwargs["content"] = body

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, **kwargs)

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return StreamingResponse(
                iter([resp.content]),
                media_type="text/event-stream",
                status_code=resp.status_code,
            )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

    return router
