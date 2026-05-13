# `state` plugin

Generic stateful storage core for screamingface plugins. Owns Tortoise ORM
lifecycle, accepts model registrations from other plugins, exposes a
cross-cutting `BaseModel` and a generic `BaseStore[T]` helper, and ships
pytest fixtures.

## Quickstart for a new stateful plugin

```python
# apps/server/src/screamingface/plugins/my_plugin/plugin.py
from screamingface.plugin import Plugin
from screamingface.plugins.state.plugin import StatePlugin


class MyPlugin(Plugin):
    name = "my-plugin"
    depends = ["state"]

    def setup(self, app, hooks, classes, routes):
        state: StatePlugin = app.state.state_plugin
        state.register_models(
            "my_plugin",
            ["screamingface.plugins.my_plugin.models"],
        )
        # ... routes, etc.
```

The state plugin's `app.startup` hook runs *after* every plugin's `setup()`,
so by the time Tortoise initializes, every plugin has had its chance to
register. **Do not query the DB in `setup()`** — only in request handlers
or in your own post-startup hook.

## Model conventions (required)

Downstream plugins MUST follow these. Reviewers enforce them.

1. **Models live in a `models/` subpackage.** Never a single `models.py`.
2. **One file per model.**
3. **Each concrete model has an abstract `Base<Entity>` interface.** The
   `Base<Entity>` declares fields and pure helpers; the concrete model adds
   relations, `Meta.table`, and DB-dependent behaviour. The service layer
   accepts `Base<Entity>` so it can be unit-tested with a mock.
4. **All concrete models inherit from `state.BaseModel`** (UUID pk + `created_at` + `updated_at`).
5. **Class member order** inside any model:
   1. `class Meta` first
   2. fields
   3. class/private methods (`__str__`, `_helper`, …)
   4. public methods
6. **`models/__init__.py` re-exports both** the `Base<Entity>` and the concrete model.

### Example

```python
# my_plugin/models/widget.py
from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


class BaseWidget(BaseModel):
    class Meta:
        abstract = True

    name = fields.CharField(max_length=128)
    weight = fields.IntField(default=0)

    def __str__(self) -> str:
        return self.name


class Widget(BaseWidget):
    class Meta:
        table = "widget"
```

```python
# my_plugin/models/__init__.py
from .widget import BaseWidget, Widget

__all__ = ["BaseWidget", "Widget"]
```

## `BaseStore[T]`

Optional CRUD helper for plugins that don't need joined or aggregate
queries:

```python
from screamingface.plugins.state.store import BaseStore
from screamingface.plugins.my_plugin.models import Widget


class WidgetStore(BaseStore[Widget]):
    model = Widget

store = WidgetStore()
w = await store.create(name="alpha", weight=3)
w = await store.get(w.id)
await store.update(w.id, weight=99)
await store.delete(w.id)
```

Composite/joined queries: skip `BaseStore`, use the queryset API
(`Widget.filter(...).prefetch_related(...)`).

## Settings

| Env var | Default | Purpose |
| --- | --- | --- |
| `SF_STATE__PATH` | `~/.screamingface/state.db` | sqlite file location |
| `SF_STATE__ECHO` | `false` | SQL echo (reserved; not yet wired) |

The parent directory is auto-created on startup.

## Testing

Import the fixtures in your plugin's `tests/conftest.py`:

```python
from screamingface.plugins.state.testing import (  # noqa: F401
    initialized_state,
    temp_state_path,
)
```

Then in your tests:

```python
import pytest


async def test_widget_create(temp_state_path):
    config = AppConfig(plugins=["state", "my-plugin"], plugin_config={})
    app = create_app(config)
    async with app.router.lifespan_context(app):
        # query the DB here
        ...
```

Every test gets an isolated sqlite file under `tmp_path`.

## Migration limitation

The state plugin uses `Tortoise.generate_schemas(safe=True)` — additive-only.
No `aerich`. Destructive migrations (renamed columns, type changes) require
shipping a one-shot patch in an app update.

If screamingface grows a server-deployed component, we adopt aerich. Tracked
as a follow-up ticket.

## Out of scope

- Per-plugin separate database files
- Postgres driver (model code stays Postgres-compatible; URL swap is a
  deployment concern)
- aerich / destructive migrations
- Cross-plugin transactions or FKs spanning `app_label`s
