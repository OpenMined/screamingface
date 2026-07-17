"""Fusion reducer contracts and built-in mechanisms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal, NotRequired, TypedDict, cast

from screamingface.model_inputs import ParameterValue, _parameter_items

ExecutionLocation = Literal["local", "engine"]


class MajorityVoteConfig(TypedDict):
    kind: Literal["majority_vote"]
    tie_breaker: NotRequired[str | None]


class ModelReducerConfig(TypedDict):
    kind: Literal["model"]
    model: str
    prompt: str
    params: NotRequired[dict[str, ParameterValue]]


type ReducerConfig = MajorityVoteConfig | ModelReducerConfig


class Reducer(ABC):
    """Base contract for turning completed panel outputs into one answer.

    Concrete reducers define a mechanism. Semantic variants of model-backed
    reduction—synthesis, selection, ranking, or adjudication—belong in the
    model prompt rather than in separate reducer classes.
    """

    @property
    @abstractmethod
    def kind(self) -> str:
        """Stable serialized reducer kind."""

    @property
    @abstractmethod
    def execution(self) -> ExecutionLocation:
        """Where reduction is executed."""

    @property
    def name(self) -> str:
        """Stable serialized reducer kind."""

        return self.kind


class LocalReducer(Reducer):
    """A deterministic reducer executed by the ScreamingFace SDK."""

    execution: ClassVar[ExecutionLocation] = "local"

    def reduce(self, answers: Sequence[str], model_names: Sequence[str]) -> str:
        raise NotImplementedError


class EngineReducer(Reducer):
    """A reducer represented as additional work in the URL4 graph."""

    execution: ClassVar[ExecutionLocation] = "engine"


@dataclass(frozen=True, slots=True)
class MajorityVote(LocalReducer):
    """Select the most common normalized answer.

    ``tie_breaker`` names an existing configured model whose answer wins a tied
    vote. A unique model ID is accepted as shorthand. It never causes an
    additional model call.
    """

    tie_breaker: str | None = None
    kind: ClassVar[str] = "majority_vote"

    def reduce(self, answers: Sequence[str], model_names: Sequence[str]) -> str:
        if len(answers) != len(model_names):
            raise ValueError("answers and model_names must have the same length")
        counts = Counter(answer for answer in answers if answer)
        result = ""
        if counts:
            highest = max(counts.values())
            winners = {answer for answer, count in counts.items() if count == highest}
            result = next(iter(winners)) if len(winners) == 1 else sorted(winners)[0]
            if len(winners) > 1 and self.tie_breaker is not None:
                tied_answer = answers[tuple(model_names).index(self.tie_breaker)]
                if tied_answer:
                    result = tied_answer
        return result


@dataclass(frozen=True, slots=True, init=False)
class ModelReducer(EngineReducer):
    """Use one model and one URL4-native prompt to reduce panel outputs."""

    model: str
    prompt: str
    _params: tuple[tuple[str, ParameterValue], ...]
    kind: ClassVar[str] = "model"

    def __init__(
        self,
        *,
        model: str,
        prompt: str,
        params: Mapping[str, ParameterValue] | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model reducer model must not be empty")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("model reducer prompt must not be empty")
        object.__setattr__(self, "model", model.strip())
        object.__setattr__(self, "prompt", prompt.strip())
        object.__setattr__(self, "_params", _parameter_items(params))

    @property
    def params(self) -> dict[str, ParameterValue]:
        """Return a defensive copy of request-affecting model parameters."""

        return dict(self._params)

    @property
    def parameter_items(self) -> tuple[tuple[str, ParameterValue], ...]:
        return self._params


def reducer_from_config(config: Mapping[str, object]) -> Reducer:
    """Decode a strict portable reducer mapping into its Python mechanism."""

    kind = config.get("kind")
    if kind is None:
        raise ValueError("reducer configuration is missing required field: kind")
    if not isinstance(kind, str):
        raise ValueError("reducer configuration field 'kind' must be a string")
    try:
        decoder = _REDUCER_CONFIG_DECODERS[kind]
    except KeyError as exc:
        raise ValueError(f"unknown reducer kind: {kind}") from exc
    return decoder(config)


def _majority_vote_from_config(config: Mapping[str, object]) -> Reducer:
    _reject_unknown(config, {"kind", "tie_breaker"})
    tie_breaker = config.get("tie_breaker")
    if tie_breaker is not None and not isinstance(tie_breaker, str):
        raise ValueError("majority_vote reducer field 'tie_breaker' must be a string or null")
    return MajorityVote(tie_breaker=tie_breaker)


def _model_reducer_from_config(config: Mapping[str, object]) -> Reducer:
    _reject_unknown(config, {"kind", "model", "prompt", "params"})
    missing = {"model", "prompt"} - set(config)
    if missing:
        fields = ", ".join(sorted(missing))
        raise ValueError(f"model reducer is missing required field(s): {fields}")
    model = config["model"]
    prompt = config["prompt"]
    params = config.get("params")
    if not isinstance(model, str):
        raise ValueError("model reducer field 'model' must be a string")
    if not isinstance(prompt, str):
        raise ValueError("model reducer field 'prompt' must be a string")
    if params is not None and not isinstance(params, Mapping):
        raise ValueError("model reducer field 'params' must be a mapping")
    return ModelReducer(
        model=model,
        prompt=prompt,
        params=cast("Mapping[str, ParameterValue] | None", params),
    )


def _reject_unknown(config: Mapping[str, object], allowed: set[str]) -> None:
    unknown = set(config) - allowed
    if unknown:
        fields = ", ".join(sorted(str(field) for field in unknown))
        raise ValueError(f"reducer configuration contains unknown field(s): {fields}")


_REDUCER_CONFIG_DECODERS = {
    "majority_vote": _majority_vote_from_config,
    "model": _model_reducer_from_config,
}
