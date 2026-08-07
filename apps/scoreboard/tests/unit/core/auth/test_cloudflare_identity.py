"""Scoreboard resolves the submitter from the identity header the mesh gateway injects.

The trust model is the deployment's, not this module's: Cloudflare Access authenticates at the
edge and Envoy re-verifies that assertion before injecting `X-User-Email`, so in
`cloudflare_headers` mode this service reads the header directly. Mirrors
apps/aigateway/tests/unit/auth/test_cloudflare_identity.py, simplified for a plain-string
submitter identity rather than an Account lookup.
"""

from __future__ import annotations

from starlette.datastructures import Headers

from scoreboard.core.auth.cloudflare_identity import identity_from_headers

EMAIL = "someone@openmined.org"


def test_a_caller_is_identified_by_their_verified_email() -> None:
    assert identity_from_headers({"X-User-Email": EMAIL}) == EMAIL


def test_no_identity_header_is_no_identity() -> None:
    """`None` means "nothing presented", which the route turns into a 401 — never anonymous."""
    assert identity_from_headers({}) is None


def test_a_blank_header_is_treated_as_absent() -> None:
    """Blank carries no identity; treating it as one would let a reader think a caller was known."""
    assert identity_from_headers({"X-User-Email": "   "}) is None


def test_the_header_is_read_case_insensitively() -> None:
    """Header names are case-insensitive on the wire, whatever casing the mesh emits.

    Exercised through Starlette's `Headers`, not a plain dict: the case-insensitivity is the
    mapping's, which is exactly the contract `identity_from_headers` documents for its argument.
    """
    assert identity_from_headers(Headers({"x-user-email": EMAIL})) == EMAIL


def test_surrounding_whitespace_is_stripped() -> None:
    assert identity_from_headers({"X-User-Email": f"  {EMAIL}  "}) == EMAIL
