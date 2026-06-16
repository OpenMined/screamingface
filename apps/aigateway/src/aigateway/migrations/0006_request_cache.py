from uuid import uuid4

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0005_secret_store")]

    operations = [
        ops.CreateModel(
            name="RequestCacheEntry",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("key_hash", fields.CharField(unique=True, db_index=True, max_length=64)),
                ("key_version", fields.CharField(max_length=32)),
                ("account_id", fields.CharField(db_index=True, max_length=64)),
                ("profile_name", fields.CharField(db_index=True, max_length=128)),
                ("prompt_hash", fields.CharField(db_index=True, max_length=64)),
                ("provider", fields.CharField(db_index=True, max_length=64)),
                ("model", fields.CharField(db_index=True, max_length=255)),
                ("response_ciphertext", fields.TextField()),
                ("response_size_bytes", fields.IntField()),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ("expires_at", fields.DatetimeField(db_index=True)),
                (
                    "last_hit_at",
                    fields.DatetimeField(null=True, auto_now=False, auto_now_add=False),
                ),
                ("hit_count", fields.IntField(default=0)),
            ],
            options={
                "table": "request_cache_entries",
                "app": "models",
                "pk_attr": "id",
                "indexes": (("account_id", "profile_name", "provider", "expires_at"),),
            },
            bases=["Model"],
        ),
    ]
