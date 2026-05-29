from __future__ import annotations

import pytest

from scoreboard.config import DEFAULT_DATABASE_URL, Settings, normalize_database_url


def test_database_url_defaults_to_local_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SCOREBOARD_DATABASE_URL", raising=False)

    settings = Settings()

    assert DEFAULT_DATABASE_URL == "sqlite://./scoreboard.sqlite3"
    assert settings.database_url == DEFAULT_DATABASE_URL


def test_database_url_can_use_postgres_override(monkeypatch: pytest.MonkeyPatch) -> None:
    database_url = "postgres://scoreboard:scoreboard@localhost:5434/scoreboard"
    monkeypatch.setenv("SCOREBOARD_DATABASE_URL", database_url)

    settings = Settings()

    assert settings.database_url == database_url


def test_sqlite_root_url_with_bare_filename_is_treated_as_relative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCOREBOARD_DATABASE_URL", "sqlite:///scoreboard-local.sqlite3")

    settings = Settings()

    assert settings.database_url == "sqlite://./scoreboard-local.sqlite3"
    assert normalize_database_url("sqlite:///scoreboard-local.sqlite3") == settings.database_url


def test_sqlite_absolute_url_keeps_absolute_path() -> None:
    assert normalize_database_url("sqlite:////tmp/scoreboard.sqlite3") == (
        "sqlite:////tmp/scoreboard.sqlite3"
    )
