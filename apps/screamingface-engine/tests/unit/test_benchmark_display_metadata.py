"""The Engine owns every word the leaderboard shows about a Benchmark (OME-904).

FEATURE: benchmark descriptions on the leaderboard, with one authoring site.
STORY: as a leaderboard reader, I see what a benchmark tests without leaving the board.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from screamingface_engine.app import create_app
from screamingface_engine.benchmarks import Benchmark, BenchmarkRegistry, candidate
from screamingface_engine.benchmarks.builtins import BUILTIN_BENCHMARKS
from screamingface_engine.config import Settings
from screamingface_engine.testing import InMemoryEventStream

pytestmark = pytest.mark.asyncio


def _benchmark(*, focus: str | None = None, dataset_url: str | None = None) -> Benchmark:
    return Benchmark(
        id="example-smoke",
        title="Example Smoke",
        description="One non-comparable structural probe.",
        revision="example-smoke-v1",
        case_count=3,
        build=lambda selected: candidate(
            f"Explain why the sky looks blue. Selected cases: {selected}.",
            web_search=False,
        ),
        focus=focus,
        dataset_url=dataset_url,
    )


async def _catalog(benchmark: Benchmark) -> dict[str, object]:
    app: FastAPI = create_app(
        Settings(jwt_secret="s"),
        stream=InMemoryEventStream(),
        benchmarks=BenchmarkRegistry((benchmark,)),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://engine.test",
    ) as client:
        entries = (await client.get("/v1/benchmarks")).json()["data"]
    entry: dict[str, object] = entries[0]
    return entry


async def test_a_declared_focus_and_dataset_link_reach_the_catalog() -> None:
    entry = await _catalog(
        _benchmark(
            focus="Structural probing",
            dataset_url="https://huggingface.co/datasets/example/smoke",
        )
    )

    assert entry["focus"] == "Structural probing"
    assert entry["dataset_url"] == "https://huggingface.co/datasets/example/smoke"


async def test_a_declared_focus_and_dataset_link_reach_the_detail_resource() -> None:
    benchmark = _benchmark(
        focus="Structural probing",
        dataset_url="https://huggingface.co/datasets/example/smoke",
    )

    resource = benchmark.resource(1)

    assert resource["focus"] == "Structural probing"
    assert resource["dataset_url"] == "https://huggingface.co/datasets/example/smoke"


async def test_a_benchmark_declaring_neither_publishes_neither_key() -> None:
    # INVARIANT: absent display metadata is an absent key, never a null. A seeded row's
    # focus/dataset columns are then left untouched rather than blanked by a null.
    entry = await _catalog(_benchmark())

    assert "focus" not in entry
    assert "dataset_url" not in entry


@pytest.mark.parametrize("blank", ["", "   "])
async def test_a_blank_focus_line_is_refused(blank: str) -> None:
    with pytest.raises(ValueError, match="focus"):
        _benchmark(focus=blank)


@pytest.mark.parametrize(
    "reference",
    ["/datasets/example", "huggingface.co/datasets/example", "ftp://example.invalid/x", ""],
)
async def test_a_dataset_link_that_is_not_an_absolute_web_url_is_refused(reference: str) -> None:
    with pytest.raises(ValueError, match="dataset_url"):
        _benchmark(dataset_url=reference)


async def test_every_installed_benchmark_publishes_a_focus_line() -> None:
    # STORY: the portal's "Focus" column is filled from the Engine, not hand-copied into a chart.
    assert {benchmark.id: benchmark.focus for benchmark in BUILTIN_BENCHMARKS} == {
        "draco": "Research reports with citations",
        # Same dataset and subject as the canonical board — the judge-pass count is the only
        # thing that separates them, so that is what a reader needs in the Focus column.
        "draco-3pass": "Research reports, three judge passes",
        # The two HealthBench boards share a dataset, so their focus lines have to separate
        # them at a glance — that is the only place a reader sees the difference.
        "healthbench-professional": "Clinical safety, full official exam",
        "healthbench-worst30": "Clinical safety, hardest cases",
        "ifeval": "Instruction following",
    }


async def test_only_the_benchmarks_with_a_public_dataset_publish_a_link() -> None:
    # WHY IFEval has none: its dataset is vendored inside the Engine
    # (screamingface_engine.benchmarks.ifeval.vendor), so no single public URL is authoritative.
    assert {benchmark.id: benchmark.dataset_url for benchmark in BUILTIN_BENCHMARKS} == {
        "draco": "https://huggingface.co/datasets/perplexity-ai/draco",
        "draco-3pass": "https://huggingface.co/datasets/perplexity-ai/draco",
        "healthbench-professional": "https://huggingface.co/datasets/openai/healthbench",
        "healthbench-worst30": "https://huggingface.co/datasets/openai/healthbench",
        "ifeval": None,
    }


async def test_the_catalog_publishes_the_computed_revision_untouched_by_display_metadata() -> None:
    # INVARIANT: a submission carries the Engine's revision and the board ranks per revision, so
    # a revision that moves makes every already-recorded submission look incomparable. `revision`
    # is computed from dataset and protocol constants; editorial text must never reach it, and
    # the wire value must be that computed value rather than anything derived from metadata.
    entry = await _catalog(
        _benchmark(focus="Structural probing", dataset_url="https://example.test/dataset")
    )
    plain = await _catalog(_benchmark())

    assert entry["revision"] == plain["revision"] == "example-smoke-v1"


async def test_the_catalog_publishes_every_installed_benchmarks_own_revision() -> None:
    # AIDEV-NOTE: deliberately NOT a table of literal hashes. Pinning them here would recreate
    # the very failure OME-904 removes — a hand-copied second copy that silently goes stale.
    # The board no longer holds its own copy either: it seeds `revision` straight from this
    # catalogue response.
    for benchmark in BUILTIN_BENCHMARKS:
        entry = await _catalog(benchmark)
        assert entry["revision"] == benchmark.revision
        assert entry["revision"]
