from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0003_auto_20260713_1505")]

    initial = False

    operations = [
        ops.AddField(
            model_name="Score",
            name="openness_override",
            field=fields.CharField(null=True, max_length=8),
        ),
        ops.AddField(
            model_name="Baseline",
            name="openness_override",
            field=fields.CharField(null=True, max_length=8),
        ),
    ]
