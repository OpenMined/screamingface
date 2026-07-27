"""Behaviour tests for the aigateway catalog adapter (OME-625; spec §6.1, plan Batch 3).

Headless: every request is served by an ``httpx.MockTransport``, so nothing here touches the
network or a live aigateway.
"""

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

TOKEN = "aigw-secret-token"
CATALOG = {
    "object": "list",
    "data": [
        {"id": "claude-haiku-4-5", "object": "model", "owned_by": "anthropic"},
        {"id": "openrouter/llama-3.3-70b", "object": "model", "owned_by": "openrouter"},
    ],
}


def source_for(handler: object) -> tuple[AigatewayCatalogSource, list[httpx.Request]]:
    """An adapter wired to a mock transport, plus the list of requests it saw."""
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


# --- conformance ----------------------------------------------------------


async def test_adapter_satisfies_the_catalog_source_port() -> None:
    adapter, _ = source_for(ok(CATALOG))
    assert isinstance(adapter, CatalogSource)


# --- happy path -----------------------------------------------------------


async def test_returns_the_upstream_body_verbatim_with_its_etag() -> None:
    # INVARIANT: verbatim. url4-cloud proxies rather than reshapes, so an added upstream field
    # must survive without a change here (spec §5.2).
    adapter, _ = source_for(ok(CATALOG))
    catalog = await adapter.fetch(Credential.derive(TOKEN))
    assert catalog.body == CATALOG
    assert catalog.etag == compute_etag(CATALOG)


async def test_unknown_upstream_fields_are_preserved() -> None:
    payload = {"object": "list", "data": [{"id": "m", "brand_new_field": 42}], "extra": True}
    adapter, _ = source_for(ok(payload))
    catalog = await adapter.fetch(Credential.derive(TOKEN))
    assert catalog.body == payload


async def test_an_empty_catalog_is_valid() -> None:
    # WHY: a gateway with no provider plugins loaded is a legitimate (if useless) deployment —
    # it is not a malformed response, and must not be turned into a 502.
    adapter, _ = source_for(ok({"object": "list", "data": []}))
    catalog = await adapter.fetch(Credential.derive(TOKEN))
    assert catalog.body["data"] == []


# --- credential forwarding ------------------------------------------------


async def test_the_credential_is_forwarded_as_a_bearer_token() -> None:
    adapter, seen = source_for(ok(CATALOG))
    await adapter.fetch(Credential.derive(TOKEN))
    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert seen[0].url.path == "/v1/models"


async def test_the_profile_is_forwarded_when_set() -> None:
    adapter, seen = source_for(ok(CATALOG))
    await adapter.fetch(Credential.derive(TOKEN, "team-a"))
    assert seen[0].headers["X-Profile"] == "team-a"


async def test_no_profile_header_is_sent_when_there_is_no_profile() -> None:
    # WHY assert absence: sending `X-Profile: ` (empty) is not the same request as omitting it,
    # and aigateway is entitled to treat the two differently.
    adapter, seen = source_for(ok(CATALOG))
    await adapter.fetch(Credential.derive(TOKEN))
    assert "x-profile" not in seen[0].headers


# --- rejection ------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
async def test_a_refused_credential_raises_catalog_rejected(status: int) -> None:
    adapter, _ = source_for(ok({"detail": "nope"}, status=status))
    with pytest.raises(CatalogRejected):
        await adapter.fetch(Credential.derive(TOKEN))


# --- bad upstream responses -----------------------------------------------


async def test_a_non_json_body_is_named_rather_than_escaping_as_a_decode_error() -> None:
    # WHY: a transparent proxy can answer 200 with an HTML interstitial. The Runner's own
    # `_list_models` learned this the hard way; a raw JSONDecodeError escaping here would be an
    # unhandled 500 instead of a 502.
    adapter, _ = source_for(lambda request: httpx.Response(200, text="<html>hi</html>"))
    with pytest.raises(CatalogBadResponse):
        await adapter.fetch(Credential.derive(TOKEN))


@pytest.mark.parametrize(
    "payload",
    [
        {"object": "list"},  # no data
        {"data": [{"id": "m"}]},  # no object
        {"object": "not-a-list", "data": []},  # wrong object
        {"object": "list", "data": "nope"},  # data not a list
        {"object": "list", "data": [{"no_id": 1}]},  # entry without id
        {"object": "list", "data": [{"id": 42}]},  # id not a string
        {"object": "list", "data": ["bare-string"]},  # entry not an object
        [],  # body not an object at all
    ],
)
async def test_a_malformed_catalog_shape_raises_catalog_bad_response(payload: object) -> None:
    adapter, _ = source_for(ok(payload))
    with pytest.raises(CatalogBadResponse):
        await adapter.fetch(Credential.derive(TOKEN))


async def test_a_server_error_raises_catalog_bad_response() -> None:
    adapter, _ = source_for(ok({"detail": "boom"}, status=500))
    with pytest.raises(CatalogBadResponse):
        await adapter.fetch(Credential.derive(TOKEN))


# --- transport failures ---------------------------------------------------


async def test_a_timeout_raises_catalog_unavailable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    adapter, _ = source_for(timeout)
    with pytest.raises(CatalogUnavailable):
        await adapter.fetch(Credential.derive(TOKEN))


async def test_a_connect_failure_raises_catalog_bad_response() -> None:
    # WHY 502 and not 504: RFC 9110 reserves 504 for "no timely response". A refused connection
    # got no response at all, which is a bad gateway.
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    adapter, _ = source_for(refused)
    with pytest.raises(CatalogBadResponse):
        await adapter.fetch(Credential.derive(TOKEN))


# --- secret hygiene -------------------------------------------------------


async def test_the_token_is_never_logged_on_the_happy_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter, _ = source_for(ok(CATALOG))
    with caplog.at_level(logging.DEBUG):
        await adapter.fetch(Credential.derive(TOKEN))
    assert TOKEN not in caplog.text


@pytest.mark.parametrize(
    "handler",
    [
        ok({"detail": "nope"}, status=401),
        ok({"object": "list"}),
        lambda request: httpx.Response(200, text="<html>"),
    ],
)
async def test_the_token_is_never_logged_on_a_failure_path(
    handler: object, caplog: pytest.LogCaptureFixture
) -> None:
    # INVARIANT: error paths are where secrets usually leak — an exception message that
    # interpolates the request is the classic way this happens.
    adapter, _ = source_for(handler)
    with caplog.at_level(logging.DEBUG), pytest.raises(Exception) as excinfo:
        await adapter.fetch(Credential.derive(TOKEN))
    assert TOKEN not in caplog.text
    assert TOKEN not in str(excinfo.value)
