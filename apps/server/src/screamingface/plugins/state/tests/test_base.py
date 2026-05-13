"""Tests for the cross-cutting BaseModel."""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model

from screamingface.plugins.state.base import BaseModel


def test_basemodel_is_abstract() -> None:
    assert BaseModel._meta.abstract is True


def test_basemodel_has_uuid_primary_key() -> None:
    pk = BaseModel._meta.fields_map["id"]
    assert isinstance(pk, fields.UUIDField)
    assert pk.pk is True


def test_basemodel_has_audit_timestamps() -> None:
    fmap = BaseModel._meta.fields_map
    assert isinstance(fmap["created_at"], fields.DatetimeField)
    assert isinstance(fmap["updated_at"], fields.DatetimeField)
    assert fmap["created_at"].auto_now_add is True
    assert fmap["updated_at"].auto_now is True


def test_basemodel_is_a_tortoise_model() -> None:
    assert issubclass(BaseModel, Model)
