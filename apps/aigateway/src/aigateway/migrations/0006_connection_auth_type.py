from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0005_secret_store")]

    operations = [
        ops.AddField(
            model_name="OAuthConnection",
            name="auth_type",
            field=fields.CharField(default="oauth", db_default="oauth", max_length=16),
        ),
    ]
