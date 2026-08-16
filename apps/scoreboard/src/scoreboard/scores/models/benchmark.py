from __future__ import annotations

from tortoise import fields

from .base import BaseScoreboardModel


class BaseBenchmark(BaseScoreboardModel):
    class Meta:
        abstract = True

    id = fields.CharField(max_length=64, primary_key=True)
    display_name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    dataset_url = fields.CharField(max_length=2048, null=True)
    # INVARIANT: mirrors the Engine benchmark's immutable REVISION — a sha256 over its
    # dataset + protocol (+ verifier) revisions. It identifies *what was measured*, so two
    # revisions of one benchmark are not comparable results (OME-775).
    # WHY nullable: the retained legacy demo entries (hle/livetruth/livetruth-latest) have no
    # Engine revision, so this column is added without a backfill.
    revision = fields.CharField(max_length=64, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)


class Benchmark(BaseBenchmark):
    class Meta:
        table = "benchmarks"
