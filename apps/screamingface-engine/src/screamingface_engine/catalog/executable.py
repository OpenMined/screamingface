"""Project AI Gateway discovery onto the Engine's declared execution world."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from screamingface_engine.catalog.cache import CacheCounters, CatalogService
from screamingface_engine.catalog.port import (
    CatalogBadResponse,
    Credential,
    ModelCatalog,
    ModelNotInstalled,
    ModelParameterResponse,
    ModelParameterSource,
    compute_etag,
)
from screamingface_engine.models.registry import decode_route_id, encode_route_id


class ExecutableCatalogSource(CatalogService, Protocol):
    """The managed catalog surface preserved by the executable-world decorator."""

    @property
    def counters(self) -> CacheCounters | None: ...

    @property
    def entry_count(self) -> int: ...

    @property
    def model_parameter_source(self) -> ModelParameterSource | None: ...

    async def aclose(self) -> None: ...


class ExecutableCatalog:
    """A catalog decorator that keeps only model documents installed on this Engine.

    The wrapped cache remains caller-scoped and stores AI Gateway's authoritative response.
    Projection happens after that fetch so one deployment-level route set cannot leak into the
    Gateway adapter's provider/profile contract. Retained model documents and unknown top-level
    fields pass through unchanged.
    """

    def __init__(self, source: ExecutableCatalogSource, model_ids: frozenset[str]) -> None:
        self._source = source
        self._model_ids = model_ids
        parameter_source = source.model_parameter_source
        self._model_parameter_source = (
            None
            if parameter_source is None
            else ExecutableModelParameterSource(parameter_source, model_ids)
        )

    @property
    def counters(self) -> CacheCounters | None:
        return self._source.counters

    @property
    def entry_count(self) -> int:
        return self._source.entry_count

    async def fetch(self, credential: Credential) -> ModelCatalog:
        catalog = await self._source.fetch(credential)
        data = catalog.body.get("data")
        # WHY this one raises but a bad ENTRY does not: a `data` that is not a list cannot be
        # projected at all, so there is no honest answer to give. A single malformed entry has
        # one — omit it. Raising there would let one odd upstream document turn discovery into a
        # 502 for every caller, and `CachedCatalog` serves stale-on-error, so a PERSISTENT
        # oddity would degrade into an outage once `stale_max_s` elapsed.
        if not isinstance(data, list):
            raise CatalogBadResponse("catalog data is not a list")
        # INVARIANT: membership is the whole filter. An entry that is not a mapping, or whose id
        # is absent or not a string, cannot equal a declared id — so the acceptance contract
        # ("every id returned is a declared route") holds without a separate shape check, and an
        # unknown future field on a RETAINED document still passes through untouched.
        #
        # WHY rewrite `id` here (OME-873): `self._model_ids` holds the REAL gateway ids (what
        # aigateway's own `data[].id` names, and what the membership check above compares
        # against), but what a caller should put in a url4 expression is the `~`-encoded route
        # id. `encode_route_id` is a no-op for the ids with no colon, so this applies uniformly.
        body = {
            **catalog.body,
            "data": [
                {**item, "id": encode_route_id(item["id"])}
                for item in data
                if isinstance(item, Mapping) and item.get("id") in self._model_ids
            ],
        }
        return ModelCatalog(body=body, etag=compute_etag(body))

    def max_age_s(self, credential: Credential) -> int:
        return self._source.max_age_s(credential)

    async def aclose(self) -> None:
        await self._source.aclose()

    @property
    def model_parameter_source(self) -> ModelParameterSource | None:
        """The uncached Gateway detail source, guarded by this same executable route set."""

        return self._model_parameter_source


class ExecutableModelParameterSource:
    """Reject model-parameter lookups outside the same declared execution world."""

    def __init__(self, source: ModelParameterSource, model_ids: frozenset[str]) -> None:
        self._source = source
        self._model_ids = model_ids

    async def fetch_model_parameters(
        self,
        credential: Credential,
        model: str,
    ) -> ModelParameterResponse:
        # `model` arrives as the caller wrote it — the same `~`-encoded id `GET /v1/models` just
        # advertised (OME-873). `self._model_ids` holds the REAL ids, and aigateway itself has
        # never heard of '~', so both the membership check and the forwarded call need the
        # decoded form; `ModelNotInstalled` echoes back what the caller actually sent.
        real_model = decode_route_id(model)
        if real_model not in self._model_ids:
            raise ModelNotInstalled(model)
        return await self._source.fetch_model_parameters(credential, real_model)


__all__ = ["ExecutableCatalog", "ExecutableCatalogSource", "ExecutableModelParameterSource"]
