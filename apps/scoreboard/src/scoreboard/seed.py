from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .config import Settings
from .db import close_db, init_db
from .scores.models import Baseline, Benchmark, Score
from .scores.schemas import BenchmarkSchema
from .scores.store import ScoreStore

SEED_BENCHMARKS_ENV = "SCOREBOARD_SEED_BENCHMARKS_JSON"


class SeedBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    dataset_url: str | None = None


_BENCHMARKS_ADAPTER = TypeAdapter(list[SeedBenchmark])


def load_benchmarks_json(raw_json: str) -> list[SeedBenchmark]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid benchmark seed JSON: {exc.msg}") from exc

    try:
        return _BENCHMARKS_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid benchmark seed payload: {exc}") from exc


async def seed_benchmarks(
    benchmarks: Sequence[SeedBenchmark],
    *,
    exact: bool = False,
) -> list[BenchmarkSchema]:
    if exact:
        await _remove_unseeded_benchmarks(frozenset(benchmark.id for benchmark in benchmarks))
    store = ScoreStore()
    seeded: list[BenchmarkSchema] = []
    for benchmark in benchmarks:
        seeded.append(
            await store.register_benchmark(
                benchmark_id=benchmark.id,
                display_name=benchmark.display_name,
                description=benchmark.description,
                dataset_url=benchmark.dataset_url,
            )
        )
    return seeded


async def _remove_unseeded_benchmarks(selected_ids: frozenset[str]) -> None:
    """Remove only empty registrations omitted from an explicitly exact seed."""

    stale_ids = tuple(
        await Benchmark.exclude(id__in=selected_ids).order_by("id").values_list("id", flat=True)
    )
    if not stale_ids:
        return
    has_scores = await Score.filter(benchmark_id__in=stale_ids).exists()
    has_baselines = await Baseline.filter(benchmark_id__in=stale_ids).exists()
    if has_scores or has_baselines:
        joined = ", ".join(repr(value) for value in stale_ids)
        raise ValueError(
            f"cannot remove unseeded benchmarks with stored results: {joined}; "
            "use a fresh local Scoreboard database or migrate those results explicitly"
        )
    await Benchmark.filter(id__in=stale_ids).delete()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed scoreboard benchmark definitions.")
    parser.add_argument(
        "--benchmarks-json",
        default=None,
        help=f"JSON benchmark list. Defaults to ${SEED_BENCHMARKS_ENV}; empty list if unset.",
    )
    parser.add_argument(
        "--exact",
        action="store_true",
        help="Remove unseeded benchmark registrations when they have no stored results.",
    )
    return parser


async def _run(raw_json: str, *, exact: bool) -> None:
    benchmarks = load_benchmarks_json(raw_json)
    if not benchmarks:
        print("no benchmarks configured")
        return

    settings = Settings()
    await init_db(settings.database_url)
    try:
        seeded = await seed_benchmarks(benchmarks, exact=exact)
        for benchmark in seeded:
            print(f"seeded benchmark {benchmark.id}")
    finally:
        await close_db()


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw_json = args.benchmarks_json or os.getenv(SEED_BENCHMARKS_ENV, "[]")
    try:
        asyncio.run(_run(raw_json, exact=args.exact))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
