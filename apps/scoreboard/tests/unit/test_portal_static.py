from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scoreboard.config import Settings
from scoreboard.main import create_app


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite://{tmp_path / 'scoreboard.sqlite3'}",
        "cors_origins": [],
    }
    values.update(overrides)
    return Settings(**values)


def test_portal_has_no_auth_settings() -> None:
    settings = Settings()

    assert not hasattr(settings, "portal_auth_enabled")
    assert not hasattr(settings, "portal_auth_username")
    assert not hasattr(settings, "portal_auth_password")


def test_root_portal_is_public(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/")

        assert response.status_code == 200
        assert "Results you can reproduce" in response.text


def test_portal_assets_and_pages_are_public(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        for path in ("/index.html", "/benchmark.html", "/spec.html", "/data.html", "/main.js"):
            response = client.get(path)
            assert response.status_code == 200, path


def test_portal_pages_include_plausible_analytics(tmp_path: Path) -> None:
    # OME-373: traffic/visit analytics on the public board — a future rewrite of any
    # of these pages must not silently drop the tracking snippet.
    with TestClient(create_app(_settings(tmp_path))) as client:
        for path in ("/index.html", "/benchmark.html", "/spec.html", "/data.html"):
            response = client.get(path)
            assert "plausible.io/js/pa-ysspwNldM0r_4o-m1utPa.js" in response.text, path


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

        eval_results = client.get("/livetruth-latest.eval.jsonl")
        assert eval_results.status_code == 200
        assert eval_results.headers["content-type"].startswith("text/plain")
        assert '"expected_answer"' in eval_results.text


@pytest.mark.parametrize(
    "path",
    [
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
    (artifacts / "livetruth-latest.eval.jsonl").write_text("{}\n", encoding="utf-8")

    settings = _settings(tmp_path, portal_artifacts_dir=artifacts)

    with pytest.raises(RuntimeError, match="livetruth-masking.dataset.jsonl"):
        create_app(settings)
