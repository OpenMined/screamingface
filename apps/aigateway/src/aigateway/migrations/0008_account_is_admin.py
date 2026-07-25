from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0007_connection_auth_type")]

    operations = [
        ops.AddField(
            model_name="Account",
            name="is_admin",
            field=fields.BooleanField(default=False, db_default="false"),
        ),
    ]
