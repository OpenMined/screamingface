from __future__ import annotations

import base64
import binascii
import hmac
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .config import Settings

PUBLIC_ARTIFACTS = ("livetruth-latest.jsonl", "livetruth-masking.dataset.jsonl")
FORBIDDEN_ARTIFACTS = (
    "livetruth-latest.eval.jsonl",
    "livetruth-latest.eval.jsonl.txt",
    "livetruth-latest.answer-key.jsonl",
)
TEXT_MEDIA_TYPE = "text/plain; charset=utf-8"


class BasicAuthApp:
    def __init__(self, app: ASGIApp, *, username: str, password: str) -> None:
        self._app = app
        self._username = username
        self._password = password

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._authorized(scope):
            await self._app(scope, receive, send)
            return

        response = PlainTextResponse(
            "Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="scoreboard portal"'},
        )
        await response(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        header = Headers(scope=scope).get("authorization")
        if not header or not header.startswith("Basic "):
            return False

        try:
            decoded = base64.b64decode(header[6:], validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            decoded = ""

        username, sep, password = decoded.partition(":")
        return (
            sep == ":"
            and hmac.compare_digest(username, self._username)
            and hmac.compare_digest(password, self._password)
        )


def register_portal(app: FastAPI, settings: Settings) -> None:
    portal_dir = _resolve_portal_dir(settings)
    artifacts_dir = _resolve_artifacts_dir(settings)
    _validate_portal_auth(settings)
    _validate_public_artifacts(artifacts_dir)

    _register_forbidden_artifacts(app)
    _register_public_artifacts(app, artifacts_dir)

    static_app: ASGIApp = StaticFiles(directory=portal_dir, html=True)
    if settings.portal_auth_enabled:
        assert settings.portal_auth_password is not None
        static_app = BasicAuthApp(
            static_app,
            username=settings.portal_auth_username,
            password=settings.portal_auth_password,
        )
    app.mount("/", static_app, name="portal")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_portal_dir(settings: Settings) -> Path:
    portal_dir = settings.portal_dir or _repo_root() / "web" / "portal"
    if not portal_dir.is_dir():
        raise RuntimeError(f"portal directory not found: {portal_dir}")
    return portal_dir


def _resolve_artifacts_dir(settings: Settings) -> Path:
    artifacts_dir = (
        settings.portal_artifacts_dir or _repo_root() / "output_artifacts" / "eval_results"
    )
    if not artifacts_dir.is_dir():
        raise RuntimeError(f"portal artifacts directory not found: {artifacts_dir}")
    return artifacts_dir


def _validate_portal_auth(settings: Settings) -> None:
    if settings.portal_auth_enabled and not settings.portal_auth_password:
        raise ValueError("SCOREBOARD_PORTAL_AUTH_PASSWORD is required when portal auth is enabled")


def _validate_public_artifacts(artifacts_dir: Path) -> None:
    for name in PUBLIC_ARTIFACTS:
        path = artifacts_dir / name
        if not path.is_file():
            raise RuntimeError(f"portal artifact not found: {path}")


def _register_public_artifacts(app: FastAPI, artifacts_dir: Path) -> None:
    for name in PUBLIC_ARTIFACTS:
        app.get(f"/{name}", include_in_schema=False)(_artifact_response(artifacts_dir / name))


def _register_forbidden_artifacts(app: FastAPI) -> None:
    for name in FORBIDDEN_ARTIFACTS:
        app.get(f"/{name}", include_in_schema=False)(_not_found)


def _artifact_response(path: Path) -> Callable[[], FileResponse]:
    def endpoint() -> FileResponse:
        return FileResponse(path, media_type=TEXT_MEDIA_TYPE)

    return endpoint


def _not_found() -> None:
    raise HTTPException(status_code=404)
