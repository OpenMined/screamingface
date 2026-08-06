"""Project AI Gateway discovery onto the Engine's declared execution world."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from url4_cloud.catalog.cache import CatalogService
from url4_cloud.catalog.port import (
    CatalogBadResponse,
    Credential,
    ModelCatalog,
    ModelNotInstalled,
    ModelParameterResponse,
    ModelParameterSource,
    compute_etag,
)


class ExecutableCatalog:
    """A catalog decorator that keeps only model documents installed on this Engine.

    The wrapped cache remains caller-scoped and stores AI Gateway's authoritative response.
    Projection happens after that fetch so one deployment-level route set cannot leak into the
    Gateway adapter's provider/profile contract. Retained model documents and unknown top-level
    fields pass through unchanged.
    """

    def __init__(self, source: CatalogService, model_ids: frozenset[str]) -> None:
        self._source = source
        self._model_ids = model_ids

    @property
    def counters(self) -> Any:
        return getattr(self._source, "counters", None)

    @property
    def entry_count(self) -> int:
        return int(getattr(self._source, "entry_count", 0))

    async def fetch(self, credential: Credential) -> ModelCatalog:
        catalog = await self._source.fetch(credential)
        data = catalog.body.get("data")
        if not isinstance(data, list):
            raise CatalogBadResponse("catalog data is not a list")
        for item in data:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                raise CatalogBadResponse("catalog model is missing a string id")
        body = {
            **catalog.body,
            "data": [item for item in data if item.get("id") in self._model_ids],
        }
        return ModelCatalog(body=body, etag=compute_etag(body))

    def max_age_s(self, credential: Credential) -> int:
        return self._source.max_age_s(credential)

    async def aclose(self) -> None:
        close = getattr(self._source, "aclose", None)
        if close is not None:
            await close()

    @property
    def model_parameter_source(self) -> ModelParameterSource | None:
        """The uncached Gateway detail source, guarded by this same executable route set."""

        source = getattr(self._source, "model_parameter_source", None)
        if source is None:
            return None
        return ExecutableModelParameterSource(source, self._model_ids)


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
        if model not in self._model_ids:
            raise ModelNotInstalled(model)
        return await self._source.fetch_model_parameters(credential, model)


__all__ = ["ExecutableCatalog", "ExecutableModelParameterSource"]
