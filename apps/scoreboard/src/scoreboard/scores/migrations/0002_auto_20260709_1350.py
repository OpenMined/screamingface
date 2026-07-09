import functools
from json import dumps, loads
from uuid import uuid4

from tortoise import fields, migrations
from tortoise.fields.base import OnDelete
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0001_initial")]

    initial = False

    operations = [
        ops.CreateModel(
            name="Baseline",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("model_name", fields.CharField(max_length=255)),
                ("accuracy", fields.FloatField()),
                ("source", fields.CharField(max_length=64)),
                ("source_url", fields.CharField(null=True, max_length=2048)),
                ("imported_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
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
                        related_name="baselines",
                        on_delete=OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={
                "table": "baselines",
                "app": "models",
                "unique_together": (("benchmark", "model_name", "source"),),
                "pk_attr": "id",
            },
            bases=["BaseBaseline"],
        ),
    ]
