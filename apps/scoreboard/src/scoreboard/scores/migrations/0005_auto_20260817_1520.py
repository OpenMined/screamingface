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
