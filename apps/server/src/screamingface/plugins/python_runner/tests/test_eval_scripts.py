"""Integration tests: real eval scripts run through run_script_main.

Exercises the ACTUAL committed eval_scripts/check_correct.py and
eval_scripts/calculate_accuracy.py byte-for-byte, confirming that
run_script_main correctly imports them as modules (skipping their
__main__ self-test) and calls main() with introspected kwargs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from screamingface.plugins.python_runner.runner import run_script_main


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "eval_scripts").is_dir():
            return parent
    raise RuntimeError("eval_scripts/ not found above test file")


CHECK = (_repo_root() / "eval_scripts" / "check_correct.py").read_text()
ACC = (_repo_root() / "eval_scripts" / "calculate_accuracy.py").read_text()


@pytest.mark.asyncio
async def test_real_check_correct_match_ignores_extra_keys():
    # payload carries question/expected (for the eval-runs hook) AND
    # correct_answer/consensus (for main); main() gets only its two params.
    out = await run_script_main(
        CHECK,
        {"question": "q", "expected": "Paris", "correct_answer": "Paris", "consensus": " paris "},
    )
    assert out["correct"] is True
    assert out["predicted"] == "paris"  # consensus, stripped
    assert out["ground_truth"] == "Paris"


@pytest.mark.asyncio
async def test_real_check_correct_mismatch():
    out = await run_script_main(CHECK, {"correct_answer": "Paris", "consensus": "London"})
    assert out["correct"] is False


@pytest.mark.asyncio
async def test_real_calculate_accuracy_bare_array():
    rows = [
        {"correct": True, "predicted": "A"},
        {"correct": False, "predicted": "B"},
        {"correct": True, "predicted": "C"},
        {"error": {"kind": "Timeout"}},  # on_error=collect element — excluded from denominator
    ]
    out = await run_script_main(ACC, rows)  # bare list -> single-param main(checks)
    assert out["n"] == 3 and out["n_correct"] == 2 and out["n_errors"] == 1
    assert abs(out["accuracy_pct"] - 66.67) < 0.01
