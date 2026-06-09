from __future__ import annotations

import base64
import os

import pytest
from pydantic import ValidationError

from aigateway.config import Settings


@pytest.fixture(autouse=True)
def _clean_secret_env(monkeypatch):
    # Settings reads os.environ; isolate the two fields under test.
    for key in ("AIGATEWAY_SECRET_KEY", "AIGATEWAY_SECRET_PROVIDER"):
        monkeypatch.delenv(key, raising=False)


def _settings(**env) -> Settings:
    # Dict-spread so static checkers don't flag the dotenv/alias kwargs (read at
    # runtime by pydantic-settings via **values).
    return Settings(**{"_env_file": None, **env})


def test_secret_provider_defaults_to_local() -> None:
    assert _settings().secret_provider == "local"


@pytest.mark.parametrize(
    "raw,expected", [("LOCAL", "local"), ("KMS", "kms"), ("local", "local"), ("Kms", "kms")]
)
def test_secret_provider_normalized(raw: str, expected: str) -> None:
    assert _settings(AIGATEWAY_SECRET_PROVIDER=raw).secret_provider == expected


def test_secret_provider_unknown_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(AIGATEWAY_SECRET_PROVIDER="vault")


def test_secret_key_not_validated_at_settings_layer_and_not_leaked() -> None:
    # SF-221 review #5: content validation moved to runtime (_decode_key) so a
    # rejected key never reaches Pydantic's ValidationError input_value and cannot
    # leak into startup logs despite the SecretStr type.
    bad = "definitely-not-valid-base64-or-32-bytes=="
    settings = _settings(AIGATEWAY_SECRET_KEY=bad)
    assert settings.secret_key is not None
    assert repr(settings.secret_key) == "SecretStr('**********')"
    assert bad not in repr(settings.secret_key)
    assert bad not in str(settings)


def test_secret_key_valid_value_preserved() -> None:
    good = base64.b64encode(os.urandom(32)).decode()
    settings = _settings(AIGATEWAY_SECRET_KEY=good)
    assert settings.secret_key is not None
    assert settings.secret_key.get_secret_value() == good
