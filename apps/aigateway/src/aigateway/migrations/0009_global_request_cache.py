"""Make ``request_cache_entries.expires_at`` nullable for the global v2 cache (OME-305 §4.2).

V2 semantics are closed: every global row writes ``expires_at=NULL`` and never expires, so the
column has to accept NULL. Existing v1 rows keep the expiry they were written with.

WHY a custom operation instead of the bare declarative ``ops.AlterField``:

On Postgres the declarative path is already right — the base schema editor emits
``ALTER COLUMN "expires_at" DROP NOT NULL``, which touches no data and no index.

SQLite has no ``ALTER COLUMN`` at all, and unlike ``VARCHAR(n)`` (which it ignores — see 0008) it
DOES enforce ``NOT NULL``, so real DDL is unavoidable there. Tortoise's SQLite editor therefore
rebuilds the table: ``CREATE TABLE new__request_cache_entries`` … ``INSERT … SELECT`` … ``DROP
TABLE`` … ``RENAME``. Rows and column-level UNIQUE survive that; **standalone indexes do not**,
because they are separate ``CREATE INDEX`` objects that die with the dropped table and the rebuild
recreates none of them. Measured on a populated 0008 database, the bare operation left the table
with only its two implicit UNIQUE indexes — all seven single-column indexes and the composite
``(account_id, profile_name, provider, expires_at)`` were gone, silently turning every local
``key_hash`` lookup into a full scan.

Unlike 0008 the rebuild is otherwise safe here: nothing references ``request_cache_entries``, so the
``DROP`` cascades to nothing. The only missing half is the indexes, so this operation keeps
``AlterField``'s state and DDL and adds their restoration on the dialect that dropped them, under
the schema generator's own canonical names so a later ``makemigrations`` sees no drift.

AIDEV-NOTE: **this migration is a one-way door once v2 traffic exists.** The downgrade re-applies
``SET NOT NULL``, which fails as soon as a single global row is present, because every one of them
holds NULL by design. Reverting therefore requires deleting the global cache first
(``DELETE FROM request_cache_entries WHERE account_id = 'global'``) — a deliberate cache reset, not
a schema rollback. Documented for operators in ``DEPLOYMENT.md``.
"""

from typing import Any

from tortoise import fields, migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor.base import BaseSchemaEditor
from tortoise.migrations.schema_generator.state import State

_MODEL_NAME = "RequestCacheEntry"
# The only dialect whose nullability change rebuilds the table (and so loses its indexes).
_REBUILDING_DIALECTS = frozenset({"sqlite"})


def _dialect_of(schema_editor: BaseSchemaEditor) -> str:
    capabilities = getattr(getattr(schema_editor, "client", None), "capabilities", None)
    return (getattr(capabilities, "dialect", "") or "").lower()


def _declared_index_statements(schema_editor: BaseSchemaEditor, model: Any) -> list[str]:
    """The ``CREATE INDEX`` statements the schema generator would emit for ``model``.

    Derived from the model rather than hardcoded so a later indexed field is restored too, and built
    through the generator's own helper so the index NAMES match the ones ``CreateModel`` produced —
    a hand-rolled name would leave a duplicate index behind on the next rebuild.
    """
    statements: list[str] = []
    for field in model._meta.fields_map.values():
        if not getattr(field, "index", False) or getattr(field, "pk", False):
            continue
        column = field.source_field or field.model_field_name
        statements.append(schema_editor._get_index_sql(model, [column]))  # noqa: SLF001
    for index in model._meta.indexes or ():
        if isinstance(index, Index):
            index.resolve_expressions(model)
            statements.append(
                schema_editor._get_index_sql(  # noqa: SLF001
                    model,
                    list(index.field_names),
                    index_name=index.name,
                    index_type=index.INDEX_TYPE,
                    extra=index.extra,
                )
            )
            continue
        columns = [model._meta.fields_map[name].source_field or name for name in index]
        statements.append(schema_editor._get_index_sql(model, columns))  # noqa: SLF001
    return [statement for statement in dict.fromkeys(statements) if statement]


async def _restore_indexes(
    app_label: str,
    state: State,
    schema_editor: BaseSchemaEditor | None,
) -> None:
    if schema_editor is None:
        return
    if _dialect_of(schema_editor) not in _REBUILDING_DIALECTS:
        return
    model = state.apps.get_model(f"{app_label}.{_MODEL_NAME}")
    for statement in _declared_index_statements(schema_editor, model):
        await schema_editor._run_sql(statement)  # noqa: SLF001 - no public raw-SQL entry point


class NullableRequestCacheExpiry(ops.AlterField):
    """``AlterField``, plus the indexes SQLite's table rebuild drops."""

    def __init__(self) -> None:
        # INVARIANT: mirrors `BaseRequestCacheEntry.expires_at` exactly — any drift here re-arms the
        # autodetector, which would propose this same alter again and rebuild the table a second
        # time. Pinned by `test_autodetector_proposes_no_request_cache_change`.
        super().__init__(
            model_name=_MODEL_NAME,
            name="expires_at",
            field=fields.DatetimeField(db_index=True, null=True),
        )

    async def database_forward(
        self,
        app_label: str,
        old_state: State,
        new_state: State,
        state_editor: BaseSchemaEditor | None = None,
    ) -> None:
        await super().database_forward(app_label, old_state, new_state, state_editor)
        await _restore_indexes(app_label, new_state, state_editor)

    async def database_backward(
        self,
        app_label: str,
        old_state: State,
        new_state: State,
        state_editor: BaseSchemaEditor | None = None,
    ) -> None:
        """Re-imposing NOT NULL FAILS while any indefinite v2 row exists — deliberately.

        There is no honest expiry to invent for a row written as "never expires", and stamping one
        would make rows silently disappear later. An operator rolling back past this migration must
        first delete the global v2 rows.
        """
        await super().database_backward(app_label, old_state, new_state, state_editor)
        await _restore_indexes(app_label, new_state, state_editor)


class Migration(migrations.Migration):
    dependencies = [("models", "0008_widen_account_username")]

    operations = [NullableRequestCacheExpiry()]
