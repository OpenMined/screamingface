"""Compatibility imports for the service-neutral Cloudflare Access contract."""

# ruff: noqa: F401 -- this module intentionally preserves private import paths.

import webbrowser

from screamingface._access.contract import (
    _REFRESH_SKEW_SECONDS,
    _access_audience,
    _access_authorization_url,
    _access_logout_url,
    _access_token,
    _AccessToken,
    _auth_error,
    _base64url_decode,
    _base64url_padded,
    _challenge_audience,
    _decrypt_transfer,
    _present_access_authorization,
    _present_access_logout,
    _raise_if_cancelled,
    _require_positive_timeout,
)

__all__: list[str] = []
