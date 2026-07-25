"""Identity resolvers — the adapters behind ``current_account``.

Core defines the port (:mod:`.base`); adapters live beside it and are wired into
``app.state.identity_resolvers`` by ``main.py``. ``current_account`` imports only
the port, never an adapter.
"""

from __future__ import annotations

from .base import IdentityResolver, Rejection, Resolution
from .local_jwt import LocalJwtResolver

__all__ = [
    "IdentityResolver",
    "LocalJwtResolver",
    "Rejection",
    "Resolution",
    "build_default_resolvers",
]


def build_default_resolvers() -> list[IdentityResolver]:
    """Return the chain every deployment gets.

    AIDEV-NOTE: order is the contract. Later units append the Cloudflare Access
    resolver (OME-591) and the API-key resolver (OME-592) *after* this one; the
    local session token stays first so a gateway with no federation configured
    behaves exactly as it always has.
    """
    return [LocalJwtResolver()]
