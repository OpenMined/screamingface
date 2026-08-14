from __future__ import annotations

import pytest

from scoreboard.scores.models import Benchmark
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
