"""JWKS client for a Cloudflare Access team domain.

FEATURE: federated authentication. Cloudflare signs identity assertions RS256
with a key pair unique to the account, published at
``https://<team>.cloudflareaccess.com/cdn-cgi/access/certs``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from jwt import PyJWK

logger = logging.getLogger(__name__)

_CERTS_PATH = "/cdn-cgi/access/certs"
_FETCH_TIMEOUT_SECONDS = 5.0

#: Cloudflare rotates the signing key every 6 weeks and keeps the previous key
#: valid for 7 days, so a `kid` miss is a real (if rare) event rather than an
#: attack signal. Re-fetching on every miss would let an attacker drive unbounded
#: outbound requests with forged `kid`s, so misses are rate-limited.
_MIN_REFETCH_INTERVAL_SECONDS = 60.0


class JwksUnavailableError(RuntimeError):
    """No key material is available — neither cached nor fetchable."""


class CloudflareAccessJwks:
    """Fetches and caches Cloudflare's signing keys, keyed by ``kid``.

    INVARIANT: this class never fails *open*. Every path either returns a key
    that Cloudflare published or raises; there is no branch that skips
    verification because the network was unavailable.
    """

    def __init__(
        self,
        team_domain: str,
        *,
        http_client_factory: Any | None = None,
        min_refetch_interval_seconds: float = _MIN_REFETCH_INTERVAL_SECONDS,
    ) -> None:
        self._certs_url = f"https://{team_domain}{_CERTS_PATH}"
        self._http_client_factory = http_client_factory or self._default_client
        self._min_refetch_interval = min_refetch_interval_seconds
        self._keys: dict[str, PyJWK] = {}
        self._last_fetch_monotonic: float | None = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _default_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(_FETCH_TIMEOUT_SECONDS))

    async def get_key(self, kid: str) -> PyJWK:
        """Return the signing key for ``kid``, refreshing the cache if needed."""
        key = self._keys.get(kid)
        if key is not None:
            return key

        async with self._lock:
            # Re-check: a concurrent caller may have refreshed while we waited.
            key = self._keys.get(kid)
            if key is not None:
                return key
            if self._refetch_is_rate_limited():
                raise JwksUnavailableError(f"no signing key for kid={kid!r}")
            await self._refresh()

        key = self._keys.get(kid)
        if key is None:
            raise JwksUnavailableError(f"no signing key for kid={kid!r}")
        return key

    def _refetch_is_rate_limited(self) -> bool:
        if self._last_fetch_monotonic is None:
            return False
        elapsed = asyncio.get_running_loop().time() - self._last_fetch_monotonic
        return elapsed < self._min_refetch_interval

    async def _refresh(self) -> None:
        try:
            client = self._http_client_factory()
            async with client:
                response = await client.get(self._certs_url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # WHY stale-on-error: a Cloudflare certs blip must not 401 the entire
            # fleet. Keys already cached stay valid (they are signed by Cloudflare
            # and independently checked for exp), so serve them and retry later.
            # With a COLD cache there is nothing to serve and we still refuse —
            # degraded, never open.
            self._last_fetch_monotonic = asyncio.get_running_loop().time()
            if self._keys:
                logger.warning("cf_access jwks refresh failed; serving cached keys (%s)", exc)
                return
            raise JwksUnavailableError(f"could not fetch {self._certs_url}: {exc}") from exc

        self._last_fetch_monotonic = asyncio.get_running_loop().time()
        self._keys = self._parse(payload)

    @staticmethod
    def _parse(payload: Any) -> dict[str, PyJWK]:
        if not isinstance(payload, dict):
            raise JwksUnavailableError("certs response was not a JSON object")
        keys: dict[str, PyJWK] = {}
        for entry in payload.get("keys", []):
            if not isinstance(entry, dict):
                continue
            kid = entry.get("kid")
            if not isinstance(kid, str):
                continue
            try:
                keys[kid] = PyJWK.from_dict(entry)
            except Exception as exc:  # noqa: BLE001 - PyJWK raises assorted types
                # One malformed entry must not discard the whole (possibly
                # rotating) key set.
                logger.warning("cf_access jwks: skipping unusable key kid=%s (%s)", kid, exc)
        if not keys:
            raise JwksUnavailableError("certs response contained no usable keys")
        return keys
