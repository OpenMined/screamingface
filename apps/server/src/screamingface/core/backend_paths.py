"""Shared helpers for URL4 backend-call paths and profile aliases."""

from __future__ import annotations

import hashlib
import logging
import re

_log = logging.getLogger(__name__)

PROFILE_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_UNSAFE_ALIAS_CHARS_RE = re.compile(r"[^a-z0-9_-]+")


def is_valid_profile_alias(alias: str) -> bool:
    return PROFILE_ALIAS_RE.match(alias) is not None


def normalize_backend_call_path(path: object) -> str | None:
    if not isinstance(path, str):
        return None
    normalized = path.rstrip("/")
    if not normalized or not normalized.startswith("/"):
        return None
    return normalized


def catalog_aliases_from_model_ids(model_ids: list[str]) -> dict[str, str]:
    """Derive deterministic URL4-safe aliases from gateway model ids.

    The gateway's ``/v1/models`` ids are already the model registry source of
    truth. URL4 aliases should be short enough to type, but collision-safe enough
    that autocomplete never advertises two aliases for different models.
    """

    candidates: list[tuple[str, str | None, str | None, str]] = []
    seen_model_ids: set[str] = set()
    for model_id in model_ids:
        if model_id in seen_model_ids:
            continue
        parts = _model_alias_parts(model_id)
        if parts is not None:
            candidates.append((*parts, model_id))
            seen_model_ids.add(model_id)
    candidates.sort(key=lambda item: item[3])

    base_counts: dict[str, int] = {}
    for base, _suffix, _owner, _model_id in candidates:
        base_counts[base] = base_counts.get(base, 0) + 1

    alias_groups: dict[str, list[str]] = {}
    for base, suffix, owner, model_id in candidates:
        alias = base
        if base_counts[base] > 1:
            alias = _join_alias_parts(base, suffix or owner)
        alias_groups.setdefault(alias, []).append(model_id)

    aliases: dict[str, str] = {}
    for alias, ids in sorted(alias_groups.items()):
        if len(ids) == 1:
            aliases[alias] = ids[0]
            continue
        for model_id in ids:
            hashed_alias = _hashed_alias(alias, model_id, aliases)
            _log.warning(
                "catalog model alias collision for %r; using %r for model %r",
                alias,
                hashed_alias,
                model_id,
            )
            aliases[hashed_alias] = model_id
    return aliases


def _model_alias_parts(model_id: str) -> tuple[str, str | None, str | None] | None:
    if not isinstance(model_id, str) or not model_id:
        return None
    path_parts = [part for part in model_id.split("/") if part]
    if not path_parts:
        return None

    last = path_parts[-1]
    model_part, _sep, provider_suffix = last.partition(":")
    base = _slugify_alias(model_part)
    if base is None:
        return None
    suffix = _slugify_alias(provider_suffix) if provider_suffix else None
    owner = _slugify_alias(path_parts[-2]) if len(path_parts) > 2 else None
    return base, suffix, owner


def _slugify_alias(value: str) -> str | None:
    slug = _UNSAFE_ALIAS_CHARS_RE.sub("-", value.lower()).strip("-_")
    if not slug or not slug[0].isalnum():
        return None
    return slug if is_valid_profile_alias(slug) else None


def _join_alias_parts(base: str, suffix: str | None) -> str:
    if not suffix:
        return base
    return f"{base}-{suffix}"


def _unique_alias(alias: str, aliases: dict[str, str]) -> str:
    if alias not in aliases:
        return alias
    i = 2
    while f"{alias}-{i}" in aliases:
        i += 1
    return f"{alias}-{i}"


def _hashed_alias(alias: str, model_id: str, aliases: dict[str, str]) -> str:
    digest = hashlib.sha1(model_id.encode("utf-8")).hexdigest()[:8]
    return _unique_alias(f"{alias}-{digest}", aliases)
