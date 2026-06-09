from uuid import uuid4

from tortoise import fields, migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    dependencies = [("models", "0004_gemini_credential_locator")]

    operations = [
        ops.AddField(
            model_name="CredentialBlob",
            name="ciphertext_version",
            field=fields.CharField(default="v1", max_length=16, null=True),
        ),
        ops.CreateModel(
            name="SecretMasterKey",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("provider", fields.CharField(max_length=32)),
                ("key_material", fields.TextField()),
                ("version", fields.CharField(default="v1", max_length=16)),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
            ],
            options={
                "table": "secret_master_keys",
                "app": "models",
                "pk_attr": "id",
                "unique_together": (("provider", "version"),),
            },
            bases=["Model"],
        ),
    ]
