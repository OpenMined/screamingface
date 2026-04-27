"""In-process mock of the subset of httpbin.org we use in e2e tests.

httpbin.org goes flaky in CI roughly once a week (transient 502 / empty
body / DNS hiccups) and there's no retry budget that's both polite and
reliable. This mock implements only the routes we touch:

- ``GET  /robots.txt``      → plain-text body (deterministic)
- ``GET  /user-agent``      → JSON with the requesting User-Agent header
- ``ANY  /anything``        → JSON echo of method/headers/json/data/url

Run with :class:`LocalHttpbin` as a context manager; it spawns a
``uvicorn`` server in a background thread on a free localhost port.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/robots.txt")
    async def robots() -> PlainTextResponse:
        # Same content httpbin.org serves; tests only assert it's
        # non-empty and contains "User-agent" or "Disallow".
        return PlainTextResponse("User-agent: *\nDisallow: /deny\n")

    @app.get("/user-agent")
    async def user_agent(request: Request) -> JSONResponse:
        return JSONResponse({"user-agent": request.headers.get("user-agent", "")})

    @app.api_route(
        "/anything",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    @app.api_route(
        "/anything/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    async def anything(request: Request) -> JSONResponse:
        body_bytes = await request.body()
        json_body: object | None = None
        if body_bytes:
            try:
                import json as _json

                json_body = _json.loads(body_bytes)
            except ValueError:
                json_body = None
        return JSONResponse(
            {
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "json": json_body,
                "data": body_bytes.decode("utf-8", errors="replace") if not json_body else "",
                "args": dict(request.query_params),
                "origin": request.client.host if request.client else "",
            }
        )

    return app


class LocalHttpbin:
    """Thread-managed in-process httpbin mock.

    Usage::

        with LocalHttpbin() as hb:
            url = hb.base_url  # "http://127.0.0.1:<port>"
    """

    def __init__(self, port: int | None = None) -> None:
        self._port = port or _find_free_port()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def start(self, timeout: float = 5.0) -> None:
        config = uvicorn.Config(
            _build_app(),
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                return
            time.sleep(0.05)
        raise RuntimeError(f"LocalHttpbin failed to start on port {self._port}")

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def __enter__(self) -> LocalHttpbin:
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()


@contextmanager
def local_httpbin() -> Iterator[LocalHttpbin]:
    hb = LocalHttpbin()
    hb.start()
    try:
        yield hb
    finally:
        hb.stop()
