from uuid import uuid4

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0002_oauth_connections")]

    operations = [
        ops.CreateModel(
            name="CredentialBlob",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("service", fields.CharField(db_index=True, max_length=255)),
                ("account", fields.CharField(db_index=True, max_length=255)),
                ("value", fields.TextField()),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
            ],
            options={
                "table": "credential_blobs",
                "app": "models",
                "pk_attr": "id",
                "unique_together": (("service", "account"),),
            },
            bases=["Model"],
        ),
    ]
