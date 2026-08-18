from tortoise import fields, migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [
        ("models", "0005_auto_20260817_1520"),
    ]

    initial = False

    # FEATURE: OME-866 — benchmark-native Leaderboard scores. The submission contract
    # stops assuming binary accuracy: `accuracy` becomes `score` (any finite number,
    # higher is better within a benchmark) and `correct_questions` becomes nullable
    # because "correct" only means something for binary grading.
    #
    # AIDEV-NOTE: same multi-replica rollout caveat as 0005 — the migration Job is a
    # pre-upgrade hook, old pods query `accuracy` until the rollout finishes, and helm
    # rollback does not revert schema. Re-check the live row count before cutting a
    # scoreboard-v* tag (apps/scoreboard/DEPLOYMENT.md, "Breaking migrations").

    operations = [
        # The ranking partition index is rebuilt around the rename so its name never
        # refers to a column that no longer exists.
        ops.RemoveIndex(model_name="Score", fields=["benchmark_id", "accuracy"]),
        # INVARIANT: RENAMES, not drop-and-recreate — live IFEval rows keep the score
        # they were submitted with (their 0..1 values are already benchmark-native).
        ops.RenameField(
            model_name="Score",
            old_name="accuracy",
            new_name="score",
        ),
        ops.RenameField(
            model_name="Baseline",
            old_name="accuracy",
            new_name="score",
        ),
        # WHY nullable rather than dropped: existing binary-era rows keep their counts
        # (dropping would destroy data), while non-binary benchmarks submit nothing.
        ops.AlterField(
            model_name="Score",
            name="correct_questions",
            field=fields.IntField(null=True),
        ),
        ops.AddIndex(model_name="Score", index=Index(fields=["benchmark_id", "score"])),
    ]
