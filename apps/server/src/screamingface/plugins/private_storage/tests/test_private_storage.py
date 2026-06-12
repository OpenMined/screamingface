"""CRUD + url4 integration tests for the private-storage plugin."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig

# Re-export the state plugin's temp_state_path fixture so the state plugin
# initializes Tortoise against a fresh sqlite file under tmp_path.
from screamingface.plugins.state.testing import temp_state_path  # noqa: F401


@pytest.fixture
def app(temp_state_path: Path) -> FastAPI:  # noqa: F811
    config = AppConfig(
        plugins=["state", "private-storage", "url4-executor"],
        plugin_config={},
    )
    return create_app(config)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # The context manager runs startup/shutdown (Tortoise init via the state plugin).
    with TestClient(app) as c:
        yield c


def test_create_get_update_list_delete(client: TestClient) -> None:
    # create
    r = client.post("/private", json={"content": "# Title", "label": "notes"})
    assert r.status_code == 200
    uuid = r.json()["uuid"]
    assert r.json()["url"] == f"/private/{uuid}"

    # get raw markdown
    r = client.get(f"/private/{uuid}")
    assert r.status_code == 200
    assert r.text == "# Title"
    assert r.headers["content-type"].startswith("text/markdown")

    # update
    r = client.put(f"/private/{uuid}", json={"content": "# Changed"})
    assert r.status_code == 200
    assert client.get(f"/private/{uuid}").text == "# Changed"

    # list
    r = client.get("/private")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["uuid"] == uuid and row["label"] == "notes" for row in rows)

    # delete
    assert client.delete(f"/private/{uuid}").status_code == 204
    assert client.get(f"/private/{uuid}").status_code == 404


def test_unknown_uuid_404(client: TestClient) -> None:
    assert client.get("/private/not-a-uuid").status_code == 404
    assert client.get("/private/00000000-0000-0000-0000-000000000000").status_code == 404


async def test_url4_resolves_private_entity(app: FastAPI) -> None:
    """A /private/{uuid7} relurl resolves to the stored markdown inside url4.

    The /ensemble/format endpoint only *formats* an expression; actual
    resolution of a bare relative URL happens via the url4 resolver, which
    fetches the path in-process through the ASGI transport. We exercise that
    real resolution path directly (resolve(Url4RelUrl(...), app=app)) and
    assert it yields the stored content. Everything runs on the test's event
    loop (in-process ASGI client + resolver) so Tortoise stays on one loop.
    """
    import httpx
    from httpx import ASGITransport

    from screamingface.plugins.url4_executor.url4_ast import Url4RelUrl
    from screamingface.plugins.url4_executor.url4_resolve import resolve

    async with app.router.lifespan_context(app):  # Tortoise init on this loop
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            uuid = (await ac.post("/private", json={"content": "SECRET-CONTEXT"})).json()["uuid"]

        resolved = await resolve(Url4RelUrl(value=f"/private/{uuid}"), app=app)
        assert resolved == "SECRET-CONTEXT"
