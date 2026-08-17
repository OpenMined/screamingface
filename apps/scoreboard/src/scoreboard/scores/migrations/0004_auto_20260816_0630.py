from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0003_auto_20260713_1505")]

    initial = False

    operations = [
        # WHY both are nullable with no backfill: the retained legacy demo benchmarks have no
        # Engine revision, and every pre-existing score genuinely ran before revisions were
        # recorded — inventing a value would assert something false about what was measured
        # (OME-775 D4).
        ops.AddField(
            model_name="Benchmark",
            name="revision",
            field=fields.CharField(null=True, max_length=64),
        ),
        ops.AddField(
            model_name="Score",
            name="benchmark_revision",
            field=fields.CharField(null=True, db_index=True, max_length=64),
        ),
    ]
