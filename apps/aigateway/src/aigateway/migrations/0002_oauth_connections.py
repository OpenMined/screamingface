from uuid import uuid4

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0001_initial_accounts")]

    operations = [
        ops.CreateModel(
            name="OAuthConnection",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("provider", fields.CharField(db_index=True, max_length=64)),
                ("label", fields.CharField(max_length=255)),
                ("status", fields.CharField(db_index=True, max_length=32)),
                ("identity_sub", fields.CharField(null=True, max_length=255)),
                ("identity_email", fields.CharField(null=True, max_length=320)),
                ("identity_name", fields.CharField(null=True, max_length=255)),
                ("identity_raw", fields.JSONField(null=True)),
                ("credential_locator", fields.JSONField()),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                (
                    "last_used_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                (
                    "last_refreshed_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                ("error_message", fields.TextField(null=True)),
                (
                    "account",
                    fields.ForeignKeyField(
                        "models.Account",
                        related_name="oauth_connections",
                        on_delete=fields.OnDelete.CASCADE,
                    ),
                ),
            ],
            options={
                "table": "oauth_connections",
                "app": "models",
                "pk_attr": "id",
                "unique_together": (
                    ("account_id", "provider", "identity_sub"),
                    ("account_id", "provider", "label"),
                ),
            },
            bases=["Model"],
        ),
    ]
