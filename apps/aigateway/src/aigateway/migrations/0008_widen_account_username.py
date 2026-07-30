"""Widen `accounts.username` from 64 to 255 characters.

A Cloudflare-identified caller's account is keyed on its username, and that username IS the verified
email address (`core/auth/cloudflare_identity.py`). RFC 5321 allows an address up to 254 characters,
so a 64-character column silently caps what can be stored. SQLite ignores `VARCHAR` length while
Postgres enforces it, so without this the failure would appear only in a hosted deployment, as a 500
on account creation for a caller who did nothing wrong.

WHY a custom operation instead of the declarative `ops.AlterField`:

SQLite cannot widen a column in place, so Tortoise's SQLite editor rebuilds the table —
`CREATE TABLE new__accounts` … `DROP TABLE accounts` … `RENAME`. `oauth_connections.account_id`
references `accounts` with `ON DELETE CASCADE`, so that `DROP` **deletes every OAuth connection in
the database**. `test_full_chain_applies_to_populated_database` catches it: the connection row
seeded before the upgrade is gone afterwards.

And the rebuild buys nothing, because SQLite does not enforce `VARCHAR(n)` at all — the column
already stores a 254-character address. So the correct DDL is genuinely dialect-specific: an `ALTER`
on Postgres, nothing on SQLite. This is not a workaround for the cascade; the cascade is what
exposed that the SQLite branch never needed DDL in the first place.

WHY it is not `ops.RunPython` either — the trap that shape leaves behind:

`RunPython` contributes no state change, so Tortoise's projected migration state would keep
recording `max_length=64` while the model declares 255. Nothing reads that state at runtime, but the
autodetector does: `makemigrations` would then propose the very `AlterField(Account.username)` this
migration exists to avoid, and applying that generated migration to a populated SQLite database
performs the table rebuild and the cascading delete described above. A future maintainer accepting
routine autodetector output would destroy data, with nothing in the diff to warn them.

So the operation splits the two halves that `AlterField` normally couples: it keeps `AlterField`'s
`state_forward` — which is what makes the projected state agree with the model and keeps the
autodetector quiet (`test_autodetector_proposes_no_account_change`) — and replaces only the
database half with the dialect guard.
"""

from tortoise import fields, migrations
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor.base import BaseSchemaEditor
from tortoise.migrations.schema_generator.state import State

_POSTGRES_DIALECTS = frozenset({"postgres", "postgresql", "asyncpg", "psycopg"})

_NARROW = 64
_WIDE = 255


async def _alter(schema_editor: BaseSchemaEditor | None, width: int) -> None:
    """Runs the widening on Postgres only; every other dialect is left untouched."""
    if schema_editor is None:
        return
    dialect = getattr(getattr(schema_editor, "client", None), "capabilities", None)
    dialect_name = getattr(dialect, "dialect", "") or ""
    if dialect_name.lower() not in _POSTGRES_DIALECTS:
        return
    await schema_editor._run_sql(  # noqa: SLF001 - the editor exposes no public raw-SQL entry point
        f'ALTER TABLE "accounts" ALTER COLUMN "username" TYPE VARCHAR({width})'
    )


class WidenUsername(ops.AlterField):
    """`AlterField`'s projected state, but DDL only on the dialect that needs it."""

    def __init__(self) -> None:
        # Mirrors `BaseAccount.username` exactly — any drift here re-arms the autodetector.
        super().__init__(
            model_name="Account",
            name="username",
            field=fields.CharField(unique=True, db_index=True, max_length=_WIDE),
        )

    async def database_forward(
        self,
        app_label: str,
        old_state: State,
        new_state: State,
        state_editor: BaseSchemaEditor | None = None,
    ) -> None:
        await _alter(state_editor, _WIDE)

    async def database_backward(
        self,
        app_label: str,
        old_state: State,
        new_state: State,
        state_editor: BaseSchemaEditor | None = None,
    ) -> None:
        """Narrowing is lossy by definition — it fails on Postgres if any stored address exceeds 64.

        Left as the honest inverse rather than a silent truncation: a rollback that quietly rewrote
        people's usernames would detach them from their stored credentials.
        """
        await _alter(state_editor, _NARROW)


class Migration(migrations.Migration):
    dependencies = [("models", "0007_connection_auth_type")]

    operations = [WidenUsername()]
