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


# --- OME-775: benchmarks carry the Engine revision through seeding --------------------------


async def test_seed_benchmarks_persists_the_revision(tortoise_db: None) -> None:
    # INVARIANT: the registered revision must match the Engine's computed REVISION exactly, or
    # a submission's revision will never match the board's and every result looks incomparable.
    benchmarks = load_benchmarks_json(
        '[{"id":"draco","display_name":"DRACO","revision":"1c58b3085912e304"}]'
    )

    seeded = await seed_benchmarks(benchmarks)

    assert seeded[0].revision == "1c58b3085912e304"
    assert (await Benchmark.get(id="draco")).revision == "1c58b3085912e304"


async def test_seed_benchmarks_allows_an_absent_revision(tortoise_db: None) -> None:
    # WHY: the retained legacy demo entries (hle/livetruth) have no Engine revision at all.
    benchmarks = load_benchmarks_json('[{"id":"hle","display_name":"News Hallucinations"}]')

    seeded = await seed_benchmarks(benchmarks)

    assert seeded[0].revision is None


async def test_reseeding_updates_the_revision_without_duplicating(tortoise_db: None) -> None:
    # WHY: an Engine benchmark's revision changes whenever its dataset or protocol does, and
    # redeploying must move the registered value rather than create a second row.
    await seed_benchmarks(
        load_benchmarks_json('[{"id":"draco","display_name":"DRACO","revision":"rev-old"}]')
    )

    reseeded = await seed_benchmarks(
        load_benchmarks_json('[{"id":"draco","display_name":"DRACO","revision":"rev-new"}]')
    )

    assert await Benchmark.all().count() == 1
    assert reseeded[0].revision == "rev-new"


async def test_load_benchmarks_json_still_rejects_an_unknown_key() -> None:
    # INVARIANT: the seed payload is extra="forbid", so a typo'd key fails the deploy loudly
    # rather than silently registering a benchmark without its revision.
    with pytest.raises(ValueError, match="invalid benchmark seed payload"):
        load_benchmarks_json('[{"id":"draco","display_name":"DRACO","revsion":"typo"}]')


# --- OME-874: benchmarks carry a short editorial "focus" line -------------------------------


async def test_seed_benchmarks_persists_the_focus(tortoise_db: None) -> None:
    seeded = await seed_benchmarks(
        load_benchmarks_json(
            '[{"id":"draco","display_name":"DRACO","focus":"Research reports with citations"}]'
        )
    )

    assert seeded[0].focus == "Research reports with citations"
    assert (await Benchmark.get(id="draco")).focus == "Research reports with citations"


async def test_seed_benchmarks_allows_an_absent_focus(tortoise_db: None) -> None:
    # WHY: focus is editorial copy rather than data we derive, so a benchmark can legitimately
    # ship without one — the portal renders an em dash instead of an empty cell.
    seeded = await seed_benchmarks(
        load_benchmarks_json('[{"id":"hle","display_name":"News Hallucinations"}]')
    )

    assert seeded[0].focus is None
