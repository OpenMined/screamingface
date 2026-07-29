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
    async def fetch(self, credential: Credential) -> ModelCatalog:
        return ModelCatalog(body=BODY, etag=compute_etag(BODY))


def test_stub_satisfies_the_catalog_source_port() -> None:
    assert isinstance(_StubSource(), CatalogSource)


def test_etag_is_stable_across_key_ordering() -> None:
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
    assert Credential.derive("tok", "prof").key == Credential.derive("tok", "prof").key


def test_distinct_tokens_derive_distinct_keys() -> None:
    assert Credential.derive("tok-a").key != Credential.derive("tok-b").key


def test_distinct_profiles_derive_distinct_keys() -> None:
    assert Credential.derive("tok", "a").key != Credential.derive("tok", "b").key


def test_absent_profile_is_not_confusable_with_an_empty_one() -> None:
    assert Credential.derive("tok", None).key == Credential.derive("tok").key
    assert Credential.derive("ab", "c").key != Credential.derive("a", "bc").key


def test_credential_repr_never_exposes_the_token() -> None:
    credential = Credential.derive("super-secret-token", "prof")
    assert "super-secret-token" not in repr(credential)
    assert "super-secret-token" not in str(credential)
    assert credential.token.get_secret_value() == "super-secret-token"


def test_key_is_fixed_length_regardless_of_token_length() -> None:
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
    assert error("boom").status == status
    assert isinstance(error("boom"), CatalogError)
