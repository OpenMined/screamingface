from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence

from pydantic import TypeAdapter, ValidationError

from .config import Settings
from .db import close_db, init_db
from .scores.baseline_store import BaselineStore
from .scores.schemas import BaselineImportRow, BaselineSchema

SEED_BASELINES_ENV = "SCOREBOARD_SEED_BASELINES_JSON"

_BASELINES_ADAPTER = TypeAdapter(list[BaselineImportRow])


def load_baselines_json(raw_json: str) -> list[BaselineImportRow]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid baseline import JSON: {exc.msg}") from exc

    try:
        return _BASELINES_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid baseline import payload: {exc}") from exc


async def import_baselines(rows: Sequence[BaselineImportRow]) -> list[BaselineSchema]:
    store = BaselineStore()
    imported: list[BaselineSchema] = []
    for row in rows:
        imported.append(await store.import_baseline(row))
    return imported


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import scoreboard single-model baselines.")
    parser.add_argument(
        "--baselines-json",
        default=None,
        help=f"JSON baseline list. Defaults to ${SEED_BASELINES_ENV}; empty list if unset.",
    )
    return parser


async def _run(raw_json: str) -> None:
    rows = load_baselines_json(raw_json)
    if not rows:
        print("no baselines configured")
        return

    settings = Settings()
    await init_db(settings.database_url)
    try:
        imported = await import_baselines(rows)
        for baseline in imported:
            print(f"imported baseline {baseline.model_name} for {baseline.benchmark_id}")
    finally:
        await close_db()


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    raw_json = args.baselines_json or os.getenv(SEED_BASELINES_ENV, "[]")
    try:
        asyncio.run(_run(raw_json))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
