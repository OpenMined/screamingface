from __future__ import annotations

import pytest

from scoreboard.scores.models import Benchmark, Score
from scoreboard.scores.store import ScoreStore
from scoreboard.seed import load_benchmarks_json, seed_benchmarks

pytestmark = pytest.mark.asyncio


async def test_seed_benchmarks_inserts_and_updates(tortoise_db: None) -> None:
    first = load_benchmarks_json(
        '[{"id":"hle","display_name":"Humanity\'s Last Exam","description":"Fixture benchmark"}]'
    )
    second = load_benchmarks_json(
        '[{"id":"hle","display_name":"News Hallucinations","dataset_url":"https://github.com/openmined/HLE.jsonl"}]'
    )

    seeded = await seed_benchmarks(first)
    reseeded = await seed_benchmarks(second)
    benchmarks = await ScoreStore().list_benchmarks()

    assert await Benchmark.all().count() == 1
    assert seeded[0].id == "hle"
    assert reseeded[0].display_name == "News Hallucinations"
    assert benchmarks == reseeded


async def test_load_benchmarks_json_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError, match="invalid benchmark seed payload"):
        load_benchmarks_json('{"id":"hle"}')


async def test_exact_seed_removes_only_unreferenced_registrations(tortoise_db: None) -> None:
    await seed_benchmarks(
        load_benchmarks_json(
            '[{"id":"retired","display_name":"Retired"},{"id":"draco","display_name":"DRACO"}]'
        )
    )

    seeded = await seed_benchmarks(
        load_benchmarks_json('[{"id":"draco","display_name":"DRACO"}]'),
        exact=True,
    )

    assert [benchmark.id for benchmark in seeded] == ["draco"]
    assert await Benchmark.all().order_by("id").values_list("id", flat=True) == ["draco"]


async def test_exact_seed_refuses_to_delete_stored_results(tortoise_db: None) -> None:
    [retired] = await seed_benchmarks(
        load_benchmarks_json('[{"id":"retired","display_name":"Retired"}]')
    )
    benchmark = await Benchmark.get(id=retired.id)
    await Score.create(
        benchmark=benchmark,
        spec_id="fixture",
        url4_expression="(@)!'answer'",
        accuracy=1.0,
        total_questions=1,
        correct_questions=1,
        ran_with_providers=[],
    )

    with pytest.raises(ValueError, match="cannot remove unseeded benchmarks with stored results"):
        await seed_benchmarks(
            load_benchmarks_json('[{"id":"draco","display_name":"DRACO"}]'),
            exact=True,
        )

    assert await Benchmark.filter(id="retired").exists()
