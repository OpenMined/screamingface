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
    created_at = fields.DatetimeField(auto_now_add=True)


class Benchmark(BaseBenchmark):
    class Meta:
        table = "benchmarks"
