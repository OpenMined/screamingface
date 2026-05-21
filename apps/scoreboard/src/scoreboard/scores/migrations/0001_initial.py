import functools
from json import dumps, loads
from uuid import uuid4

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name="Benchmark",
            fields=[
                (
                    "id",
                    fields.CharField(primary_key=True, unique=True, db_index=True, max_length=64),
                ),
                ("display_name", fields.CharField(max_length=255)),
                ("description", fields.TextField(null=True, unique=False)),
                ("dataset_url", fields.CharField(null=True, max_length=2048)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={"table": "benchmarks", "app": "models", "pk_attr": "id"},
            bases=["BaseBenchmark"],
        ),
        ops.CreateModel(
            name="Score",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("version", fields.IntField(default=1)),
                ("spec_id", fields.CharField(db_index=True, max_length=255)),
                ("url4_expression", fields.TextField(unique=False)),
                ("submitted_by", fields.CharField(null=True, max_length=255)),
                ("submitted_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("accuracy", fields.FloatField()),
                ("total_questions", fields.IntField()),
                ("correct_questions", fields.IntField()),
                (
                    "ran_with_providers",
                    fields.JSONField(
                        encoder=functools.partial(dumps, separators=(",", ":")), decoder=loads
                    ),
                ),
                (
                    "ran_at_local",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                ("client_name", fields.CharField(null=True, max_length=128)),
                ("client_version", fields.CharField(null=True, max_length=64)),
                ("client_platform", fields.CharField(null=True, max_length=32)),
                ("verified_by_openmined", fields.BooleanField(default=False)),
                (
                    "metadata",
                    fields.JSONField(
                        null=True,
                        encoder=functools.partial(dumps, separators=(",", ":")),
                        decoder=loads,
                    ),
                ),
                (
                    "benchmark",
                    fields.ForeignKeyField(
                        "models.Benchmark",
                        source_field="benchmark_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="scores",
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={
                "table": "scores",
                "app": "models",
                "indexes": [
                    Index(fields=["benchmark_id", "accuracy"]),
                    Index(fields=["benchmark_id", "spec_id", "submitted_at"]),
                ],
                "pk_attr": "id",
            },
            bases=["BaseScore"],
        ),
        ops.CreateModel(
            name="IdempotencyKey",
            fields=[
                (
                    "key",
                    fields.CharField(primary_key=True, unique=True, db_index=True, max_length=255),
                ),
                (
                    "expires_at",
                    fields.DatetimeField(db_index=True, auto_now=False, auto_now_add=False),
                ),
                (
                    "score",
                    fields.ForeignKeyField(
                        "models.Score",
                        source_field="score_id",
                        db_constraint=True,
                        to_field="id",
                        related_name="idempotency_keys",
                        on_delete=OnDelete.CASCADE,
                    ),
                ),
            ],
            options={"table": "idempotency_keys", "app": "models", "pk_attr": "key"},
            bases=["BaseIdempotencyKey"],
        ),
    ]
