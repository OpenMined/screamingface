from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .config import Settings
from .db import close_db, init_db
from .scores.schemas import BenchmarkSchema
from .scores.store import ScoreStore

SEED_BENCHMARKS_ENV = "SCOREBOARD_SEED_BENCHMARKS_JSON"


class SeedBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    dataset_url: str | None = None
    # INVARIANT: must match the Engine benchmark's computed REVISION exactly — a submission
    # carries the Engine's value, and the two are compared for comparability (OME-775).
    # Optional because the retained legacy demo entries have no Engine revision.
    revision: str | None = Field(default=None, max_length=64)


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


async def seed_benchmarks(benchmarks: Sequence[SeedBenchmark]) -> list[BenchmarkSchema]:
    store = ScoreStore()
    seeded: list[BenchmarkSchema] = []
    for benchmark in benchmarks:
        seeded.append(
            await store.register_benchmark(
                benchmark_id=benchmark.id,
                display_name=benchmark.display_name,
                description=benchmark.description,
                dataset_url=benchmark.dataset_url,
                revision=benchmark.revision,
            )
        )
    return seeded


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed scoreboard benchmark definitions.")
    parser.add_argument(
        "--benchmarks-json",
        default=None,
        help=f"JSON benchmark list. Defaults to ${SEED_BENCHMARKS_ENV}; empty list if unset.",
    )
    return parser


async def _run(raw_json: str) -> None:
    benchmarks = load_benchmarks_json(raw_json)
    if not benchmarks:
        print("no benchmarks configured")
        return

    settings = Settings()
    await init_db(settings.database_url)
    try:
        seeded = await seed_benchmarks(benchmarks)
        for benchmark in seeded:
            print(f"seeded benchmark {benchmark.id}")
    finally:
        await close_db()


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw_json = args.benchmarks_json or os.getenv(SEED_BENCHMARKS_ENV, "[]")
    try:
        asyncio.run(_run(raw_json))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
