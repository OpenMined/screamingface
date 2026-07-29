"""The model-catalog port — the contract the cache and the aigateway adapter share (spec §6.2).

FEATURE: model-catalog discovery. ``GET /v1/models`` on url4-cloud answers "which models can I
address?" by forwarding the caller's own aigateway credential upstream and caching the result per
credential.

STORY: as a client composing a url4 expression, I ask url4-cloud which model paths exist before I
reference one, instead of guessing and failing at run time.

Defines the domain value types (``Credential``, ``ModelCatalog``), the RFC 9457-style error
hierarchy the aigateway adapter and the REST layer share, and the ``CatalogSource`` Protocol — the
port that concrete catalog adapters (e.g. ``AigatewayCatalogSource`` in ``catalog/aigateway.py``)
implement.

AIDEV-NOTE: this module is a dependency-free leaf on purpose — no httpx, no FastAPI. Both the
adapter (which speaks HTTP) and the cache (which speaks to nothing) import it, and the route maps
its error types onto RFC 9457 problems. Keep transport concerns out of here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import SecretStr

# WHY 32 hex (128 bits) for the cache key: it must be collision-free across concurrent callers,
# since a collision would serve one caller another's catalog. 16 hex for the ETag is fine by
# contrast — an ETag collision only costs a spurious 304, never a cross-caller leak.
_KEY_LENGTH = 32
_ETAG_LENGTH = 16

# WHY a NUL delimiter: without one, ("ab", "c") and ("a", "bc") would hash to the same key. NUL
# cannot appear in an HTTP header value, so it can never occur inside either component.
_KEY_SEPARATOR = "\x00"


@dataclass(frozen=True, slots=True)
class Credential:
    """A caller-supplied aigateway identity, plus the cache key derived from it.

    INVARIANT: ``token`` is a :class:`~pydantic.SecretStr`, never a bare ``str`` — this object
    reaches log records, tracebacks and exception reprs, and a bare str would print the secret.
    Reach for the raw value only at the moment of building the upstream header.
    """

    token: SecretStr
    profile: str | None
    key: str

    @classmethod
    def derive(cls, token: str, profile: str | None = None) -> Credential:
        """Build a credential and its cache key from a raw token.

        INVARIANT: the key is a *digest*, never the token itself. Two reasons — the raw token must
        never sit in a dict key where a heap dump or debugger would surface it, and a digest is
        fixed-length, so per-entry memory cannot be chosen by whoever sends the token (spec §7).
        """
        # WHY: separate token and profile with a NUL byte before hashing so distinct
        # (token, profile) pairs can't collide by concatenating to the same string.
        material = f"{token}{_KEY_SEPARATOR}{profile or ''}".encode()
        return cls(
            token=SecretStr(token),
            profile=profile,
            key=hashlib.sha256(material).hexdigest()[:_KEY_LENGTH],
        )


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """One fetched catalog: aigateway's response body verbatim, plus its derived ETag.

    WHY verbatim: url4-cloud proxies, it does not reshape. Passing the body through unchanged keeps
    the response OpenAI-tool-compatible and means a new upstream field needs no change here.
    """

    body: dict[str, object]
    etag: str


def compute_etag(body: dict[str, object]) -> str:
    """A strong ETag over the catalog's content (spec §5.2).

    INVARIANT: determined by content, not by dict ordering — ``sort_keys`` (and compact
    separators) is what makes a re-fetch of an unchanged catalog produce the same validator, so a
    cache refresh does not needlessly invalidate every client's copy.
    """
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:_ETAG_LENGTH]


class CatalogError(Exception):
    """Base for catalog failures, carrying the HTTP mapping the route should apply.

    WHY the status lives on the exception: the route then needs no ``isinstance`` ladder, so adding
    a failure mode does not mean editing the route. Subclasses override the three attributes.
    """

    status = 502
    title = "Bad Gateway"
    detail = "the model catalog could not be retrieved"


class CatalogRejected(CatalogError):
    """Upstream refused the credential.

    INVARIANT: the detail stays generic. This endpoint does not verify the credential itself, so a
    caller learning that a token was *recognised but refused* would be an oracle over this
    deployment's aigateway configuration.
    """

    status = 401
    title = "Unauthorized"
    detail = "aigateway rejected the supplied credential"


class CatalogBadResponse(CatalogError):
    """The upstream response was malformed, non-JSON, or otherwise unusable."""

    status = 502
    title = "Bad Gateway"
    detail = "aigateway returned an unusable model catalog"


class CatalogUnavailable(CatalogError):
    """The upstream request timed out."""

    status = 504
    title = "Gateway Timeout"
    detail = "aigateway did not respond in time"


@runtime_checkable
class CatalogSource(Protocol):
    """Anything that can produce a catalog for a credential.

    Implemented by the aigateway adapter (``AigatewayCatalogSource``) and — as a decorator over
    another source — by :class:`~url4_cloud.catalog.cache.CachedCatalog`, which is what lets the
    route depend on one type whether or not caching is in play.
    """

    async def fetch(self, credential: Credential) -> ModelCatalog: ...


__all__ = [
    "CatalogBadResponse",
    "CatalogError",
    "CatalogRejected",
    "CatalogSource",
    "CatalogUnavailable",
    "Credential",
    "ModelCatalog",
    "compute_etag",
]
