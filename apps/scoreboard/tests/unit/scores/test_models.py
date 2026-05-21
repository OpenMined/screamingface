from __future__ import annotations

from typing import Any, cast

from tortoise import fields

from scoreboard.config import Settings
from scoreboard.db import TORTOISE_CONFIG
from scoreboard.main import create_app
from scoreboard.scores.models import (
    BaseBenchmark,
    BaseIdempotencyKey,
    BaseScore,
    BaseScoreboardModel,
    Benchmark,
    IdempotencyKey,
    Score,
)
from scoreboard.scores.store import ScoreStore


def test_tortoise_config_registers_score_models_and_migrations() -> None:
    app_config = TORTOISE_CONFIG["apps"]["models"]

    assert "scoreboard.scores.models" in app_config["models"]
    assert app_config["migrations"] == "scoreboard.scores.migrations"


def test_score_model_table_names_and_indexes() -> None:
    assert Benchmark._meta.db_table == "benchmarks"
    assert Score._meta.db_table == "scores"
    assert IdempotencyKey._meta.db_table == "idempotency_keys"
    assert ("benchmark_id", "accuracy") in Score._meta.indexes
    assert ("benchmark_id", "spec_id", "submitted_at") in Score._meta.indexes


def test_score_model_relations_use_expected_delete_rules() -> None:
    benchmark_field = cast(Any, Score._meta.fields_map["benchmark"])
    score_field = cast(Any, IdempotencyKey._meta.fields_map["score"])

    assert benchmark_field.on_delete is fields.OnDelete.RESTRICT
    assert score_field.on_delete is fields.OnDelete.CASCADE


def test_score_model_package_exports_models_and_abstract_bases() -> None:
    assert Benchmark.__name__ == "Benchmark"
    assert Score.__name__ == "Score"
    assert IdempotencyKey.__name__ == "IdempotencyKey"
    assert BaseScoreboardModel._meta.abstract is True
    assert BaseBenchmark._meta.abstract is True
    assert BaseScore._meta.abstract is True
    assert BaseIdempotencyKey._meta.abstract is True


def test_score_models_live_in_one_model_file_per_concrete_model() -> None:
    assert Benchmark.__module__ == "scoreboard.scores.models.benchmark"
    assert Score.__module__ == "scoreboard.scores.models.score"
    assert IdempotencyKey.__module__ == "scoreboard.scores.models.idempotency_key"


def test_create_app_wires_score_store_without_db_io() -> None:
    app = create_app(Settings(database_url="sqlite://:memory:", cors_origins=[]))

    assert isinstance(app.state.score_store, ScoreStore)
