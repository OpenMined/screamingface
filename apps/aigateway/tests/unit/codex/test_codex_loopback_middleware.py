from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import SecretStr

from aigateway.config import Settings
from aigateway.main import create_app


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("AIGATEWAY_FAKE_KEYCHAIN", "1")
    monkeypatch.setenv("AIGATEWAY_KEYCHAIN_FILE", str(tmp_path / "keychain.json"))
    return create_app(
        Settings(
            auth_enabled=False,
            database_url=SecretStr(f"sqlite://{tmp_path / 'aigateway.sqlite3'}"),
        )
    )


def test_auth_disabled_gateway_allows_loopback_host_and_client(tmp_path, monkeypatch) -> None:
    client = TestClient(
        _app(tmp_path, monkeypatch),
        base_url="http://127.0.0.1:9105",
        client=("127.0.0.1", 50000),
    )

    resp = client.get("/healthz", headers={"host": "127.0.0.1:9105"})

    assert resp.status_code == 200


def test_auth_disabled_gateway_rejects_dns_rebinding_host(tmp_path, monkeypatch) -> None:
    client = TestClient(
        _app(tmp_path, monkeypatch),
        base_url="http://evil.example.com:9105",
        client=("127.0.0.1", 50000),
    )

    resp = client.get("/healthz", headers={"host": "evil.example.com:9105"})

    assert resp.status_code == 403
    assert resp.json()["code"] == "loopback_only"


def test_auth_disabled_gateway_rejects_non_loopback_client(tmp_path, monkeypatch) -> None:
    client = TestClient(
        _app(tmp_path, monkeypatch),
        base_url="http://127.0.0.1:9105",
        client=("192.168.1.20", 50000),
    )

    resp = client.get("/healthz", headers={"host": "127.0.0.1:9105"})

    assert resp.status_code == 403
    assert resp.json()["code"] == "loopback_only"
