"""Compatibility imports for service-neutral Cloudflare Access authentication."""

# ruff: noqa: F401 -- this module intentionally preserves private import paths.

import httpx

from screamingface._access.auth import (
    _REPLAY_SAFE,
    _access_audience,
    _access_authorization_url,
    _access_logout_url,
    _access_token,
    _AccessTokenStore,
    _decrypt_transfer,
    _default_caller_auth,
    _LoginAttempt,
    _present_access_authorization,
    _present_access_logout,
    _require_positive_timeout,
    _TransportAuth,
)
from screamingface._access.auth import (
    _CloudflareAccessAuth as _ServiceCloudflareAccessAuth,
)
from screamingface.errors import AuthenticationError, EngineUnavailableError


class _CloudflareAccessAuth(_ServiceCloudflareAccessAuth):
    """Legacy Engine import with Engine-specific discovery error translation."""

    def _discovery_response(self) -> httpx.Response:
        try:
            return super()._discovery_response()
        except AuthenticationError as exc:
            if exc.code != "access_discovery_unreachable":
                raise
            raise EngineUnavailableError(
                "Could not reach the SF Engine to discover Cloudflare Access authentication",
                engine_url=self._origin,
            ) from exc


__all__: list[str] = []
