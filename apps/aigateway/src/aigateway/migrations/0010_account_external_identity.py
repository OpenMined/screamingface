from tortoise import fields, migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops
from tortoise.migrations.constraints import UniqueConstraint


def _sqlite_foreign_keys(enabled: bool):
    """Toggle SQLite FK enforcement around the `accounts` table rebuild.

    WHY this exists at all: SQLite cannot ALTER a column's nullability, so
    Tortoise's schema editor rebuilds the table — CREATE new / INSERT SELECT /
    **DROP TABLE accounts** / RENAME (`schema_editor/sqlite.py::_remake_table`).
    That DROP has no FK guard, so with `PRAGMA foreign_keys=ON` (Tortoise's
    default) it fires ON DELETE CASCADE on every child row: `oauth_connections`
    and `global_credential_pools` are silently emptied by a migration that
    reports OK.

    INVARIANT: no migration may destroy user data. Verified by
    `test_full_chain_applies_to_populated_database`, which keeps an
    oauth_connections row across this upgrade.

    AIDEV-NOTE: SQLite-only, by dialect check — `PRAGMA` is a syntax error on
    Postgres, which needs none of this (it does a real ALTER COLUMN DROP NOT
    NULL and never rebuilds the table).
    """

    async def _run(_apps, schema_editor) -> None:
        client = schema_editor.client
        if client.capabilities.dialect != "sqlite":
            return
        await client.execute_script(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")

    return _run


class Migration(migrations.Migration):
    """Federated-identity columns on `accounts` (OME-590).

    `password_hash` goes NOT NULL -> NULL. That is a widening alteration, so
    existing local accounts keep their hash; NULL is reserved for accounts
    provisioned from an external IdP, and `login()` refuses it explicitly.
    """

    # INVARIANT: must stay False. `PRAGMA foreign_keys` is a silent no-op inside a
    # transaction, so the guard above only works on a non-atomic migration.
    atomic = False

    dependencies = [("models", "0009_global_credential_pools")]

    operations = [
        ops.RunPython(_sqlite_foreign_keys(False), _sqlite_foreign_keys(True)),
        ops.AlterField(
            model_name="Account",
            name="password_hash",
            field=fields.CharField(max_length=255, null=True),
        ),
        ops.AddField(
            model_name="Account",
            name="external_idp",
            field=fields.CharField(max_length=64, null=True),
        ),
        ops.AddField(
            model_name="Account",
            name="external_subject",
            field=fields.CharField(max_length=255, null=True),
        ),
        ops.AddField(
            model_name="Account",
            name="email",
            field=fields.CharField(max_length=320, null=True, db_index=True),
        ),
        # WHY a separate AddIndex: `db_index=True` on AddField updates model state
        # but emits no CREATE INDEX, so the column would be unindexed in every
        # migrated database while generate_schemas-built test databases had it.
        ops.AddIndex(
            model_name="Account",
            index=Index(fields=("email",), name="idx_accounts_email"),
        ),
        # WHY an explicit UniqueConstraint and not AlterModelOptions: the latter is
        # state-only (its `database_forward` returns None), so it would leave the
        # migrated database with NO constraint while the model claimed one.
        # OME-591's concurrent JIT provisioning depends on this being real.
        ops.AddConstraint(
            model_name="Account",
            constraint=UniqueConstraint(
                fields=("external_idp", "external_subject"),
                name="uid_accounts_external_identity",
            ),
        ),
        ops.RunPython(_sqlite_foreign_keys(True), _sqlite_foreign_keys(False)),
    ]
