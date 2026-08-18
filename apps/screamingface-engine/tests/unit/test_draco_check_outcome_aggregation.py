"""DRACO's 5-pass verdicts must fold into each check's top-level outcome (OME-848).

FEATURE: DRACO grades every criterion with 5 seeded judge passes. The report schema's
contract (documented at the healthbench builder: "Without a top-level outcome the SDK
renders the check as unjudged") expects each check to carry one summary verdict —
DRACO shipped only the 5 raw evidence entries, so every criterion rendered unjudged
and the report view colored chips by criterion sign instead of by verdict.
STORY: as a researcher reading a DRACO case, a criterion my answer met 5/5 shows MET,
a 3/2 split shows the majority, and only a genuinely undecidable criterion (no valid
passes, or a tie among the valid ones) stays outcome-less.
"""

from __future__ import annotations

from typing import Any

from screamingface_engine.benchmarks.draco.case_results import _checks

_RUBRIC = {
    "sections": [
        {
            "id": "axis-a",
            "title": "Axis A",
            "criteria": [
                {"id": "c1", "requirement": "says hi", "weight": 5, "axis": "axis-a"},
                {"id": "c2", "requirement": "avoids jargon", "weight": -2, "axis": "axis-a"},
            ],
        }
    ]
}


def _record(criterion_id: str, criterion_type: str) -> dict[str, Any]:
    return {
        "case_id": 1,
        "criterion_id": criterion_id,
        "requirement": "says hi" if criterion_id == "c1" else "avoids jargon",
        "criterion_type": criterion_type,
    }


def _pass(
    criterion_id: str,
    sequence: int,
    status: str | None,
    *,
    valid: bool = True,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "case_id": 1,
        "criterion_id": criterion_id,
        "sequence": sequence,
        "producer_type": "model",
        "producer_id": "draco/judge",
        "valid": valid,
        "raw_output": "raw",
    }
    if valid:
        value["criterion_status"] = status
        value["explanation"] = "because"
    else:
        value["reason"] = "undecodable"
    return value


def _built(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records = [_record("c1", "positive"), _record("c2", "negative")]
    checks = _checks(1, _RUBRIC, records, evidence, 2)
    return {check["id"]: check for check in checks}


def _five(criterion_id: str, statuses: list[str]) -> list[dict[str, Any]]:
    return [_pass(criterion_id, i + 1, status) for i, status in enumerate(statuses)]


def test_unanimous_passes_summarize_to_their_verdict() -> None:
    checks = _built(
        _five("c1", ["MET"] * 5) + _five("c2", ["UNMET"] * 5),
    )
    assert checks["c1"]["outcome"] == "MET"
    assert checks["c2"]["outcome"] == "UNMET"


def test_a_split_takes_the_majority() -> None:
    # 3/2 splits are exactly what the 5-pass protocol exists to settle.
    checks = _built(
        _five("c1", ["MET", "MET", "UNMET", "MET", "UNMET"])
        + _five("c2", ["UNMET", "MET", "UNMET", "UNMET", "MET"])
    )
    assert checks["c1"]["outcome"] == "MET"
    assert checks["c2"]["outcome"] == "UNMET"


def test_invalid_passes_are_excluded_from_the_majority() -> None:
    # 2 valid MET vs 1 valid UNMET (2 invalid): majority over VALID passes only.
    evidence = [
        _pass("c1", 1, "MET"),
        _pass("c1", 2, None, valid=False),
        _pass("c1", 3, "MET"),
        _pass("c1", 4, None, valid=False),
        _pass("c1", 5, "UNMET"),
    ] + _five("c2", ["UNMET"] * 5)
    checks = _built(evidence)
    assert checks["c1"]["outcome"] == "MET"


def test_a_tie_among_valid_passes_stays_unjudged() -> None:
    # INVARIANT: absence is honesty — a 2-2 tie (one invalid) has no majority, and
    # inventing one would be a verdict nobody rendered.
    evidence = [
        _pass("c1", 1, "MET"),
        _pass("c1", 2, "UNMET"),
        _pass("c1", 3, "MET"),
        _pass("c1", 4, "UNMET"),
        _pass("c1", 5, None, valid=False),
    ] + _five("c2", ["UNMET"] * 5)
    checks = _built(evidence)
    assert "outcome" not in checks["c1"]


def test_no_valid_passes_stays_unjudged() -> None:
    evidence = [_pass("c1", i + 1, None, valid=False) for i in range(5)] + _five(
        "c2", ["UNMET"] * 5
    )
    checks = _built(evidence)
    assert "outcome" not in checks["c1"]


def test_evidence_entries_keep_their_per_pass_verdicts() -> None:
    # The summary is an ADDITION — the 5 raw verdicts stay auditable underneath.
    checks = _built(_five("c1", ["MET"] * 5) + _five("c2", ["UNMET"] * 5))
    assert [item["outcome"] for item in checks["c1"]["evidence"]] == ["MET"] * 5
