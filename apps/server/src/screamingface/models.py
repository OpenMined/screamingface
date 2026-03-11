"""Shared base models for ScreamingFace plugins."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AliasedModel(BaseModel):
    """Base for all plugin API models.

    Uses validation_alias for accepting both long and short names in input,
    and serialization_alias for compact output.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )
