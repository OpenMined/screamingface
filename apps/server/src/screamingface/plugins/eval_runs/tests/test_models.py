"""Unit tests for EvalRun model invariants (no DB)."""

from __future__ import annotations

from tortoise import fields

from screamingface.plugins.eval_runs.models.eval_question import (
    BaseEvalQuestion,
    EvalQuestion,
)
from screamingface.plugins.eval_runs.models.eval_run import BaseEvalRun, EvalRun
from screamingface.plugins.state.base import BaseModel


def test_base_eval_run_is_abstract() -> None:
    assert BaseEvalRun._meta.abstract is True


def test_eval_run_inherits_state_basemodel() -> None:
    assert issubclass(EvalRun, BaseModel)


def test_eval_run_table_name() -> None:
    assert EvalRun._meta.db_table == "eval_run"


def test_eval_run_ordering_started_at_desc() -> None:
    from pypika_tortoise.enums import Order

    assert EvalRun._meta.ordering == (("started_at", Order.desc),)


def test_eval_run_has_expected_fields() -> None:
    fmap = EvalRun._meta.fields_map
    # Inherited from state.BaseModel
    assert "id" in fmap
    assert "created_at" in fmap
    assert "updated_at" in fmap
    # Own fields
    assert isinstance(fmap["spec_name"], fields.CharField)
    assert isinstance(fmap["url4_expression"], fields.TextField)
    assert isinstance(fmap["started_at"], fields.DatetimeField)
    assert fmap["finished_at"].null is True
    assert isinstance(fmap["status"], fields.CharField)
    assert fmap["accuracy"].null is True
    assert fmap["total_questions"].null is True
    assert fmap["correct_questions"].null is True
    assert fmap["error"].null is True


def test_base_eval_question_is_abstract() -> None:
    assert BaseEvalQuestion._meta.abstract is True


def test_eval_question_inherits_state_basemodel() -> None:
    assert issubclass(EvalQuestion, BaseModel)


def test_eval_question_table_name() -> None:
    assert EvalQuestion._meta.db_table == "eval_question"


def test_eval_question_unique_together_run_idx() -> None:
    assert EvalQuestion._meta.unique_together == (("run", "idx"),)


def test_eval_question_fk_cascades() -> None:
    fk = EvalQuestion._meta.fields_map["run"]
    # Tortoise stores on_delete behaviour on the relation descriptor.
    # `fields.CASCADE` is a string-valued enum in Tortoise 1.x — equality with
    # the enum or its `.value` both work.
    assert str(fk.on_delete).upper().endswith("CASCADE")  # type: ignore[attr-defined]


def test_eval_question_has_expected_fields() -> None:
    fmap = EvalQuestion._meta.fields_map
    assert isinstance(fmap["idx"], fields.IntField)
    assert isinstance(fmap["question"], fields.TextField)
    assert isinstance(fmap["expected"], fields.TextField)
    assert fmap["predicted"].null is True
    assert fmap["correct"].null is True
    assert fmap["raw_output"].null is True
    assert fmap["error"].null is True
