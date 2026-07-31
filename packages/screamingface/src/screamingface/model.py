"""Atomic model-backed Candidate values."""

from __future__ import annotations

from dataclasses import dataclass

from screamingface.recipe import Recipe, _model_route, _name


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Model(Recipe):
    """Select one model route for a Benchmark-owned answer policy."""

    model: str
    name: str
    _sample_id: str | None

    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
    ) -> None:
        route = _model_route(model)
        inferred_name = route.rsplit("/", 1)[-1]
        explicit_name = None if name is None else _name(name, "model name")
        object.__setattr__(self, "model", route)
        object.__setattr__(self, "name", inferred_name if explicit_name is None else explicit_name)
        object.__setattr__(self, "_sample_id", explicit_name)

    @property
    def _recipe_marker(self) -> None:
        return None

    def __repr__(self) -> str:
        if self._sample_id is None:
            return f"Model({self.model!r})"
        return f"Model({self.model!r}, name={self.name!r})"

    def _repr_html_(self) -> str:
        from screamingface._card_display import model_card_html

        return model_card_html(self)


__all__ = ["Model"]
