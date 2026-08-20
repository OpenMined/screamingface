"""Benchmark prose is seeded from the Engine catalogue, never from chart values (OME-904).

FEATURE: benchmark descriptions on the leaderboard, with one authoring site.
STORY: as a leaderboard reader, I see what a benchmark tests without leaving the board.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from scoreboard.scores.models import Benchmark
from scoreboard.seed import (
    EngineCatalogUnavailable,
    fetch_engine_benchmarks,
    load_benchmarks_json,
    seed_benchmarks,
    seed_from_sources,
)

pytestmark = pytest.mark.asyncio

ENGINE_URL = "https://engine.test"

_CATALOG = {
    "object": "list",
    "data": [
        {
            "object": "benchmark",
            "id": "draco",
            "title": "DRACO",
            "description": "A 100-task DRACO reproduction with official score arithmetic.",
            "revision": "rev-draco",
            "case_count": 100,
            "focus": "Research reports with citations",
            "dataset_url": "https://huggingface.co/datasets/perplexity-ai/draco",
            "href": "/v1/benchmarks/draco",
        },
        {
            "object": "benchmark",
            "id": "ifeval",
            "title": "IFEval",
            "description": "The canonical 541-prompt instruction-following benchmark.",
            "revision": "rev-ifeval",
            "case_count": 541,
            "href": "/v1/benchmarks/ifeval",
        },
    ],
}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _serving(payload: object, *, status: int = 200) -> httpx.Client:
    return _client(lambda request: httpx.Response(status, json=payload))


def _refusing(exc: Exception) -> httpx.Client:
    def _raise(request: httpx.Request) -> httpx.Response:
        raise exc

    return _client(_raise)


# --- reading the catalogue ------------------------------------------------------------------


async def test_a_catalog_entry_becomes_a_seed_row() -> None:
    with _serving(_CATALOG) as client:
        rows = fetch_engine_benchmarks(ENGINE_URL, client=client)

    draco = rows[0]
    assert draco.id == "draco"
    # The Engine calls it `title`; the board's column is `display_name`. One mapping, one place.
    assert draco.display_name == "DRACO"
    assert draco.description == "A 100-task DRACO reproduction with official score arithmetic."
    assert draco.revision == "rev-draco"
    assert draco.focus == "Research reports with citations"
    assert draco.dataset_url == "https://huggingface.co/datasets/perplexity-ai/draco"


async def test_an_entry_without_display_extras_seeds_them_as_absent() -> None:
    # WHY: the Engine omits the key rather than sending null, and the portal already renders an
    # em dash for a benchmark with no focus line.
    with _serving(_CATALOG) as client:
        ifeval = fetch_engine_benchmarks(ENGINE_URL, client=client)[1]

    assert ifeval.focus is None
    assert ifeval.dataset_url is None
    assert ifeval.revision == "rev-ifeval"


async def test_catalog_fields_the_board_does_not_display_are_ignored() -> None:
    # INVARIANT: the Engine may grow its catalogue (case_count, href, check_surface, whatever
    # comes next) without breaking a deploy. The board reads the fields it displays and no more.
    payload = {
        "object": "list",
        "data": [
            {
                "id": "draco",
                "title": "DRACO",
                "description": "Text.",
                "revision": "rev",
                "case_count": 100,
                "href": "/v1/benchmarks/draco",
                "check_surface": {"check_route": "/x", "feedback_intent": "f"},
                "a_field_invented_next_quarter": True,
            }
        ],
    }
    with _serving(payload) as client:
        rows = fetch_engine_benchmarks(ENGINE_URL, client=client)

    assert [row.id for row in rows] == ["draco"]


async def test_the_catalog_path_is_appended_to_the_configured_engine_url() -> None:
    seen: list[str] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"object": "list", "data": []})

    with _client(_record) as client:
        fetch_engine_benchmarks("https://engine.test/", client=client)

    assert seen == ["https://engine.test/v1/benchmarks"]


# --- refusing to guess when the catalogue cannot be read -------------------------------------


async def test_a_transport_failure_is_reported_as_a_seed_error() -> None:
    # INVARIANT: an httpx exception never escapes the seed module. The deploy log must name the
    # thing that failed, not leak a library's internals.
    with _refusing(httpx.ConnectError("no route to host")) as client:
        with pytest.raises(EngineCatalogUnavailable, match="engine.test"):
            fetch_engine_benchmarks(ENGINE_URL, client=client)


async def test_an_error_status_is_reported_as_a_seed_error() -> None:
    with _serving({"detail": "down"}, status=503) as client:
        with pytest.raises(EngineCatalogUnavailable, match="503"):
            fetch_engine_benchmarks(ENGINE_URL, client=client)


async def test_a_body_that_is_not_json_is_reported_as_a_seed_error() -> None:
    with _client(lambda request: httpx.Response(200, text="<html>proxy error</html>")) as client:
        with pytest.raises(EngineCatalogUnavailable):
            fetch_engine_benchmarks(ENGINE_URL, client=client)


async def test_a_catalog_entry_missing_a_displayed_field_is_reported_as_a_seed_error() -> None:
    payload = {"object": "list", "data": [{"id": "draco", "revision": "rev"}]}
    with _serving(payload) as client:
        with pytest.raises(EngineCatalogUnavailable):
            fetch_engine_benchmarks(ENGINE_URL, client=client)


# --- the Engine is the only copy, not merely the preferred one -------------------------------


async def test_an_engine_row_wins_over_a_configured_row_with_the_same_id(
    tortoise_db: None,
) -> None:
    # INVARIANT: this is what makes the Engine the ONLY copy. A deploy that reintroduces prose
    # under a published id is ignored, so the text cannot drift back into configuration.
    configured = load_benchmarks_json(
        '[{"id":"draco","display_name":"Stale DRACO","description":"Hand-typed copy"}]'
    )
    with _serving(_CATALOG) as client:
        report = await seed_from_sources(
            engine_url=ENGINE_URL, configured=configured, client=client
        )

    draco = await Benchmark.get(id="draco")
    assert draco.display_name == "DRACO"
    assert draco.description == "A 100-task DRACO reproduction with official score arithmetic."
    assert report.shadowed == ["draco"]


async def test_a_configured_row_the_engine_does_not_publish_is_kept(tortoise_db: None) -> None:
    # WHY: the legacy demo entries predate the Engine catalogue and have no Engine counterpart.
    configured = load_benchmarks_json(
        '[{"id":"hle","display_name":"News Hallucinations","description":"OpenMined HLE"}]'
    )
    with _serving(_CATALOG) as client:
        await seed_from_sources(engine_url=ENGINE_URL, configured=configured, client=client)

    assert sorted(row.id for row in await Benchmark.all()) == ["draco", "hle", "ifeval"]


async def test_the_seeded_revision_is_the_catalog_revision(tortoise_db: None) -> None:
    # INVARIANT: a submission carries the Engine's revision and the board ranks per revision.
    # Both values now come from one response, so they cannot drift apart the way a hand-copied
    # chart value did.
    configured = load_benchmarks_json('[{"id":"draco","display_name":"X","revision":"stale"}]')
    with _serving(_CATALOG) as client:
        await seed_from_sources(engine_url=ENGINE_URL, configured=configured, client=client)

    assert (await Benchmark.get(id="draco")).revision == "rev-draco"


# --- what happens when the Engine is unreachable at deploy -----------------------------------


async def test_an_unreachable_engine_leaves_an_already_seeded_board_untouched(
    tortoise_db: None,
) -> None:
    # WHY not fail the deploy: re-seeding refreshes a populated board, so blocking a Scoreboard
    # release on an unrelated service's health would cost availability and buy nothing.
    await seed_benchmarks(
        load_benchmarks_json(
            '[{"id":"draco","display_name":"DRACO","description":"Kept","revision":"rev-draco"}]'
        )
    )
    configured = load_benchmarks_json('[{"id":"hle","display_name":"News Hallucinations"}]')

    with _refusing(httpx.ConnectError("down")) as client:
        report = await seed_from_sources(
            engine_url=ENGINE_URL, configured=configured, client=client
        )

    assert (await Benchmark.get(id="draco")).description == "Kept"
    assert await Benchmark.filter(id="hle").exists()
    assert report.engine_error is not None
    assert report.bootstrap_failed is False


async def test_an_unreachable_engine_fails_when_no_row_carries_a_revision(
    tortoise_db: None,
) -> None:
    # INVARIANT: only a benchmark the Engine published carries a revision, so "no row has one"
    # means no successful seed has ever run. Exiting zero there would publish a board holding
    # nothing but legacy demo entries and call it a success.
    configured = load_benchmarks_json('[{"id":"hle","display_name":"News Hallucinations"}]')

    with _refusing(httpx.ConnectError("down")) as client:
        report = await seed_from_sources(
            engine_url=ENGINE_URL, configured=configured, client=client
        )

    assert report.bootstrap_failed is True


async def test_no_configured_engine_url_seeds_only_the_configured_rows(tortoise_db: None) -> None:
    # WHY: a local or test deployment may run the board without an Engine at all.
    configured = load_benchmarks_json('[{"id":"hle","display_name":"News Hallucinations"}]')

    report = await seed_from_sources(engine_url=None, configured=configured)

    assert [row.id for row in await Benchmark.all()] == ["hle"]
    assert report.engine_error is None
    assert report.bootstrap_failed is False
