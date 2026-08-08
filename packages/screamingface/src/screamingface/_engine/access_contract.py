"""Cloudflare Access URL, token, and encrypted-transfer primitives."""

from __future__ import annotations

import base64
import builtins
import json
import re
import threading
import webbrowser
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx
from nacl.exceptions import CryptoError
from nacl.public import Box, PrivateKey, PublicKey

from screamingface.errors import AuthenticationError

_MAX_TRANSFER_BYTES = 1_000_000
_REFRESH_SKEW_SECONDS = 30.0
_VALID_AUDIENCE = re.compile(r"[A-Za-z0-9_-]{16,256}\Z")


@dataclass(frozen=True, slots=True, repr=False)
class _AccessToken:
    value: str
    expires_at: float


def _access_audience(response: httpx.Response) -> str | None:
    audience = response.headers.get("cf-access-aud")
    if audience is None:
        location = response.headers.get("location")
        if location:
            values = parse_qs(urlsplit(location).query).get("kid", [])
            audience = values[0] if len(values) == 1 else None
    if audience is None:
        return None
    audience = audience.strip()
    return audience if _VALID_AUDIENCE.fullmatch(audience) else None


def _raise_if_cancelled(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise _auth_error(
            "Cloudflare Access login was cancelled",
            code="access_login_cancelled",
            permanent=False,
        )


def _access_authorization_url(engine_url: str, audience: str, public_key: str) -> str:
    parts = urlsplit(engine_url)
    transfer = {
        "token": public_key,
        "aud": audience,
        "send_org_token": "true",
        "edge_token_transfer": "true",
    }
    transfer["redirect_url"] = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(transfer), "")
    )
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            "/cdn-cgi/access/cli",
            urlencode(transfer),
            "",
        )
    )


def _access_logout_url(engine_url: str) -> str:
    parts = urlsplit(engine_url)
    return urlunsplit((parts.scheme, parts.netloc, "/cdn-cgi/access/logout", "", ""))


def _present_access_authorization(authorization_url: str) -> None:
    print(f"Complete Cloudflare Access login in your browser:\n\n{authorization_url}\n")
    if _running_in_notebook():
        return
    try:
        webbrowser.open(authorization_url, new=2)
    except (OSError, webbrowser.Error):
        # The URL is already visible for terminals without a browser integration.
        return


def _present_access_logout(logout_url: str) -> None:
    print(f"Completing Cloudflare Access logout in your browser:\n\n{logout_url}\n")
    try:
        webbrowser.open(logout_url, new=2)
    except (OSError, webbrowser.Error):
        # The URL is already visible for environments without browser integration.
        return


def _decrypt_transfer(response: httpx.Response, private_key: PrivateKey) -> str:
    if len(response.content) > _MAX_TRANSFER_BYTES:
        raise _invalid_transfer()
    service_key = response.headers.get("service-public-key")
    if not service_key:
        raise _invalid_transfer()
    try:
        peer = PublicKey(_base64url_decode(service_key))
        encrypted = base64.b64decode(response.content, validate=True)
        decrypted = Box(private_key, peer).decrypt(encrypted)
        payload = json.loads(decrypted)
    except (ValueError, TypeError, json.JSONDecodeError, CryptoError) as exc:
        raise _invalid_transfer() from exc
    token = payload.get("app_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise _invalid_transfer()
    return token


def _access_token(value: str, monotonic_now: float, wall_now: float) -> _AccessToken:
    parts = value.split(".")
    if len(parts) != 3:
        raise _invalid_token()
    try:
        payload = json.loads(_base64url_decode(parts[1]))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _invalid_token() from exc
    expires = payload.get("exp") if isinstance(payload, dict) else None
    if not isinstance(expires, int | float) or isinstance(expires, bool):
        raise _invalid_token()
    lifetime = float(expires) - wall_now
    if lifetime <= _REFRESH_SKEW_SECONDS:
        raise _invalid_token()
    return _AccessToken(value, monotonic_now + lifetime)


def _base64url_padded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(f"{value}{padding}", altchars=b"-_", validate=True)


def _invalid_transfer() -> AuthenticationError:
    return _auth_error(
        "Cloudflare Access returned an invalid encrypted login transfer",
        code="access_invalid_transfer",
    )


def _invalid_token() -> AuthenticationError:
    return _auth_error(
        "Cloudflare Access returned an invalid or expired application token",
        code="access_invalid_token",
    )


def _running_in_notebook() -> bool:
    get_ipython = getattr(builtins, "get_ipython", None)
    if not callable(get_ipython):
        return False
    try:
        shell = get_ipython()
    except Exception:  # pragma: no cover - defensive around a host-provided hook
        return False
    return shell is not None and shell.__class__.__module__.startswith("ipykernel")


def _auth_error(
    message: str,
    *,
    code: str,
    status: int | None = None,
    permanent: bool = True,
) -> AuthenticationError:
    return AuthenticationError(message, code=code, status=status, permanent=permanent)


def _require_positive_timeout(timeout: float) -> None:
    if not isinstance(timeout, int | float) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("timeout must be a positive number")


__all__: list[str] = []
