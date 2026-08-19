"""Decoding results from OLDER Engines that still truncate (OME-892).

FEATURE: deliver large results in full instead of cutting them off at 1 MiB.
INVARIANT: a body ending in the legacy `…[truncated]` marker is named as truncation —
with the received byte count — never reported as the generic "must be JSON", which sent
researchers on an archaeology dig through clean engine logs (GitHub #642).
"""

from datetime import UTC, datetime

import pytest

from screamingface._core.ports import _RunOutcome
from screamingface._evaluation.model import Candidate, _compiled_candidate, _compiled_operation
from screamingface._evaluation.results import report_from_url4_outcome
from screamingface.errors import ExecutionError

_T = datetime(2026, 8, 18, 9, 0, 0, tzinfo=UTC)


def _candidate() -> Candidate:
    return _compiled_candidate(
        name="opus",
        kind="model",
        models=("provider/opus",),
        url4="(@)!'hello'",
        operations=(
            _compiled_operation(id="op_opus", kind="model", label="opus answer", depends_on=()),
        ),
    )


def _outcome(body: str | None) -> _RunOutcome:
    return _RunOutcome(
        run_id="run_1",
        started_at=_T,
        completed_at=_T,
        result_body=body,
        media_type="application/json",
        root_usage=None,
    )


def test_legacy_truncation_marker_is_named_with_the_received_byte_count() -> None:
    truncated = '{"schema":"screamingface.candidate-result.v1","cases":[' + "…[truncated]"
    with pytest.raises(ExecutionError) as excinfo:
        report_from_url4_outcome(_candidate(), _outcome(truncated))
    message = str(excinfo.value)
    assert "truncated" in message
    assert str(len(truncated.encode("utf-8"))) in message
    assert excinfo.value.code == "result_truncated"


def test_invalid_json_without_the_marker_stays_the_generic_error() -> None:
    with pytest.raises(ExecutionError) as excinfo:
        report_from_url4_outcome(_candidate(), _outcome('{"cut mid'))
    assert "must be JSON" in str(excinfo.value)


def test_an_unmaterialized_artifact_outcome_is_refused_loudly() -> None:
    # INVARIANT: results decoding never sees an unredeemed claim ticket; a None body here
    # is a transport bug and must be named as such, not crash as a TypeError.
    with pytest.raises(ExecutionError) as excinfo:
        report_from_url4_outcome(_candidate(), _outcome(None))
    assert "artifact" in str(excinfo.value).casefold()
