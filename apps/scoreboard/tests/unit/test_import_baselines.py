from __future__ import annotations

import pytest

from scoreboard.import_baselines import import_baselines, load_baselines_json
from scoreboard.scores.baseline_store import BaselineStore
from scoreboard.scores.store import ScoreStore

pytestmark = pytest.mark.asyncio


async def _register_benchmark(benchmark_id: str = "demo-benchmark") -> None:
    await ScoreStore().register_benchmark(
        benchmark_id=benchmark_id,
        display_name="Demo Benchmark",
        description="Fixture benchmark",
        dataset_url="https://example.test/demo-benchmark.jsonl",
    )


async def test_import_baselines_inserts_and_updates(tortoise_db: None) -> None:
    await _register_benchmark()
    first = load_baselines_json(
        '[{"benchmark_id":"demo-benchmark","model_name":"GPT-5.2","score":0.62,'
        '"source":"artificial_analysis"}]'
    )
    second = load_baselines_json(
        '[{"benchmark_id":"demo-benchmark","model_name":"GPT-5.2","score":0.71,'
        '"source":"artificial_analysis","source_url":"https://artificialanalysis.ai/demo-benchmark"}]'
    )

    imported = await import_baselines(first)
    reimported = await import_baselines(second)
    all_baselines = await BaselineStore().list_baselines("demo-benchmark")

    assert imported[0].score == 0.62
    assert reimported[0].score == 0.71
    assert reimported[0].source_url == "https://artificialanalysis.ai/demo-benchmark"
    assert len(all_baselines) == 1


async def test_load_baselines_json_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError, match="invalid baseline import payload"):
        load_baselines_json('{"benchmark_id":"demo-benchmark"}')


async def test_load_baselines_json_rejects_malformed_json() -> None:
    with pytest.raises(ValueError, match="invalid baseline import JSON"):
        load_baselines_json("not json")


async def test_import_baselines_propagates_unknown_benchmark_error(
    tortoise_db: None,
) -> None:
    rows = load_baselines_json(
        '[{"benchmark_id":"missing","model_name":"GPT-5.2","score":0.62,'
        '"source":"artificial_analysis"}]'
    )

    with pytest.raises(ValueError, match="unknown benchmark_id"):
        await import_baselines(rows)
