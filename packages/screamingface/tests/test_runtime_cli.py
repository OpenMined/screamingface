from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from screamingface._runtime import cli
from screamingface._runtime.bootstrap import enable_local_providers, scoreboard_seed_json
from screamingface._runtime.config import RuntimeConfig


def test_parser_exposes_public_commands() -> None:
    parser = cli._parser()

    for command in ("up", "down", "status", "logs", "prepare"):
        assert parser.parse_args([command]).command == command


def test_runtime_data_is_user_scoped(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)

    assert config.state_path == tmp_path / "runtime.json"
    assert config.log_path == tmp_path / "runtime.log"
    assert config.assets_dir == tmp_path / "benchmark-assets"


def test_owned_state_is_removed_but_foreign_state_is_preserved(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)
    config.state_path.write_text(json.dumps({"pid": 42, "owner_token": "ours"}))

    cli._remove_owned_state(config, "theirs")
    assert config.state_path.exists()
    cli._remove_owned_state(config, "ours")
    assert not config.state_path.exists()


def test_logs_rejects_negative_tail(tmp_path: Path) -> None:
    config = RuntimeConfig(data_dir=tmp_path)

    with pytest.raises(RuntimeError, match="zero or greater"):
        cli._logs(config, tail=-1, follow=False)


def test_plain_sdk_import_does_not_load_server_packages() -> None:
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import sys, screamingface; "
            "print(any(name in sys.modules "
            "for name in ('uvicorn', 'aigateway', 'screamingface_engine')))",
        ],
        text=True,
    )

    assert output.strip() == "False"


def test_local_runtime_enables_openrouter_without_overriding_an_explicit_choice() -> None:
    default_environment: dict[str, str] = {}
    disabled_environment = {"AIGW_OPENROUTER_ENABLED": "false"}

    enable_local_providers(default_environment)
    enable_local_providers(disabled_environment)

    assert default_environment == {"AIGW_OPENROUTER_ENABLED": "true"}
    assert disabled_environment == {"AIGW_OPENROUTER_ENABLED": "false"}


def test_scoreboard_seed_is_derived_from_engine_benchmark_identity() -> None:
    class Benchmark:
        id = "ifeval"
        title = "IFEval"
        description = "Deterministic instruction following"
        revision = "revision-from-engine"

    assert json.loads(scoreboard_seed_json([Benchmark()])) == [
        {
            "id": "ifeval",
            "display_name": "IFEval",
            "description": "Deterministic instruction following",
            "revision": "revision-from-engine",
        }
    ]


def test_the_local_projection_carries_the_leaderboard_display_fields() -> None:
    # INVARIANT: the local board must show what the deployed board shows (OME-904). The Engine
    # publishes focus and dataset_url in its catalogue; a local stack reads the same registry by
    # import, so dropping them here would make a local leaderboard quietly poorer than the real
    # one — the two projections have to stay in step.
    class Benchmark:
        id = "draco"
        title = "DRACO"
        description = "Research reports"
        revision = "revision-from-engine"
        focus = "Research reports with citations"
        dataset_url = "https://huggingface.co/datasets/perplexity-ai/draco"

    projected = json.loads(scoreboard_seed_json([Benchmark()]))[0]

    assert projected["focus"] == "Research reports with citations"
    assert projected["dataset_url"] == "https://huggingface.co/datasets/perplexity-ai/draco"


def test_the_local_projection_omits_display_fields_a_benchmark_did_not_declare() -> None:
    # WHY omit rather than send null: the seed contract forbids unknown keys and treats an
    # absent optional as "leave it alone", which is what an undeclared focus line means.
    class Benchmark:
        id = "ifeval"
        title = "IFEval"
        description = "Deterministic instruction following"
        revision = "revision-from-engine"
        focus = None
        dataset_url = None

    projected = json.loads(scoreboard_seed_json([Benchmark()]))[0]

    assert "focus" not in projected
    assert "dataset_url" not in projected
