"""Models and pools (engine-side).

`Model` is a thin, friendly handle over a catalog entry. `Pool` is an ordered,
de-duplicated collection of models filterable by price / context / provider.
AIDEV-NOTE: `Pool` is INTERNAL in the SDK — the public discovery surface is the
`sf.models` service (studio.py), which returns plain `provider/model` id strings.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from .catalog import _POOLS, MODEL_META, PROVIDERS, ModelMeta, Provider, provider_color


@dataclass(frozen=True)
class Model:
    """A single model offered by a provider."""

    id: str
    name: str
    provider_id: str
    tag: str | None = None

    @property
    def provider(self) -> Provider:
        return PROVIDERS[self.provider_id]

    @property
    def provider_name(self) -> str:
        return self.provider.name

    @property
    def meta(self) -> ModelMeta:
        return MODEL_META[self.id]

    @property
    def price_in(self) -> float:
        return self.meta.price_in

    @property
    def price_out(self) -> float:
        return self.meta.price_out

    @property
    def price(self) -> float:
        """Combined in+out price per million tokens."""
        m = self.meta
        return m.price_in + m.price_out

    @property
    def ctx(self) -> int:
        return self.meta.ctx

    @property
    def ability(self) -> float:
        return self.meta.ability

    @property
    def color(self) -> str:
        return provider_color(self.provider_id)

    @property
    def label(self) -> str:
        return f"{self.name} [{self.provider_name}]"

    def __str__(self) -> str:
        return self.label


def _build_all() -> dict[str, Model]:
    out: dict[str, Model] = {}
    for provider_id, entries in _POOLS.items():
        for mid, name, tag in entries:
            out[mid] = Model(id=mid, name=name, provider_id=provider_id, tag=tag)
    return out


ALL_MODELS: dict[str, Model] = _build_all()


def get_model(model_id: str) -> Model:
    try:
        return ALL_MODELS[model_id]
    except KeyError:
        raise KeyError(
            f"Unknown model id {model_id!r}. Try sf.models.list() or sf.models.list(search=...)."
        ) from None


def resolve(m: str | Model) -> Model:
    """Accept either a short model id or a Model and return a Model."""
    return m if isinstance(m, Model) else get_model(m)


class Pool:
    """An ordered, de-duplicated set of models. Filtering is non-mutating."""

    def __init__(self, models: Iterable[str | Model] = ()):
        self._models: list[Model] = []
        self._ids: set[str] = set()
        for m in models:
            self.add(m)

    def __iter__(self) -> Iterator[Model]:
        return iter(self._models)

    def __len__(self) -> int:
        return len(self._models)

    def __getitem__(self, i: int) -> Model:
        return self._models[i]

    @property
    def ids(self) -> list[str]:
        return [m.id for m in self._models]

    def add(self, m: str | Model) -> Pool:
        model = resolve(m)
        if model.id not in self._ids:
            self._models.append(model)
            self._ids.add(model.id)
        return self

    def filter(
        self,
        search: str = "",
        max_price: float | None = None,
        min_ctx: int = 0,
        provider: str | Iterable[str] | None = None,
    ) -> Pool:
        q = search.lower()
        providers = None
        if provider is not None:
            providers = {provider} if isinstance(provider, str) else set(provider)

        def keep(m: Model) -> bool:
            return (
                (not q or q in m.name.lower())
                and (providers is None or m.provider_id in providers)
                and (max_price is None or m.price <= max_price)
                and (not min_ctx or m.ctx >= min_ctx)
            )

        return Pool(m for m in self._models if keep(m))

    _SORT_KEYS: dict[str, Callable[[Model], object]] = {
        "price": lambda m: m.price,
        "context": lambda m: m.ctx,
        "ctx": lambda m: m.ctx,
        "ability": lambda m: m.ability,
        "name": lambda m: m.name,
    }

    def sort_by(self, field: str, desc: bool = False) -> Pool:
        """Sort by a named field: price / context / ability / name."""
        key = self._SORT_KEYS.get(field)
        if key is None:
            raise KeyError(
                f"Unknown sort key {field!r}. Choose one of "
                f"{sorted(k for k in self._SORT_KEYS if k != 'ctx')}."
            )
        return Pool(sorted(self._models, key=key, reverse=desc))  # type: ignore[arg-type]

    def __repr__(self) -> str:
        ids = ", ".join(self.ids[:6])
        return f"Pool({len(self)} models: {ids}{' …' if len(self) > 6 else ''})"


# the master catalog: every known model, ready to filter
catalog = Pool(ALL_MODELS.values())
