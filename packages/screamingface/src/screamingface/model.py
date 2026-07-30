"""Atomic model-backed Recipe values."""

from __future__ import annotations

from dataclasses import dataclass

from screamingface.recipe import (
    Recipe,
    _instructions,
    _max_output_tokens,
    _model_route,
    _model_value_repr,
    _name,
    _reasoning,
    _temperature,
)


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Model(Recipe):
    """One immutable model-backed answer Recipe."""

    model: str
    name: str
    instructions: str | None
    temperature: float | None
    reasoning: str | None
    max_output_tokens: int | None

    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        instructions: str | None = None,
        temperature: float | None = None,
        reasoning: str | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        route = _model_route(model)
        inferred_name = route.rsplit("/", 1)[-1]
        object.__setattr__(self, "model", route)
        object.__setattr__(
            self,
            "name",
            _name(inferred_name if name is None else name, "model name"),
        )
        object.__setattr__(self, "instructions", _instructions(instructions))
        object.__setattr__(self, "temperature", _temperature(temperature))
        object.__setattr__(self, "reasoning", _reasoning(reasoning))
        object.__setattr__(self, "max_output_tokens", _max_output_tokens(max_output_tokens))

    @property
    def _recipe_marker(self) -> None:
        return None

    def __repr__(self) -> str:
        return _model_value_repr(
            "Model",
            model=self.model,
            name=self.name,
            instructions=self.instructions,
            temperature=self.temperature,
            reasoning=self.reasoning,
            max_output_tokens=self.max_output_tokens,
        )

    def _repr_html_(self) -> str:
        from screamingface._card_display import model_card_html

        return model_card_html(self)


__all__ = ["Model"]
