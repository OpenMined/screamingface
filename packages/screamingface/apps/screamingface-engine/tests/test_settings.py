from __future__ import annotations

import pytest

from screamingface_engine.settings import Settings, SettingsError


def test_settings_resolve_from_environment() -> None:
    settings = Settings.from_env(
        {
            "URL4_HOST": "0.0.0.0",
            "URL4_PORT": "4500",
            "AIGATEWAY_URL": "http://gateway:9105/",
            "AIGATEWAY_TIMEOUT": "30.5",
            "SCREAMINGFACE_ENGINE_TIMEOUT": "90",
            "SCREAMINGFACE_ENGINE_MAX_INFLIGHT": "7",
        }
    )

    assert settings == Settings(
        host="0.0.0.0",
        port=4500,
        gateway_url="http://gateway:9105",
        gateway_timeout=30.5,
        evaluation_timeout=90,
        max_inflight=7,
    )


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"URL4_PORT": "bad"}, "URL4_PORT must be an integer"),
        ({"URL4_PORT": "0"}, "between 1 and 65535"),
        ({"AIGATEWAY_URL": "gateway:9105"}, "absolute http"),
        ({"AIGATEWAY_TIMEOUT": "nan"}, "positive finite"),
        ({"SCREAMINGFACE_ENGINE_TIMEOUT": "0"}, "positive finite"),
        ({"SCREAMINGFACE_ENGINE_MAX_INFLIGHT": "0"}, "at least 1"),
    ],
)
def test_settings_reject_invalid_values(env: dict[str, str], message: str) -> None:
    with pytest.raises(SettingsError, match=message):
        Settings.from_env(env)
