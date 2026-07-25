from __future__ import annotations

from typing import Any

import jwt
import pytest
from fastapi import Request

from aigateway.core.auth.middleware import ANONYMOUS_ACCOUNT_ID, anonymous_account
from aigateway.core.auth.models import BaseAccount
from aigateway.core.auth.resolvers import IdentityResolver, LocalJwtResolver, Rejection


class _StubResolver:
    """Records invocation so chain-ordering assertions can prove short-circuiting."""

    def __init__(self, name: str, outcome: BaseAccount | Rejection | None) -> None:
        self.name = name
        self._outcome = outcome
        self.calls = 0

    async def resolve(self, _request: Request) -> BaseAccount | Rejection | None:
        self.calls += 1
        return self._outcome


def _install(client, *resolvers: Any) -> None:
    client.app.state.identity_resolvers = list(resolvers)


def test_stub_satisfies_the_identity_resolver_port() -> None:
    # INVARIANT: the port is structural — adapters never inherit from a base class.
    assert isinstance(_StubResolver("x", None), IdentityResolver)
    assert isinstance(LocalJwtResolver(), IdentityResolver)


def test_first_account_wins_and_later_resolvers_are_not_invoked(client) -> None:
    winner = _StubResolver("winner", anonymous_account())
    never = _StubResolver("never", anonymous_account())
    _install(client, winner, never)

    response = client.get("/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(ANONYMOUS_ACCOUNT_ID)
    assert winner.calls == 1
    assert never.calls == 0


def test_none_falls_through_to_the_next_resolver(client) -> None:
    skipped = _StubResolver("skipped", None)
    winner = _StubResolver("winner", anonymous_account())
    _install(client, skipped, winner)

    response = client.get("/v1/auth/me")

    assert response.status_code == 200
    assert skipped.calls == 1
    assert winner.calls == 1


def test_rejection_does_not_stop_a_later_resolver_from_authenticating(client) -> None:
    # WHY: a Cloudflare token arrives in `Authorization: Bearer` too, so the local
    # JWT resolver refusing it must not deny the CF resolver its turn.
    rejecting = _StubResolver("rejecting", Rejection(detail="not mine"))
    winner = _StubResolver("winner", anonymous_account())
    _install(client, rejecting, winner)

    response = client.get("/v1/auth/me")

    assert response.status_code == 200
    assert rejecting.calls == 1


def test_recorded_rejection_surfaces_when_the_chain_is_exhausted(client) -> None:
    _install(
        client,
        _StubResolver("a", Rejection(detail="precise reason")),
        _StubResolver("b", None),
    )

    response = client.get("/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "precise reason"


def test_first_rejection_wins_over_a_later_one(client) -> None:
    _install(
        client,
        _StubResolver("a", Rejection(detail="first")),
        _StubResolver("b", Rejection(detail="second")),
    )

    response = client.get("/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "first"


def test_rejection_carries_its_own_status_code(client) -> None:
    _install(client, _StubResolver("a", Rejection(detail="teapot", status_code=418)))

    response = client.get("/v1/auth/me")

    assert response.status_code == 418
    assert response.json()["detail"] == "teapot"


def test_exhausted_chain_without_a_rejection_is_a_generic_401(client) -> None:
    _install(client, _StubResolver("a", None))

    response = client.get("/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


def test_empty_chain_is_a_generic_401(client) -> None:
    _install(client)

    response = client.get("/v1/auth/me")

    assert response.status_code == 401


def test_auth_disabled_short_circuits_ahead_of_the_chain(client) -> None:
    # INVARIANT: the auth_enabled=False escape hatch stays in front of the chain;
    # no resolver may observe a request the gateway is not authenticating at all.
    never = _StubResolver("never", Rejection(detail="unreachable"))
    _install(client, never)
    client.app.state.settings.auth_enabled = False

    response = client.get("/v1/auth/me")

    assert response.status_code == 200
    assert never.calls == 0


def test_default_chain_is_registered_with_exactly_the_local_jwt_resolver(client) -> None:
    resolvers = client.app.state.identity_resolvers

    assert [r.name for r in resolvers] == ["local_jwt"]


@pytest.mark.asyncio
async def test_local_jwt_resolver_falls_through_on_a_non_hs256_token() -> None:
    # WHY: Cloudflare Access signs RS256. The local resolver must decline those so
    # the CF resolver (OME-591) gets its turn, rather than claiming and rejecting them.
    token = jwt.encode({"sub": "x"}, "k" * 48, algorithm="HS384")

    outcome = await LocalJwtResolver().resolve(_bearer_request(token))

    assert outcome is None


@pytest.mark.asyncio
async def test_local_jwt_resolver_rejects_an_unparseable_bearer_token() -> None:
    outcome = await LocalJwtResolver().resolve(_bearer_request("not-a-token"))

    assert isinstance(outcome, Rejection)
    assert "Invalid token" in str(outcome.detail)


@pytest.mark.asyncio
async def test_local_jwt_resolver_ignores_a_request_without_a_bearer_header() -> None:
    outcome = await LocalJwtResolver().resolve(_request(headers=[]))

    assert outcome is None


def _bearer_request(token: str) -> Request:
    return _request(headers=[(b"authorization", f"Bearer {token}".encode())])


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "query_string": b"",
        }
    )
