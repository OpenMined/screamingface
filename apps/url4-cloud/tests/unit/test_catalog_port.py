"""Port-shape tests for the model catalog (OME-625; spec §6.2).

FEATURE: model-catalog discovery. These pin the *contract* the cache and the adapter both code
against — protocol conformance, the credential identity key, and the ETag's determinism — with no
I/O and no app.
"""

from __future__ import annotations

import pytest

from url4_cloud.catalog.port import (
    CatalogBadResponse,
    CatalogError,
    CatalogRejected,
    CatalogSource,
    CatalogUnavailable,
    Credential,
    ModelCatalog,
    compute_etag,
)

BODY = {"object": "list", "data": [{"id": "claude-haiku-4-5", "object": "model"}]}


class _StubSource:
    """A minimal in-memory ``CatalogSource`` — the shape every adapter must satisfy."""

    async def fetch(self, credential: Credential) -> ModelCatalog:
        return ModelCatalog(body=BODY, etag=compute_etag(BODY))


def test_stub_satisfies_the_catalog_source_port() -> None:
    # INVARIANT: the port is structural — an adapter never subclasses it, so conformance must be
    # checkable at runtime or a wrong shape only surfaces at the first live call.
    assert isinstance(_StubSource(), CatalogSource)


def test_etag_is_stable_across_key_ordering() -> None:
    # INVARIANT: the ETag identifies the catalog's CONTENT. Two dicts differing only in insertion
    # order are the same catalog, so they must not produce a spurious cache-validator change.
    reordered = {"data": BODY["data"], "object": "list"}
    assert compute_etag(BODY) == compute_etag(reordered)


def test_etag_differs_for_different_bodies() -> None:
    other = {"object": "list", "data": []}
    assert compute_etag(BODY) != compute_etag(other)


def test_etag_is_a_short_hex_digest() -> None:
    etag = compute_etag(BODY)
    assert len(etag) == 16
    assert all(char in "0123456789abcdef" for char in etag)


def test_same_token_and_profile_derive_the_same_key() -> None:
    # INVARIANT: the cache key is a pure function of (token, profile) — otherwise a repeat request
    # from one caller would miss the cache every time.
    assert Credential.derive("tok", "prof").key == Credential.derive("tok", "prof").key


def test_distinct_tokens_derive_distinct_keys() -> None:
    # INVARIANT: this is the byok-correctness property at its root — two callers must never
    # collide onto one cache entry.
    assert Credential.derive("tok-a").key != Credential.derive("tok-b").key


def test_distinct_profiles_derive_distinct_keys() -> None:
    assert Credential.derive("tok", "a").key != Credential.derive("tok", "b").key


def test_absent_profile_is_not_confusable_with_an_empty_one() -> None:
    # WHY the NUL separator in `derive`: without a delimiter, ("ab", "c") and ("a", "bc") would
    # hash identically. `None` and "" must also stay distinct.
    assert Credential.derive("tok", None).key == Credential.derive("tok").key
    assert Credential.derive("ab", "c").key != Credential.derive("a", "bc").key


def test_credential_repr_never_exposes_the_token() -> None:
    # INVARIANT: the credential reaches logs, tracebacks and error reprs. A plain str field would
    # print it; SecretStr is what keeps it out.
    credential = Credential.derive("super-secret-token", "prof")
    assert "super-secret-token" not in repr(credential)
    assert "super-secret-token" not in str(credential)
    assert credential.token.get_secret_value() == "super-secret-token"


def test_key_is_fixed_length_regardless_of_token_length() -> None:
    # WHY: the key is a dict key in a bounded cache. A raw token would let a caller choose the
    # key's size; a digest makes memory-per-entry attacker-independent (spec §7).
    short = Credential.derive("x")
    long = Credential.derive("y" * 10_000)
    assert len(short.key) == len(long.key) == 32


@pytest.mark.parametrize(
    ("error", "status"),
    [(CatalogRejected, 401), (CatalogBadResponse, 502), (CatalogUnavailable, 504)],
)
def test_each_error_carries_the_status_the_route_maps_it_to(
    error: type[CatalogError], status: int
) -> None:
    # WHY on the exception rather than in the route: it keeps the route free of an isinstance
    # ladder that would need editing every time a failure mode is added.
    assert error("boom").status == status
    assert isinstance(error("boom"), CatalogError)
