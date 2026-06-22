from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scoreboard.config import Settings
from scoreboard.main import create_app


def _auth(username: str = "demo", password: str = "demo") -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite://{tmp_path / 'scoreboard.sqlite3'}",
        "cors_origins": [],
        "portal_auth_enabled": True,
        "portal_auth_username": "demo",
        "portal_auth_password": "demo",
    }
    values.update(overrides)
    return Settings(**values)


def test_portal_auth_is_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCOREBOARD_PORTAL_AUTH_ENABLED", raising=False)

    settings = Settings()

    assert settings.portal_auth_enabled is True


def test_root_portal_requires_basic_auth(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        unauthenticated = client.get("/")
        assert unauthenticated.status_code == 401
        assert unauthenticated.headers["www-authenticate"] == 'Basic realm="scoreboard portal"'

        wrong_password = client.get("/", headers=_auth(password="wrong"))
        assert wrong_password.status_code == 401

        authenticated = client.get("/", headers=_auth())
        assert authenticated.status_code == 200
        assert "Results you can rerun" in authenticated.text


def test_portal_assets_and_pages_require_basic_auth(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        for path in ("/index.html", "/benchmark.html", "/spec.html", "/data.html", "/main.js"):
            assert client.get(path).status_code == 401
            response = client.get(path, headers=_auth())
            assert response.status_code == 200, path


def test_api_routes_remain_public_before_root_static_mount(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.get("/healthz").status_code == 200


def test_public_jsonl_artifacts_are_inline_text_and_unauthenticated(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        latest = client.get("/livetruth-latest.jsonl")
        assert latest.status_code == 200
        assert latest.headers["content-type"].startswith("text/plain")
        assert '"answer"' in latest.text

        masking = client.get("/livetruth-masking.dataset.jsonl")
        assert masking.status_code == 200
        assert masking.headers["content-type"].startswith("text/plain")
        assert '"question"' in masking.text


@pytest.mark.parametrize(
    "path",
    [
        "/livetruth-latest.eval.jsonl",
        "/livetruth-latest.eval.jsonl.txt",
        "/livetruth-latest.answer-key.jsonl",
    ],
)
def test_forbidden_answer_key_artifacts_return_404_without_auth(tmp_path: Path, path: str) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.get(path).status_code == 404


def test_missing_artifact_fails_app_creation(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "livetruth-latest.jsonl").write_text("{}\n", encoding="utf-8")

    settings = _settings(tmp_path, portal_artifacts_dir=artifacts)

    with pytest.raises(RuntimeError, match="livetruth-masking.dataset.jsonl"):
        create_app(settings)


def test_missing_basic_auth_password_fails_when_auth_enabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, portal_auth_password=None)

    with pytest.raises(ValueError, match="SCOREBOARD_PORTAL_AUTH_PASSWORD"):
        create_app(settings)
