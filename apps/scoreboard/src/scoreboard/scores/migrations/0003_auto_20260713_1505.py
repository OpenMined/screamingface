from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0002_auto_20260709_1350")]

    initial = False

    operations = [
        ops.AddField(
            model_name="Score",
            name="content_hash",
            field=fields.CharField(null=True, unique=True, max_length=64),
        ),
    ]
