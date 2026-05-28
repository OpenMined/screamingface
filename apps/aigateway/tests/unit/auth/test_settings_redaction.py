from __future__ import annotations

from pydantic import SecretStr

from aigateway.config import Settings


def test_secret_settings_are_redacted() -> None:
    settings = Settings(
        database_url=SecretStr("postgres://secret:secret@localhost:5432/secret"),
        jwt_secret=SecretStr("j" * 32),
        admin_password=SecretStr("admin-pass"),
        provisioning_token=SecretStr("p" * 32),
    )
    rendered = "\n".join([repr(settings), str(settings), settings.model_dump_json()])
    assert "postgres://secret" not in rendered
    assert "j" * 32 not in rendered
    assert "admin-pass" not in rendered
    assert "p" * 32 not in rendered


def test_auth_enabled_defaults_true_and_parses_env_zero(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    assert Settings().auth_enabled is True

    monkeypatch.setenv("AIGATEWAY_AUTH_ENABLED", "0")
    assert Settings().auth_enabled is False


def test_public_url_parses_env_and_strips_trailing_slash(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AIGATEWAY_PUBLIC_URL", "https://aigateway.example.com/base/")

    assert Settings().public_url == "https://aigateway.example.com/base"


def test_invalid_public_url_rejected() -> None:
    try:
        Settings(public_url="localhost:9105")
    except ValueError as exc:
        assert "public_url must be an absolute http(s) URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid public_url was accepted")


def test_short_secret_rejected() -> None:
    try:
        Settings(jwt_secret=SecretStr("short"))
    except ValueError as exc:
        assert "secret must be at least 32 characters" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("short jwt_secret was accepted")


def test_short_provisioning_token_rejected() -> None:
    try:
        Settings(provisioning_token=SecretStr("short"))
    except ValueError as exc:
        assert "secret must be at least 32 characters" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("short provisioning_token was accepted")


def test_invalid_admin_password_rejected() -> None:
    try:
        Settings(admin_password=SecretStr("short"))
    except ValueError as exc:
        assert "password must be 8-72 UTF-8 bytes" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("short admin_password was accepted")
