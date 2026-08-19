from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [
        ("models", "0006_benchmark_native_scores"),
    ]

    initial = False

    # FEATURE: OME-874 — the portal catalogue gains a "Focus" column: one editorial line saying
    # what a benchmark is actually about, so a visitor can pick one without opening it.
    #
    # WHY nullable and NOT backfilled: this is copy someone writes, not a value derived from the
    # Engine, so there is no correct default to invent. An unset benchmark renders an em dash.
    # Same shape as `revision` in 0004 (OME-775).
    #
    # AIDEV-NOTE: unlike 0005 and 0006, this migration is SAFE for a rolling multi-replica
    # rollout — adding a nullable column leaves every query the old pods are running valid.
    # No maintenance window needed. See "Breaking migrations and multi-replica rollouts" in
    # apps/scoreboard/DEPLOYMENT.md for the ones that do.

    operations = [
        ops.AddField(
            model_name="Benchmark",
            name="focus",
            field=fields.CharField(max_length=120, null=True),
        ),
    ]
