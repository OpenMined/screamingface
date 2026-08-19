"""Contract of the `ai.url4.result` frame's data: inline body XOR artifact claim ticket.

FEATURE: deliver large results in full instead of cutting them off at 1 MiB (OME-892).
INVARIANT: a ResultData names its result exactly one way — a complete inline `body`, or a
complete `artifact` reference — never both, never neither. A reader that can see a body can
trust it; a reader that sees an artifact knows the full result is one HTTP GET away.
"""

import pytest
from pydantic import ValidationError

from url4.streaming.protocol.signals import ResultArtifact, ResultData

_SHA = "9f" * 32  # a well-formed sha256 hex digest


def _artifact(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {"id": _SHA, "size_bytes": 3_572_814, "sha256": _SHA}
    fields.update(overrides)
    return fields


def test_inline_body_alone_is_valid_and_wire_compatible() -> None:
    # WHY: every pre-OME-892 frame is exactly this shape — it must keep validating unchanged.
    data = ResultData.model_validate({"body": '{"ok":true}', "media_type": None})
    assert data.body == '{"ok":true}'
    assert data.artifact is None


def test_artifact_alone_is_valid() -> None:
    data = ResultData.model_validate({"artifact": _artifact()})
    assert data.body is None
    assert isinstance(data.artifact, ResultArtifact)
    assert data.artifact.id == _SHA
    assert data.artifact.size_bytes == 3_572_814
    assert data.artifact.sha256 == _SHA


def test_body_and_artifact_together_are_rejected() -> None:
    # INVARIANT: exactly one — "always non-null but sometimes poisoned" is the contract
    # this design replaced; both-set would resurrect the ambiguity.
    with pytest.raises(ValidationError):
        ResultData.model_validate({"body": "x", "artifact": _artifact()})


def test_neither_body_nor_artifact_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ResultData.model_validate({"media_type": "application/json"})


@pytest.mark.parametrize(
    "bad",
    [
        _artifact(id="../etc/passwd"),  # path traversal must die at the model boundary
        _artifact(id="9F" * 32),  # uppercase hex is a second spelling of the same address
        _artifact(id="9f" * 31),  # short digest
        _artifact(sha256="zz" * 32),  # non-hex digest
        _artifact(size_bytes=0),  # an artifact always has content
        _artifact(size_bytes=-1),
    ],
)
def test_malformed_artifact_fields_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ResultData.model_validate({"artifact": bad})


def test_artifact_round_trips_through_json() -> None:
    data = ResultData.model_validate({"artifact": _artifact()})
    again = ResultData.model_validate_json(data.model_dump_json())
    assert again == data


def test_inline_result_serializes_without_an_artifact_key() -> None:
    # INVARIANT: a pre-OME-892 client sees byte-identical frames for inline results — the
    # artifact field appears on the wire ONLY when a claim ticket is actually issued.
    # (Global exclude_none would be wrong: `media_type: null` was already on the wire.)
    data = ResultData.model_validate({"body": "small", "media_type": None})
    dumped = data.model_dump()
    assert "artifact" not in dumped
    assert dumped == {"body": "small", "media_type": None}
    assert '"artifact"' not in data.model_dump_json()


def test_artifact_result_serializes_with_the_ticket() -> None:
    data = ResultData.model_validate({"artifact": _artifact()})
    dumped = data.model_dump()
    assert dumped["artifact"] == {"id": _SHA, "size_bytes": 3_572_814, "sha256": _SHA}
    assert dumped["body"] is None
