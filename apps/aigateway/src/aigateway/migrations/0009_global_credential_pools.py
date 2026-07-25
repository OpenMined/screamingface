from uuid import uuid4

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0008_account_is_admin")]

    operations = [
        ops.CreateModel(
            name="GlobalCredentialPool",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("provider", fields.CharField(db_index=True, max_length=64)),
                (
                    "label",
                    fields.CharField(max_length=255, default="default", db_default="default"),
                ),
                (
                    "auth_type",
                    fields.CharField(max_length=16, default="api_key", db_default="api_key"),
                ),
                ("is_active", fields.BooleanField(default=True, db_default="true")),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
                (
                    "created_by",
                    fields.ForeignKeyField(
                        "models.Account",
                        related_name="created_credential_pools",
                        on_delete=fields.OnDelete.RESTRICT,
                    ),
                ),
            ],
            options={
                "table": "global_credential_pools",
                "app": "models",
                "pk_attr": "id",
                "unique_together": (("provider", "label"),),
            },
            bases=["Model"],
        ),
    ]
