"""Collapse the unshipped preflight cache into the sole global request-cache schema."""

from typing import Any

from tortoise import migrations
from tortoise.indexes import Index
from tortoise.migrations import operations as ops
from tortoise.migrations.schema_editor.base import BaseSchemaEditor
from tortoise.migrations.schema_generator.state import State

_MODEL_NAME = "RequestCacheEntry"


async def _clear_preflight_rows(apps: Any, _schema_editor: BaseSchemaEditor) -> None:
    """Discard cache data whose mixed encrypted/plaintext representation is no longer supported."""
    model = apps.get_model("models", _MODEL_NAME)
    await model.all().delete()


async def _restore_sqlite_indexes(apps: Any, schema_editor: BaseSchemaEditor) -> None:
    """Restore standalone indexes lost by SQLite's RemoveField table rebuilds."""
    capabilities = getattr(getattr(schema_editor, "client", None), "capabilities", None)
    dialect = (getattr(capabilities, "dialect", "") or "").lower()
    if dialect != "sqlite":
        return

    model = apps.get_model("models", _MODEL_NAME)
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

    for statement in dict.fromkeys(statements):
        await schema_editor._run_sql(statement)  # noqa: SLF001


async def _restore_preflight_identity_indexes(apps: Any, schema_editor: BaseSchemaEditor) -> None:
    """Restore indexes Tortoise 1.1.7 omits when RemoveField runs backward."""
    model = apps.get_model("models", _MODEL_NAME)
    for name in ("account_id", "profile_name"):
        field = model._meta.fields_map[name]
        column = field.source_field or field.model_field_name
        statement = schema_editor._get_index_sql(model, [column])  # noqa: SLF001
        await schema_editor._run_sql(statement)  # noqa: SLF001


class RemoveLegacyScopeIndex(ops.RemoveIndex):
    """Work around Tortoise 1.1.7 failing to remove tuple-declared indexes from state."""

    def __init__(self) -> None:
        super().__init__(
            model_name=_MODEL_NAME,
            fields=["account_id", "profile_name", "provider", "expires_at"],
        )

    def state_forward(self, app_label: str, state: State) -> None:
        model_state = self.get_model_state(state, app_label, self.model_name)
        indexes = list(model_state.options.get("indexes") or ())
        target = tuple(self.fields or ())
        for index in indexes:
            if not isinstance(index, Index) and tuple(index) == target:
                indexes.remove(index)
                break
        else:  # pragma: no cover - migration state is fixed by 0006
            raise ValueError(f"legacy request-cache index {target!r} is absent")
        if indexes:
            model_state.options["indexes"] = tuple(indexes)
        else:
            model_state.options.pop("indexes", None)
        state.reload_model(app_label, self.model_name)


class Migration(migrations.Migration):
    dependencies = [("models", "0009_global_request_cache")]

    operations = [
        # This operation runs last on downgrade, after the identity fields have been restored.
        ops.RunPython(code=ops.RunPython.noop, reverse_code=_restore_preflight_identity_indexes),
        ops.RunPython(code=_clear_preflight_rows, reverse_code=ops.RunPython.noop),
        RemoveLegacyScopeIndex(),
        ops.RenameField(
            model_name=_MODEL_NAME,
            old_name="response_ciphertext",
            new_name="response_json",
        ),
        ops.RemoveField(model_name=_MODEL_NAME, name="account_id"),
        ops.RemoveField(model_name=_MODEL_NAME, name="key_version"),
        ops.RemoveField(model_name=_MODEL_NAME, name="profile_name"),
        ops.RunPython(code=_restore_sqlite_indexes, reverse_code=ops.RunPython.noop),
        # Operations run in reverse order on downgrade. Clear rows before the removed NOT NULL
        # columns are restored, even if an operator forgot the documented cache reset.
        ops.RunPython(code=ops.RunPython.noop, reverse_code=_clear_preflight_rows),
    ]
