"""Member runtime facts distinguish unavailable attribution from observed empty values."""

from __future__ import annotations

import screamingface as sf


def test_unattributed_member_runtime_fields_serialize_as_null() -> None:
    member = sf.MemberResult(
        operation_id="op_model_1",
        name="member one",
        kind="model",
        models=("provider/model",),
        failures=None,
        duration_ms=None,
        usage=None,
    )

    assert member.to_dict() == {
        "operation_id": "op_model_1",
        "name": "member one",
        "kind": "model",
        "models": ["provider/model"],
        "failures": None,
        "duration_ms": None,
        "usage": None,
    }
