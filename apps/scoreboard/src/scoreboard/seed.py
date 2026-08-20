from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .config import Settings
from .db import close_db, init_db
from .scores.schemas import BenchmarkSchema
from .scores.store import ScoreStore

SEED_BENCHMARKS_ENV = "SCOREBOARD_SEED_BENCHMARKS_JSON"
# FEATURE: benchmark descriptions on the leaderboard (OME-904). The Engine's benchmark
# definitions are the ONLY place a benchmark's prose is written; this deployment names which
# Engine to ask, and nothing else. A values override can therefore change the Engine consulted
# but can no longer carry, alter, or omit the text itself.
ENGINE_URL_ENV = "SCOREBOARD_SEED_ENGINE_URL"
_CATALOG_PATH = "/v1/benchmarks"
# The catalogue is a small static document behind an ETag; a deploy hook should not hang on it.
_FETCH_TIMEOUT_SECONDS = 15.0


class EngineCatalogUnavailable(RuntimeError):
    """The Engine benchmark catalogue could not be read.

    INVARIANT: every transport, status, and payload failure surfaces as this one type. No
    `httpx` or `json` exception escapes this module, so a deploy log names the thing that
    failed rather than leaking a library's internals.
    """


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
    # Short editorial line for the portal catalogue's "Focus" column (OME-874). Optional: it is
    # copy someone writes, not a value the Engine derives.
    focus: str | None = Field(default=None, max_length=120)


class _CatalogEntry(BaseModel):
    """One benchmark as the Engine publishes it at ``GET /v1/benchmarks``.

    AIDEV-NOTE: ``extra="ignore"`` deliberately, opposite to :class:`SeedBenchmark`'s
    ``extra="forbid"``. A configured entry is written by hand here, so a typo must fail the
    deploy; the catalogue is written by another service that will keep growing fields
    (``case_count``, ``href``, ``check_surface``, whatever comes next), and a board that
    refuses to seed because the Engine added a field is a board that breaks on someone else's
    release. Read the fields the board displays; ignore the rest.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    revision: str = Field(min_length=1, max_length=64)
    focus: str | None = Field(default=None, max_length=120)
    dataset_url: str | None = None

    def as_seed(self) -> SeedBenchmark:
        # The Engine calls it `title`; this board's column is `display_name`. One mapping site.
        return SeedBenchmark(
            id=self.id,
            display_name=self.title,
            description=self.description,
            dataset_url=self.dataset_url,
            revision=self.revision,
            focus=self.focus,
        )


class _Catalog(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[_CatalogEntry]


@dataclass(slots=True)
class SeedReport:
    """What one seeding pass did, in the terms the deploy log and its exit code need."""

    seeded: list[BenchmarkSchema] = field(default_factory=list)
    """Rows written this pass, Engine-published first."""

    shadowed: list[str] = field(default_factory=list)
    """Configured ids the Engine also publishes; the configured copy was ignored."""

    engine_error: str | None = None
    """Why the catalogue could not be read, when it could not."""

    bootstrap_failed: bool = False
    """The catalogue was unreadable AND this board has never been seeded from one."""


def fetch_engine_benchmarks(
    engine_url: str,
    *,
    client: httpx.Client | None = None,
) -> list[SeedBenchmark]:
    """Read the Engine's benchmark catalogue and return it as rows this board can register.

    Think of it as copying a menu from the kitchen that cooks the food, rather than retyping
    it at the front desk: the Engine defines each benchmark and writes the words describing
    it, and this function carries those words across unchanged.

    Stage 1 — address the catalogue: ``{engine_url}/v1/benchmarks``. Public and read-only, so
    the seed job holds no Engine credential.
    Stage 2 — fetch it, converting every transport failure, error status, and non-JSON body
    into :class:`EngineCatalogUnavailable`.
    Stage 3 — validate the payload, ignoring fields this board does not display.
    Stage 4 — map each entry onto a seed row, renaming ``title`` to ``display_name``.

    Args:
        engine_url: origin of the Engine to ask, with or without a trailing slash.
        client: an HTTP client to use instead of opening one — the injection seam the tests
            drive; production passes nothing and gets a timeout-bounded client.

    Returns:
        One row per published benchmark, in the Engine's own order.

    Raises:
        EngineCatalogUnavailable: the catalogue could not be read or could not be understood.
    """

    url = engine_url.rstrip("/") + _CATALOG_PATH
    http = client if client is not None else httpx.Client(timeout=_FETCH_TIMEOUT_SECONDS)
    try:
        response = http.get(url)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise EngineCatalogUnavailable(f"{url} answered HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise EngineCatalogUnavailable(f"{url} could not be reached: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise EngineCatalogUnavailable(f"{url} did not answer JSON: {exc.msg}") from exc
    finally:
        if client is None:
            http.close()

    try:
        catalog = _Catalog.model_validate(payload)
    except ValidationError as exc:
        raise EngineCatalogUnavailable(f"{url} answered an unreadable catalog: {exc}") from exc
    return [entry.as_seed() for entry in catalog.data]


async def seed_from_sources(
    *,
    engine_url: str | None,
    configured: Sequence[SeedBenchmark],
    client: httpx.Client | None = None,
) -> SeedReport:
    """Register every benchmark this board should show, with the Engine as the only copy.

    Think of it as a merge with a fixed winner: whatever the Engine publishes is the truth,
    and configuration may only fill gaps the Engine leaves.

    Stage 1 — read the Engine catalogue when one is configured. A failure here is recorded,
    not raised: re-seeding refreshes a populated board, so failing a Scoreboard deploy on an
    unrelated service's health would cost availability and buy nothing.
    Stage 2 — Engine rows win over any configured entry sharing their id, and the shadowed ids
    are reported. This precedence is what makes the Engine the ONLY copy rather than merely
    the preferred one — prose reintroduced by a deploy is ignored rather than applied.
    Stage 3 — write every row through the same idempotent registration as before.
    Stage 4 — decide whether an unreadable catalogue was survivable. It was, unless no row in
    the database carries a revision at all: only Engine-published benchmarks carry one, so
    that case means no successful seed has ever run, and exiting zero would publish a board
    holding nothing but legacy demo entries and call it a success.

    Args:
        engine_url: the Engine to read, or None for a deployment that runs without one.
        configured: entries from deployment configuration — the retained legacy demos, plus
            anything the Engine does not publish.
        client: an HTTP client to use instead of opening one (see
            :func:`fetch_engine_benchmarks`).

    Returns:
        A :class:`SeedReport`; ``bootstrap_failed`` is the caller's non-zero exit signal.
    """

    report = SeedReport()
    engine_rows: list[SeedBenchmark] = []
    if engine_url:
        try:
            engine_rows = fetch_engine_benchmarks(engine_url, client=client)
        except EngineCatalogUnavailable as exc:
            report.engine_error = str(exc)

    published = {row.id for row in engine_rows}
    report.shadowed = sorted(row.id for row in configured if row.id in published)
    merged = [*engine_rows, *(row for row in configured if row.id not in published)]

    report.seeded = await seed_benchmarks(merged)
    report.bootstrap_failed = (
        report.engine_error is not None and not await ScoreStore().has_registered_revision()
    )
    return report


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
                focus=benchmark.focus,
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
    parser.add_argument(
        "--engine-url",
        default=None,
        help=(
            "Engine origin whose benchmark catalog supplies every published benchmark's text. "
            f"Defaults to ${ENGINE_URL_ENV}; omitted means seed configured entries only."
        ),
    )
    return parser


async def _run(raw_json: str, engine_url: str | None) -> int:
    configured = load_benchmarks_json(raw_json)
    if not configured and not engine_url:
        print("no benchmarks configured")
        return 0

    settings = Settings()
    await init_db(settings.database_url)
    try:
        report = await seed_from_sources(engine_url=engine_url, configured=configured)
        for benchmark in report.seeded:
            print(f"seeded benchmark {benchmark.id}")
        for benchmark_id in report.shadowed:
            # Named rather than silent: an operator who added prose to the deploy values needs
            # to know it was ignored, and where the text they see actually comes from.
            print(f"ignored configured entry {benchmark_id}: the Engine publishes it")
        if report.engine_error is not None:
            print(f"engine catalog unavailable: {report.engine_error}")
        if report.bootstrap_failed:
            print("no benchmark carries an Engine revision: this board has never been seeded")
            return 1
    finally:
        await close_db()
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw_json = args.benchmarks_json or os.getenv(SEED_BENCHMARKS_ENV, "[]")
    engine_url = args.engine_url or os.getenv(ENGINE_URL_ENV) or None
    try:
        exit_code = asyncio.run(_run(raw_json, engine_url))
    except ValueError as exc:
        parser.error(str(exc))
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
