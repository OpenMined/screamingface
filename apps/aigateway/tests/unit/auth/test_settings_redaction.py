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


def test_short_secret_rejected() -> None:
    try:
        Settings(jwt_secret=SecretStr("short"))
    except ValueError as exc:
        assert "secret must be at least 32 characters" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("short jwt_secret was accepted")
