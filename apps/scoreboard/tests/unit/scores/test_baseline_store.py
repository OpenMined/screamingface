from __future__ import annotations

import pytest

from scoreboard.scores.baseline_store import BaselineStore
from scoreboard.scores.models import Baseline
from scoreboard.scores.schemas import BaselineImportRow
from scoreboard.scores.store import ScoreStore

pytestmark = pytest.mark.asyncio


def _row(
    *,
    benchmark_id: str = "demo-benchmark",
    model_name: str = "GPT-5.2",
    score: float = 0.62,
    source: str = "artificial_analysis",
    source_url: str | None = None,
    metadata: dict[str, object] | None = None,
) -> BaselineImportRow:
    return BaselineImportRow(
        benchmark_id=benchmark_id,
        model_name=model_name,
        score=score,
        source=source,
        source_url=source_url,
        metadata=metadata,
    )


async def _register_benchmark(benchmark_id: str = "demo-benchmark") -> None:
    await ScoreStore().register_benchmark(
        benchmark_id=benchmark_id,
        display_name="Demo Benchmark",
        description="Fixture benchmark",
        dataset_url="https://example.test/demo-benchmark.jsonl",
    )


async def test_import_baseline_inserts_new_row(tortoise_db: None) -> None:
    await _register_benchmark()
    store = BaselineStore()

    imported = await store.import_baseline(_row())

    assert imported.benchmark_id == "demo-benchmark"
    assert imported.model_name == "GPT-5.2"
    assert imported.score == 0.62
    assert imported.source == "artificial_analysis"
    assert imported.source_url is None
    assert imported.metadata is None


async def test_import_baseline_reimport_updates_existing_row_in_place(
    tortoise_db: None,
) -> None:
    await _register_benchmark()
    store = BaselineStore()

    first = await store.import_baseline(_row(score=0.62))
    second = await store.import_baseline(
        _row(score=0.71, source_url="https://artificialanalysis.ai/demo-benchmark")
    )
    all_baselines = await store.list_baselines("demo-benchmark")

    assert first.id == second.id
    assert second.score == 0.71
    assert second.source_url == "https://artificialanalysis.ai/demo-benchmark"
    assert len(all_baselines) == 1


async def test_import_baseline_same_model_different_source_creates_separate_rows(
    tortoise_db: None,
) -> None:
    await _register_benchmark()
    store = BaselineStore()

    await store.import_baseline(_row(source="artificial_analysis", score=0.62))
    await store.import_baseline(_row(source="lmarena", score=0.58))
    all_baselines = await store.list_baselines("demo-benchmark")

    assert {baseline.source for baseline in all_baselines} == {"artificial_analysis", "lmarena"}


async def test_import_baseline_rejects_unknown_benchmark(tortoise_db: None) -> None:
    store = BaselineStore()

    with pytest.raises(ValueError, match="unknown benchmark_id"):
        await store.import_baseline(_row(benchmark_id="does-not-exist"))


async def test_list_baselines_orders_by_accuracy_descending(tortoise_db: None) -> None:
    await _register_benchmark()
    store = BaselineStore()
    await store.import_baseline(_row(model_name="Model A", source="lmarena", score=0.40))
    await store.import_baseline(
        _row(model_name="Model B", source="artificial_analysis", score=0.90)
    )
    await store.import_baseline(_row(model_name="Model C", source="lmarena", score=0.65))

    baselines = await store.list_baselines("demo-benchmark")

    assert [baseline.score for baseline in baselines] == [0.90, 0.65, 0.40]


async def test_list_baselines_scoped_to_benchmark(tortoise_db: None) -> None:
    await _register_benchmark("demo-benchmark")
    await _register_benchmark("other")
    store = BaselineStore()
    await store.import_baseline(_row(benchmark_id="demo-benchmark", score=0.62))
    await store.import_baseline(_row(benchmark_id="other", score=0.99))

    baselines = await store.list_baselines("demo-benchmark")

    assert [baseline.benchmark_id for baseline in baselines] == ["demo-benchmark"]


async def test_list_baselines_returns_empty_list_when_none_imported(
    tortoise_db: None,
) -> None:
    await _register_benchmark()
    store = BaselineStore()

    baselines = await store.list_baselines("demo-benchmark")

    assert baselines == []


async def test_import_many_persists_every_row_when_all_valid(tortoise_db: None) -> None:
    await _register_benchmark()
    store = BaselineStore()

    imported = await store.import_many(
        [_row(model_name="Model A", score=0.4), _row(model_name="Model B", score=0.5)]
    )
    all_baselines = await store.list_baselines("demo-benchmark")

    assert len(imported) == 2
    assert len(all_baselines) == 2


async def test_import_many_rolls_back_earlier_rows_when_a_later_row_fails(
    tortoise_db: None,
) -> None:
    await _register_benchmark()
    store = BaselineStore()

    with pytest.raises(ValueError, match="unknown benchmark_id"):
        await store.import_many(
            [
                _row(model_name="Model A", score=0.4),
                _row(benchmark_id="does-not-exist", model_name="Model B"),
            ]
        )

    all_baselines = await store.list_baselines("demo-benchmark")
    assert all_baselines == []


async def test_list_baselines_skips_a_row_with_invalid_metadata_instead_of_crashing(
    tortoise_db: None,
) -> None:
    # WHY: simulates a legacy/pre-existing row whose metadata predates the bound
    # (or bypassed it entirely) — created directly via the model, not through
    # BaselineImportRow, since that DTO would itself reject this payload.
    await _register_benchmark()
    store = BaselineStore()
    await store.import_baseline(_row(model_name="Good Model", score=0.5))
    await Baseline.create(
        benchmark_id="demo-benchmark",
        model_name="Bad Model",
        source="artificial_analysis",
        score=0.9,
        metadata={"blob": "x" * 10_000},
    )

    baselines = await store.list_baselines("demo-benchmark")

    assert [baseline.model_name for baseline in baselines] == ["Good Model"]
