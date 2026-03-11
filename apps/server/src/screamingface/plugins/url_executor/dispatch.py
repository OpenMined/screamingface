"""Internal ASGI dispatch to backend plugins."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from httpx import ASGITransport


# Backend name → (plugin name, default action, POST path template)
BACKEND_MAP: dict[str, tuple[str, str, str]] = {
    "cli": ("claude-cli", "run", "/claude/run"),
    "proxy": ("claude-proxy", "messages", "/v1/messages"),
}


async def dispatch_request(
    app: FastAPI,
    backend: str,
    action: str,
    body: dict[str, Any],
    stream: bool = False,
) -> JSONResponse | StreamingResponse:
    """Dispatch a request to a backend plugin via internal ASGI transport.

    Returns a JSONResponse or StreamingResponse.
    Raises ValueError if the backend is unknown or plugin is not active.
    """
    if backend not in BACKEND_MAP:
        raise ValueError(f"Unknown backend: {backend!r}")

    plugin_name, _, path = BACKEND_MAP[backend]

    # Check that the target plugin is active
    active = app.state.plugins.active_plugins
    if plugin_name not in active:
        raise ValueError(f"Backend plugin {plugin_name!r} is not active")

    if stream and backend == "cli":
        body["of"] = "stream-json"

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal") as client:
        if stream:
            req = client.build_request("POST", path, json=body)
            resp = await client.send(req, stream=True)

            async def stream_response():
                try:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
                finally:
                    await resp.aclose()

            return StreamingResponse(
                stream_response(),
                media_type="text/event-stream",
            )
        else:
            resp = await client.post(path, json=body)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
