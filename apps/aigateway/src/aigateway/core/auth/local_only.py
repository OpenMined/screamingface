from __future__ import annotations

from collections.abc import Awaitable, Callable
from ipaddress import ip_address
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def _host_without_port(host_header: str | None) -> str | None:
    if host_header is None:
        return None
    value = host_header.strip()
    if not value:
        return None
    try:
        hostname = urlsplit(f"//{value}").hostname
    except ValueError:
        return None
    if not hostname:
        return None
    return hostname.rstrip(".").lower()


def _is_loopback_host(host: str | None) -> bool:
    hostname = _host_without_port(host)
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _is_loopback_client(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        return ip_address(request.client.host).is_loopback
    except ValueError:
        return False


class AuthDisabledLocalOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not _is_loopback_client(request) or not _is_loopback_host(request.headers.get("host")):
            return JSONResponse(
                {"detail": "Auth-disabled gateway is limited to loopback clients and hosts"},
                status_code=403,
            )
        return await call_next(request)
