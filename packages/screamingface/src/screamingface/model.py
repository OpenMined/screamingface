"""Atomic model-backed answer Recipe."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from screamingface.model_inputs import ParameterValue, _ModelCall, _RecipeMember, make_model_call
from screamingface.recipe import Recipe, _name
from screamingface.reducers import Reducer

_DEFAULT_PROMPT = "Answer the question."


@dataclass(frozen=True, slots=True, init=False)
class Model(Recipe):
    """One configured model call that can run alone or as a Fusion member."""

    name: str
    model: str
    prompt: str
    _parameter_items: tuple[tuple[str, ParameterValue], ...] = field(repr=False)
    _explicit_name: bool = field(repr=False)

    def __init__(
        self,
        model: str,
        *,
        name: str | None = None,
        prompt: str | None = None,
        params: Mapping[str, ParameterValue] | None = None,
    ) -> None:
        call = make_model_call(
            model=model,
            prompt=_DEFAULT_PROMPT if prompt is None else prompt,
            params=params,
        )
        inferred_name = call.model.rsplit("/", 1)[-1]
        object.__setattr__(
            self,
            "name",
            _name(inferred_name if name is None else name, "model name"),
        )
        object.__setattr__(self, "model", call.model)
        object.__setattr__(self, "prompt", call.prompt)
        object.__setattr__(self, "_parameter_items", call.parameter_items)
        object.__setattr__(self, "_explicit_name", name is not None)

    @property
    def params(self) -> dict[str, ParameterValue]:
        return dict(self._parameter_items)

    def _repr_html_(self) -> str:
        from screamingface._card_display import model_card_html

        return model_card_html(self)

    @property
    def members(self) -> tuple[()]:
        return ()

    @property
    def reducer(self) -> None:
        return None

    @property
    def model_ids(self) -> tuple[str, ...]:
        return (self.model,)

    @property
    def _call(self) -> _ModelCall:
        return _ModelCall(self.model, self.prompt, self._parameter_items)

    @property
    def _members(self) -> tuple[_RecipeMember, ...]:
        return (_RecipeMember(id="member_1", call=self._call),)

    @property
    def _reducers(self) -> tuple[Reducer, ...]:
        return ()


__all__ = ["Model"]
