"""Tests for session service REST API routes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.session_service.routes import create_router
from screamingface.plugins.session_service.store import FileSessionStore


@pytest.fixture
def store(tmp_path) -> FileSessionStore:
    return FileSessionStore(tmp_path / "sessions")


@pytest.fixture
def client(store: FileSessionStore) -> TestClient:
    app = FastAPI()
    router = create_router(store)
    app.include_router(router)
    return TestClient(app)


class TestCreateSession:
    def test_create_minimal(self, client: TestClient) -> None:
        resp = client.post("/sessions")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["message_count"] == 0

    def test_create_with_title(self, client: TestClient) -> None:
        resp = client.post("/sessions", params={"title": "my chat"})
        assert resp.status_code == 201
        assert resp.json()["title"] == "my chat"


class TestListSessions:
    def test_empty(self, client: TestClient) -> None:
        resp = client.get("/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_after_create(self, client: TestClient) -> None:
        client.post("/sessions", params={"title": "one"})
        client.post("/sessions", params={"title": "two"})
        resp = client.get("/sessions")
        assert len(resp.json()) == 2


class TestGetSession:
    def test_found(self, client: TestClient) -> None:
        create_resp = client.post("/sessions", params={"title": "test"})
        sid = create_resp.json()["id"]
        resp = client.get(f"/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "test"

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/sessions/nonexistent")
        assert resp.status_code == 404


class TestMessages:
    def test_get_empty(self, client: TestClient) -> None:
        create_resp = client.post("/sessions")
        sid = create_resp.json()["id"]
        resp = client.get(f"/sessions/{sid}/messages")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_append_and_get(self, client: TestClient) -> None:
        create_resp = client.post("/sessions")
        sid = create_resp.json()["id"]

        msg = {
            "role": "user",
            "content": [{"type": "text", "text": "hello"}],
            "provider": "anthropic",
        }
        resp = client.post(f"/sessions/{sid}/messages", json=msg)
        assert resp.status_code == 201

        resp = client.get(f"/sessions/{sid}/messages")
        messages = resp.json()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"][0]["text"] == "hello"

    def test_append_to_nonexistent(self, client: TestClient) -> None:
        msg = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
        resp = client.post("/sessions/nonexistent/messages", json=msg)
        assert resp.status_code == 404


class TestDeleteSession:
    def test_delete(self, client: TestClient) -> None:
        create_resp = client.post("/sessions")
        sid = create_resp.json()["id"]
        resp = client.delete(f"/sessions/{sid}")
        assert resp.status_code == 200

        resp = client.get(f"/sessions/{sid}")
        assert resp.status_code == 404

    def test_delete_not_found(self, client: TestClient) -> None:
        resp = client.delete("/sessions/nonexistent")
        assert resp.status_code == 404
