"""Generic CRUD helper for plugins that don't need composite queries.

Plugins subclass BaseStore by setting `model`:

    class EvalRunStore(BaseStore[EvalRun]):
        model = EvalRun

then call store.create(...), store.get(...), etc. Composite queries (joins,
aggregates) should use Tortoise's queryset API directly — BaseStore is not the
place for them.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from tortoise.exceptions import DoesNotExist
from tortoise.models import Model

T = TypeVar("T", bound=Model)


class BaseStore(Generic[T]):
    model: type[T]

    def __init__(self, model: type[T] | None = None) -> None:
        if model is not None:
            self.model = model
        if not hasattr(self, "model"):
            raise TypeError(
                f"{type(self).__name__} must set `model` as a class attribute "
                "or pass it to __init__"
            )

    async def create(self, **fields: Any) -> T:
        return await self.model.create(**fields)

    async def get(self, id: Any) -> T | None:
        try:
            return await self.model.get(id=id)
        except DoesNotExist:
            return None

    async def list(self, *, limit: int = 50, offset: int = 0, **filters: Any) -> list[T]:
        qs = self.model.filter(**filters) if filters else self.model.all()
        return await qs.offset(offset).limit(limit)

    async def update(self, id: Any, **fields: Any) -> T:
        obj = await self.model.get(id=id)
        for key, value in fields.items():
            setattr(obj, key, value)
        await obj.save(update_fields=list(fields.keys()))
        return obj

    async def delete(self, id: Any) -> bool:
        deleted = await self.model.filter(id=id).delete()
        return deleted > 0
