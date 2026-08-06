"""The shipped IFEval wrapper must match Google's pinned protocol oracle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from url4_cloud.benchmarks.ifeval import grading
from url4_cloud.benchmarks.ifeval.parity import ParityError, verify_prepared_assets
from url4_cloud.benchmarks.ifeval.prepare import build


def _row(key: int, prompt: str, instruction_id: str) -> dict[str, object]:
    return {
        "key": key,
        "prompt": prompt,
        "instruction_id_list": [instruction_id],
        "kwargs": [{}],
    }


def _assets(tmp_path: Path) -> Path:
    build(
        [
            _row(1000, "Answer without commas", "punctuation:no_comma"),
            _row(1001, "Quote the answer", "startend:quotation"),
        ],
        tmp_path,
        expected_count=2,
        expected_instruction_count=2,
    )
    (tmp_path / "nltk_data").mkdir()
    return tmp_path


def test_prepared_cases_match_official_vectors_and_all_global_metrics(tmp_path: Path) -> None:
    summary = verify_prepared_assets(_assets(tmp_path))

    assert summary["parity_cases"] == 2
    assert summary["parity_metrics"] == {
        "prompt_level_strict_accuracy": 1.0,
        "inst_level_strict_accuracy": 1.0,
        "prompt_level_loose_accuracy": 1.0,
        "inst_level_loose_accuracy": 1.0,
    }
    assert len(summary["parity_sha256"]) == 64


def test_parity_proof_fails_if_the_shipped_wrapper_drifts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _assets(tmp_path)
    original = grading.check_case

    def drifted(**kwargs):
        result = original(**kwargs)
        return {"strict": [False for _ in result["strict"]], "loose": result["loose"]}

    monkeypatch.setattr(grading, "check_case", drifted)

    with pytest.raises(ParityError, match="protocol mismatch"):
        verify_prepared_assets(root)


def test_parity_proof_covers_every_prepared_case_id(tmp_path: Path) -> None:
    root = _assets(tmp_path)
    cases = json.loads((root / "cases.json").read_text(encoding="utf-8"))

    assert verify_prepared_assets(root)["parity_cases"] == len(cases)
