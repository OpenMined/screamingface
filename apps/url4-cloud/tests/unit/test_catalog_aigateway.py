from __future__ import annotations

import logging

import httpx
import pytest

from url4_cloud.catalog.aigateway import AigatewayCatalogSource
from url4_cloud.catalog.port import (
    CatalogBadResponse,
    CatalogRejected,
    CatalogSource,
    CatalogUnavailable,
    Credential,
    compute_etag,
)

pytestmark = pytest.mark.asyncio

IDENTITY = {"X-User-Email": "alice@example.com"}
CATALOG = {
    "object": "list",
    "data": [
        {"id": "claude-haiku-4-5", "object": "model", "owned_by": "anthropic"},
        {"id": "openrouter/llama-3.3-70b", "object": "model", "owned_by": "openrouter"},
    ],
}


def source_for(handler: object) -> tuple[AigatewayCatalogSource, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def capture(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)  # type: ignore[operator]

    client = httpx.AsyncClient(
        base_url="http://aigateway.test", transport=httpx.MockTransport(capture)
    )
    return AigatewayCatalogSource(client), seen


def ok(payload: object, status: int = 200) -> object:
    return lambda request: httpx.Response(status, json=payload)


async def test_adapter_satisfies_the_catalog_source_port() -> None:
    adapter, _ = source_for(ok(CATALOG))
    assert isinstance(adapter, CatalogSource)


async def test_returns_the_upstream_body_verbatim_with_its_etag() -> None:
    adapter, _ = source_for(ok(CATALOG))
    catalog = await adapter.fetch(Credential.derive(None, IDENTITY))
    assert catalog.body == CATALOG
    assert catalog.etag == compute_etag(CATALOG)


async def test_unknown_upstream_fields_are_preserved() -> None:
    payload = {"object": "list", "data": [{"id": "m", "brand_new_field": 42}], "extra": True}
    adapter, _ = source_for(ok(payload))
    catalog = await adapter.fetch(Credential.derive(None, IDENTITY))
    assert catalog.body == payload


async def test_an_empty_catalog_is_valid() -> None:
    adapter, _ = source_for(ok({"object": "list", "data": []}))
    catalog = await adapter.fetch(Credential.derive(None, IDENTITY))
    assert catalog.body["data"] == []


async def test_the_identity_is_forwarded_and_no_bearer_token_is_invented() -> None:
    adapter, seen = source_for(ok(CATALOG))
    await adapter.fetch(Credential.derive(None, IDENTITY))
    assert seen[0].headers["X-User-Email"] == "alice@example.com"
    assert "authorization" not in seen[0].headers
    assert seen[0].url.path == "/v1/models"


# A local deployment runs aigateway with auth disabled, so a caller has no identity to send and
# the request must still go out rather than being refused or sent with a fabricated header.
async def test_an_anonymous_caller_sends_no_identity_and_no_authorization() -> None:
    adapter, seen = source_for(ok(CATALOG))
    await adapter.fetch(Credential.derive())
    assert "x-user-email" not in seen[0].headers
    assert "authorization" not in seen[0].headers


async def test_the_profile_is_forwarded_when_set() -> None:
    adapter, seen = source_for(ok(CATALOG))
    await adapter.fetch(Credential.derive("team-a", IDENTITY))
    assert seen[0].headers["X-Profile"] == "team-a"


async def test_no_profile_header_is_sent_when_there_is_no_profile() -> None:
    adapter, seen = source_for(ok(CATALOG))
    await adapter.fetch(Credential.derive(None, IDENTITY))
    assert "x-profile" not in seen[0].headers


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_credential_raises_catalog_rejected(status: int) -> None:
    adapter, _ = source_for(ok({"detail": "nope"}, status=status))
    with pytest.raises(CatalogRejected):
        await adapter.fetch(Credential.derive(None, IDENTITY))


async def test_a_non_json_body_is_named_rather_than_escaping_as_a_decode_error() -> None:
    adapter, _ = source_for(lambda request: httpx.Response(200, text="<html>hi</html>"))
    with pytest.raises(CatalogBadResponse):
        await adapter.fetch(Credential.derive(None, IDENTITY))


@pytest.mark.parametrize(
    "payload",
    [
        {"object": "list"},
        {"data": [{"id": "m"}]},
        {"object": "not-a-list", "data": []},
        {"object": "list", "data": "nope"},
        {"object": "list", "data": [{"no_id": 1}]},
        {"object": "list", "data": [{"id": 42}]},
        {"object": "list", "data": ["bare-string"]},
        [],
    ],
)
async def test_a_malformed_catalog_shape_raises_catalog_bad_response(payload: object) -> None:
    adapter, _ = source_for(ok(payload))
    with pytest.raises(CatalogBadResponse):
        await adapter.fetch(Credential.derive(None, IDENTITY))


async def test_a_server_error_raises_catalog_bad_response() -> None:
    adapter, _ = source_for(ok({"detail": "boom"}, status=500))
    with pytest.raises(CatalogBadResponse):
        await adapter.fetch(Credential.derive(None, IDENTITY))


async def test_a_timeout_raises_catalog_unavailable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    adapter, _ = source_for(timeout)
    with pytest.raises(CatalogUnavailable):
        await adapter.fetch(Credential.derive(None, IDENTITY))


async def test_a_connect_failure_raises_catalog_bad_response() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter, _ = source_for(refused)
    with pytest.raises(CatalogBadResponse):
        await adapter.fetch(Credential.derive(None, IDENTITY))


async def test_the_callers_email_is_never_logged_on_the_happy_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter, _ = source_for(ok(CATALOG))
    with caplog.at_level(logging.DEBUG):
        await adapter.fetch(Credential.derive(None, IDENTITY))
    assert IDENTITY["X-User-Email"] not in caplog.text


@pytest.mark.parametrize(
    "handler",
    [
        ok({"detail": "nope"}, status=401),
        ok({"object": "list"}),
        lambda request: httpx.Response(200, text="<html>"),
    ],
)
async def test_the_callers_email_is_never_logged_on_a_failure_path(
    handler: object, caplog: pytest.LogCaptureFixture
) -> None:
    adapter, _ = source_for(handler)
    with caplog.at_level(logging.DEBUG), pytest.raises(Exception) as excinfo:
        await adapter.fetch(Credential.derive(None, IDENTITY))
    assert IDENTITY["X-User-Email"] not in caplog.text
    assert IDENTITY["X-User-Email"] not in str(excinfo.value)
