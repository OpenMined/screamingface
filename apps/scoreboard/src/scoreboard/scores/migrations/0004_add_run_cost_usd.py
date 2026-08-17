from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0003_auto_20260713_1505")]

    initial = False

    operations = [
        ops.AddField(
            model_name="Score",
            name="run_cost_usd",
            field=fields.DecimalField(null=True, max_digits=12, decimal_places=6),
        ),
    ]
