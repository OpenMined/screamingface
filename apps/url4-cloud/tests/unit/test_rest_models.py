"""Behaviour tests for ``GET /v1/models`` (OME-625; spec §5, plan Batch 4).

Headless: a fake ``CatalogService`` is injected via ``create_app`` — no aigateway, no network. HTTP
is driven through an ASGI transport so the whole request runs in one event loop.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from url4_cloud.app import create_app
from url4_cloud.catalog.port import (
    CatalogBadResponse,
    CatalogError,
    CatalogRejected,
    CatalogUnavailable,
    Credential,
    ModelCatalog,
    compute_etag,
)
from url4_cloud.config import Settings
from url4_cloud_nats import InMemoryBus

pytestmark = pytest.mark.asyncio

SECRET = "models-unit-secret"
TOKEN_A = "token-a"
TOKEN_B = "token-b"
PROBLEM_MEDIA_TYPE = "application/problem+json"


class FakeCatalog:
    """A ``CatalogService`` double: echoes the credential key so leakage is directly observable."""

    def __init__(self, *, error: CatalogError | None = None, max_age: int = 247) -> None:
        self.error = error
        self.max_age = max_age
        self.seen: list[Credential] = []

    async def fetch(self, credential: Credential) -> ModelCatalog:
        self.seen.append(credential)
        if self.error is not None:
            raise self.error
        body: dict[str, object] = {
            "object": "list",
            "data": [{"id": f"model-for-{credential.key[:8]}", "object": "model"}],
        }
        return ModelCatalog(body=body, etag=compute_etag(body))

    def max_age_s(self, credential: Credential) -> int:
        return self.max_age


def build_app(catalog: FakeCatalog | None) -> FastAPI:
    return create_app(Settings(jwt_secret=SECRET), bus=InMemoryBus(), catalog=catalog)


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- happy path -----------------------------------------------------------


async def test_returns_the_catalog_body() -> None:
    async with client_for(build_app(FakeCatalog())) as client:
        response = await client.get("/v1/models", headers=auth(TOKEN_A))
    assert response.status_code == 200
    assert response.json()["object"] == "list"


async def test_the_response_carries_etag_cache_control_and_vary() -> None:
    async with client_for(build_app(FakeCatalog(max_age=247))) as client:
        response = await client.get("/v1/models", headers=auth(TOKEN_A))
    assert response.headers["ETag"].startswith('"')
    # INVARIANT: `private` — every response is tied to a caller credential, so a shared cache must
    # never store it. `max-age` mirrors the entry's REMAINING ttl so downstream expires with us.
    assert response.headers["Cache-Control"] == "private, max-age=247"
    # INVARIANT: without Vary, a shared cache could serve one caller's catalog to another — the
    # header-level counterpart of keying the cache by credential (spec §5.2).
    vary = response.headers["Vary"]
    assert "Authorization" in vary
    assert "Cf-Access-Jwt-Assertion" in vary
    assert "X-Profile" in vary


async def test_max_age_reflects_the_remaining_ttl() -> None:
    async with client_for(build_app(FakeCatalog(max_age=12))) as client:
        response = await client.get("/v1/models", headers=auth(TOKEN_A))
    assert response.headers["Cache-Control"] == "private, max-age=12"


# --- identity ------------------------------------------------------------


async def test_two_credentials_receive_different_catalogs() -> None:
    # ACCEPTANCE 4 (spec §11) at the HTTP boundary: the byok-correctness property end to end.
    catalog = FakeCatalog()
    async with client_for(build_app(catalog)) as client:
        first = await client.get("/v1/models", headers=auth(TOKEN_A))
        second = await client.get("/v1/models", headers=auth(TOKEN_B))
    assert first.json() != second.json()
    assert catalog.seen[0].key != catalog.seen[1].key


async def test_cloudflare_access_assertion_wins_over_authorization() -> None:
    # INVARIANT: identical precedence to `start_run`. If these disagreed, a caller could list one
    # identity's models and then execute a run under another.
    catalog = FakeCatalog()
    async with client_for(build_app(catalog)) as client:
        await client.get(
            "/v1/models",
            headers={**auth(TOKEN_A), "Cf-Access-Jwt-Assertion": "cf-jwt"},
        )
    assert catalog.seen[0].token.get_secret_value() == "cf-jwt"


async def test_the_profile_becomes_part_of_the_identity() -> None:
    catalog = FakeCatalog()
    async with client_for(build_app(catalog)) as client:
        await client.get("/v1/models", headers={**auth(TOKEN_A), "X-Profile": "team-a"})
    assert catalog.seen[0].profile == "team-a"


# --- authentication -------------------------------------------------------


async def test_a_request_without_a_credential_is_rejected_before_reaching_upstream() -> None:
    # ACCEPTANCE 2 (spec §11): no credential must cost aigateway nothing at all.
    catalog = FakeCatalog()
    async with client_for(build_app(catalog)) as client:
        response = await client.get("/v1/models")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert catalog.seen == [], "upstream must not be consulted without a credential"


async def test_a_non_bearer_authorization_scheme_is_not_a_credential() -> None:
    catalog = FakeCatalog()
    async with client_for(build_app(catalog)) as client:
        response = await client.get("/v1/models", headers={"Authorization": "Basic abc"})
    assert response.status_code == 401
    assert catalog.seen == []


async def test_a_refused_credential_yields_401_with_a_challenge() -> None:
    catalog = FakeCatalog(error=CatalogRejected("nope"))
    async with client_for(build_app(catalog)) as client:
        response = await client.get("/v1/models", headers=auth(TOKEN_A))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_the_401_body_does_not_describe_the_upstream_configuration() -> None:
    # INVARIANT: this endpoint does not verify the credential itself, so the caller must not learn
    # whether a token was merely unrecognised or actively refused.
    catalog = FakeCatalog(error=CatalogRejected("aud mismatch for team acme.cloudflareaccess.com"))
    async with client_for(build_app(catalog)) as client:
        response = await client.get("/v1/models", headers=auth(TOKEN_A))
    assert "cloudflareaccess" not in response.text


# --- upstream failures ----------------------------------------------------


@pytest.mark.parametrize(
    ("error", "status"),
    [(CatalogBadResponse("bad"), 502), (CatalogUnavailable("slow"), 504)],
)
async def test_upstream_failures_map_to_rfc9457_problems(error: CatalogError, status: int) -> None:
    async with client_for(build_app(FakeCatalog(error=error))) as client:
        response = await client.get("/v1/models", headers=auth(TOKEN_A))
    assert response.status_code == status
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["status"] == status


async def test_an_unconfigured_catalog_is_a_503() -> None:
    async with client_for(build_app(None)) as client:
        response = await client.get("/v1/models", headers=auth(TOKEN_A))
    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_no_failure_path_produces_a_500() -> None:
    # INVARIANT: every failure is a typed problem. A 500 here would mean an unmapped exception
    # escaped, which is exactly what the CatalogError hierarchy exists to prevent.
    for error in (CatalogBadResponse("x"), CatalogUnavailable("x"), CatalogRejected("x")):
        async with client_for(build_app(FakeCatalog(error=error))) as client:
            response = await client.get("/v1/models", headers=auth(TOKEN_A))
        assert response.status_code < 500 or response.status_code in (502, 504)


# --- conditional requests -------------------------------------------------


async def test_a_matching_if_none_match_returns_304_without_a_body() -> None:
    async with client_for(build_app(FakeCatalog())) as client:
        first = await client.get("/v1/models", headers=auth(TOKEN_A))
        etag = first.headers["ETag"]
        second = await client.get("/v1/models", headers={**auth(TOKEN_A), "If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["ETag"] == etag


async def test_a_weak_validator_still_matches() -> None:
    # WHY: RFC 9110 §13.1.2 specifies WEAK comparison for If-None-Match, so a `W/`-prefixed tag
    # from an intermediary must still match.
    async with client_for(build_app(FakeCatalog())) as client:
        first = await client.get("/v1/models", headers=auth(TOKEN_A))
        weak = f"W/{first.headers['ETag']}"
        second = await client.get("/v1/models", headers={**auth(TOKEN_A), "If-None-Match": weak})
    assert second.status_code == 304


async def test_a_wildcard_if_none_match_matches() -> None:
    async with client_for(build_app(FakeCatalog())) as client:
        response = await client.get("/v1/models", headers={**auth(TOKEN_A), "If-None-Match": "*"})
    assert response.status_code == 304


async def test_a_stale_validator_returns_the_full_body() -> None:
    async with client_for(build_app(FakeCatalog())) as client:
        response = await client.get(
            "/v1/models", headers={**auth(TOKEN_A), "If-None-Match": '"deadbeefdeadbeef"'}
        )
    assert response.status_code == 200
    assert response.json()["object"] == "list"


async def test_one_callers_validator_does_not_match_another_callers_catalog() -> None:
    # INVARIANT: the ETag is content-derived, and the two callers get different catalogs here — so
    # caller B presenting caller A's validator must NOT be told "not modified".
    async with client_for(build_app(FakeCatalog())) as client:
        first = await client.get("/v1/models", headers=auth(TOKEN_A))
        second = await client.get(
            "/v1/models", headers={**auth(TOKEN_B), "If-None-Match": first.headers["ETag"]}
        )
    assert second.status_code == 200


# --- documentation --------------------------------------------------------


async def test_the_route_is_published_in_the_openapi_document() -> None:
    app = build_app(FakeCatalog())
    schema = app.openapi()
    assert "/v1/models" in schema["paths"]
    assert "Catalog" in schema["paths"]["/v1/models"]["get"]["tags"]


async def test_the_catalog_tag_is_registered_so_scalar_renders_it() -> None:
    app = build_app(FakeCatalog())
    names = {tag["name"] for tag in app.openapi().get("tags", [])}
    assert "Catalog" in names
