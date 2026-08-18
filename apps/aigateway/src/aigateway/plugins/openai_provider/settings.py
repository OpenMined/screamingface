from __future__ import annotations

import string
from typing import Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from aigateway.core.plugin_base import PluginSettings


def _default_models() -> list[str]:
    return [
        "openai/gpt-5.6-sol",
        "openai/gpt-5.6-terra",
        "openai/gpt-5.6-luna",
        "openai/gpt-5.5",
        "openai/gpt-5.1",
        "openai/gpt-5",
        "openai/gpt-5-mini",
        "openai/gpt-5-nano",
        "openai/gpt-4.1",
        "openai/gpt-4.1-mini",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/o3",
        "openai/o4-mini",
    ]


def _validate_model_id(model: str) -> str:
    prefix = "openai/"
    if not model.startswith(prefix):
        raise ValueError(f"OpenAI model must start with {prefix!r}: {model!r}")
    upstream = model[len(prefix) :]
    allowed = frozenset(string.ascii_letters + string.digits + "._-")
    if (
        not 1 <= len(upstream) <= 128
        or upstream[0] not in string.ascii_letters + string.digits
        or any(char not in allowed for char in upstream)
    ):
        raise ValueError(f"malformed direct OpenAI model: {model!r}")
    return model


class OpenAIPluginSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGW_OPENAI_",
        extra="ignore",
        populate_by_name=True,
    )

    default_models: list[str] = Field(default_factory=_default_models)
    validation_model: str = "openai/gpt-5-nano"

    @field_validator("default_models")
    @classmethod
    def _validate_models(cls, value: list[str]) -> list[str]:
        validated = [_validate_model_id(model) for model in value]
        if not validated:
            raise ValueError("direct OpenAI requires at least one default model")
        if len(set(validated)) != len(validated):
            raise ValueError("direct OpenAI default models must be unique")
        return validated

    @field_validator("validation_model")
    @classmethod
    def _validate_validation_model(cls, value: str) -> str:
        return _validate_model_id(value)

    @model_validator(mode="after")
    def _validation_model_must_be_registered(self) -> Self:
        if self.validation_model not in self.default_models:
            raise ValueError("direct OpenAI validation model must be registered")
        return self
