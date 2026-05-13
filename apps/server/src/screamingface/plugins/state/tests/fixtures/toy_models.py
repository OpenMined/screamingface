"""A throwaway model used by state plugin tests.

Not registered by the state plugin itself — tests register it dynamically via
state.register_models("toy", ["...toy_models"]).
"""

from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


class ToyItem(BaseModel):
    class Meta:
        table = "toy_item"

    name = fields.CharField(max_length=64)
    weight = fields.IntField(default=0)
