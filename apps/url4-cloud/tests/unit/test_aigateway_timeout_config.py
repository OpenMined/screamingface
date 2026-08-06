"""The benchmark Runner allows one long model or tool round trip to finish."""

import tomllib
from pathlib import Path

_RUNNER_CONFIG = Path(__file__).resolve().parents[2] / "url4.toml"


def test_runner_allows_ten_minutes_for_each_aigateway_request() -> None:
    with _RUNNER_CONFIG.open("rb") as handle:
        timeout_s = tomllib.load(handle)["aigateway"]["timeout_s"]

    assert timeout_s == 600
