from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    # WHY two parents: main carried two sibling 0004 migrations, both declaring 0003 —
    # 0004_auto_20260806_0000 (openness_override, OME-323) and 0004_auto_20260816_0630
    # (benchmark revision, OME-775) merged independently within minutes of each other.
    # Depending on both converges that branch so the next migration has one unambiguous
    # parent instead of an unresolved diamond.
    dependencies = [
        ("models", "0004_auto_20260806_0000"),
        ("models", "0004_auto_20260816_0630"),
    ]

    initial = False

    # AIDEV-NOTE: this is a BREAKING migration for a multi-replica rollout. The migration Job is a
    # pre-upgrade hook, so it completes before the Deployment rolls; production runs replicaCount 3,
    # and those old pods keep querying verified_by_openmined until the rollout finishes. /healthz
    # does not touch the database, so they stay in the Service while failing. helm rollback does not
    # revert schema, so the window is not recoverable that way.
    #
    # Shipped as a plain rename deliberately: dev runs a single replica, and production had no users
    # when this landed (4 demo rows from June, on benchmarks nothing queries). RE-CHECK THAT before
    # cutting a scoreboard-v* tag — see "Breaking migrations and multi-replica rollouts" in
    # apps/scoreboard/DEPLOYMENT.md for the two safe options.

    operations = [
        # INVARIANT: this RENAMES the column, it does not drop and recreate it. Existing
        # rows keep the value they were created with, which OME-820's D5 requires — rows
        # predating that ticket are genuinely unverified (some are local test
        # submissions), so losing or defaulting them would publish a claim about runs
        # nobody checked.
        ops.RenameField(
            model_name="Score",
            old_name="verified_by_openmined",
            new_name="verified_by_screamingface",
        ),
    ]
