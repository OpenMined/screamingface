"""Declared model ids must be valid URL4 expression paths before the world starts."""

from __future__ import annotations

from pathlib import Path

import pytest

from url4_cloud import job_env
from url4_cloud.model_routes import declared_model_ids
from url4_cloud.runner.config import RunnerConfigError, load_config, parse_config


def _config(model: str) -> dict[str, object]:
    return {
        "aigateway": {
            "default_route": model,
            "models": [{"id": model}],
        }
    }


def test_colon_qualified_model_id_is_rejected_at_config_parse() -> None:
    model = "huggingface/google/gemma-2-2b-it:featherless-ai"

    with pytest.raises(RunnerConfigError, match="URL4 expression path"):
        parse_config(_config(model), {})


def test_expression_path_compatible_model_id_remains_declared() -> None:
    model = "openrouter/openai/gpt-5.5"

    section = parse_config(_config(model), {}).aigateway

    assert section is not None
    assert [item.id for item in section.models] == [model]


def test_control_plane_and_runner_read_the_same_declared_ids() -> None:
    config_path = Path(__file__).resolve().parents[2] / "url4.toml"
    env = {job_env.RUNNER_CONFIG: str(config_path)}

    section = load_config(env).aigateway

    assert section is not None
    assert declared_model_ids(env) == frozenset(item.id for item in section.models)
