from uuid import uuid4

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name="Account",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("username", fields.CharField(unique=True, db_index=True, max_length=64)),
                ("password_hash", fields.CharField(max_length=255)),
                ("display_name", fields.CharField(null=True, max_length=255)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                (
                    "last_login_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                ("is_active", fields.BooleanField(default=True)),
            ],
            options={"table": "accounts", "app": "models", "pk_attr": "id"},
            bases=["Model"],
        ),
    ]
