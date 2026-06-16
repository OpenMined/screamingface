"""Async data-access helpers for PrivateEntity. Keeps route handlers slim.

uuid7 strings arrive from the URL/path; we parse to UUID and look up by pk.
Invalid uuids resolve to None (handlers turn that into 404)."""

from __future__ import annotations

from uuid import UUID

from uuid6 import uuid7

from screamingface.plugins.private_storage.models import PrivateEntity


def _parse(uuid_str: str) -> UUID | None:
    try:
        return UUID(uuid_str)
    except (ValueError, AttributeError, TypeError):
        return None


async def create_entity(*, content: str = "", label: str | None = None) -> PrivateEntity:
    return await PrivateEntity.create(id=uuid7(), content=content, label=label)


async def get_entity(uuid_str: str) -> PrivateEntity | None:
    key = _parse(uuid_str)
    if key is None:
        return None
    return await PrivateEntity.get_or_none(id=key)


async def list_entities() -> list[PrivateEntity]:
    return await PrivateEntity.all()  # Meta.ordering => newest updated first


async def update_entity(
    uuid_str: str, *, content: str | None = None, label: str | None = None, label_set: bool = False
) -> PrivateEntity | None:
    entity = await get_entity(uuid_str)
    if entity is None:
        return None
    if content is not None:
        entity.content = content
    if label_set:  # allows clearing the label to None explicitly
        entity.label = label
    await entity.save()
    return entity


async def delete_entity(uuid_str: str) -> bool:
    key = _parse(uuid_str)
    if key is None:
        return False
    deleted = await PrivateEntity.filter(id=key).delete()
    return deleted > 0
