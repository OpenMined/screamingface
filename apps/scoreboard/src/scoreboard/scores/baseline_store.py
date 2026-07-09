from __future__ import annotations

from typing import cast

from .models import Baseline, Benchmark
from .schemas import BaselineImportRow, BaselineSchema


def _baseline_to_schema(model: Baseline) -> BaselineSchema:
    return BaselineSchema(
        id=model.id,
        benchmark_id=cast(str, getattr(model, "benchmark_id")),
        model_name=model.model_name,
        accuracy=model.accuracy,
        source=model.source,
        source_url=model.source_url,
        imported_at=model.imported_at,
        metadata=model.metadata,
    )


class BaselineStore:
    """Persistence for imported single-model baselines ('line to beat').

    # WHY: a separate store (not folded into ScoreStore) because a Baseline is a
    # distinct concept from a community Score submission — no url4_expression, no
    # provider info, no correctness counts. Community and baseline rows never share
    # a table.
    """

    async def import_baseline(self, row: BaselineImportRow) -> BaselineSchema:
        # INVARIANT: a baseline can only be imported against a benchmark that already
        # exists, mirroring the check the /v1/scores route performs before ScoreStore
        # sees a submission (see routes/scores.py::submit_score).
        if not await Benchmark.exists(id=row.benchmark_id):
            raise ValueError(f"unknown benchmark_id: {row.benchmark_id!r}")

        baseline, _ = await Baseline.update_or_create(
            benchmark_id=row.benchmark_id,
            model_name=row.model_name,
            source=row.source,
            defaults={
                "accuracy": row.accuracy,
                "source_url": row.source_url,
                "metadata": row.metadata,
            },
        )
        return _baseline_to_schema(baseline)

    async def list_baselines(self, benchmark_id: str) -> list[BaselineSchema]:
        rows = await Baseline.filter(benchmark_id=benchmark_id).order_by("-accuracy")
        return [_baseline_to_schema(baseline) for baseline in rows]
