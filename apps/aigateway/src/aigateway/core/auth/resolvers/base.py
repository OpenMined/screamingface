"""The identity-resolution port.

FEATURE: federated authentication — the gateway accepts several credential
shapes (local session JWT, Cloudflare Access assertion, gateway API key)
without ``current_account`` knowing anything about any of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from fastapi import Request

from ..models import BaseAccount


@dataclass(frozen=True, slots=True)
class Rejection:
    """A resolver recognised the credential and refused it.

    WHY: distinct from ``None``. ``None`` means "not my credential, ask the next
    resolver"; a ``Rejection`` carries the *specific* reason (expired, malformed
    subject, revoked key) that the caller deserves instead of a generic 401.
    """

    detail: Any
    status_code: int = 401


#: What a resolver may answer. ``BaseAccount`` authenticates and stops the chain;
#: ``Rejection`` records a reason but lets later resolvers still try; ``None``
#: abstains.
Resolution = BaseAccount | Rejection | None


@runtime_checkable
class IdentityResolver(Protocol):
    """Resolves a request to an account, or abstains.

    INVARIANT: a resolver must abstain (``None``) for any credential it does not
    positively recognise as its own. Recognition across the registered chain is
    disjoint, which is what makes "first rejection wins" in
    :func:`~aigateway.core.auth.middleware.current_account` unambiguous.
    """

    #: Stable identifier used in logs and in chain-composition assertions.
    name: str

    async def resolve(self, request: Request) -> Resolution: ...
