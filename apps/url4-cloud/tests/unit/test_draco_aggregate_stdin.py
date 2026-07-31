"""The aggregate CLI reads its row array from stdin.

FEATURE: the reducer payload arrives on a pipe, not in argv (gap A1).
STORY: as a researcher running 100 DRACO cases, the ~16,000 verdicts my run produces reach the
scorer — instead of the Job dying at exec with "Argument list too long" at roughly four cases.

Its own module rather than an append to `test_draco_aggregate.py`: prior tests are append-only,
and that module owns the scoring MATH while this one owns the CLI's input channel.

`--args` is kept as an explicit override, so the script stays hand-runnable and the flag this
repo already documented does not disappear under anyone.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from url4_cloud.benchmarks.draco import aggregate as agg

_RUBRIC = {
    "sections": [
        {"id": "Factual Accuracy", "criteria": [{"id": "a1", "weight": 2, "requirement": "x"}]}
    ]
}


@pytest.fixture
def rubrics(tmp_path: Path) -> Path:
    directory = tmp_path / "rubrics"
    directory.mkdir()
    (directory / "1.json").write_text(json.dumps(_RUBRIC), encoding="utf-8")
    return directory


def _row(case: int = 1, status: str = "MET") -> str:
    return "graded: {}".format(
        json.dumps({"case_id": case, "criterion_id": "a1", "criterion_status": status})
    )


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str], stdin: str | None) -> dict:
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    captured: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: captured.append(str(a[0])))
    assert agg.main(argv) == 0
    return json.loads(captured[-1])


def test_payload_is_read_from_stdin(monkeypatch: pytest.MonkeyPatch, rubrics: Path) -> None:
    result = _run(monkeypatch, ["--rubrics", str(rubrics)], json.dumps([_row()]))

    assert result["case_count"] == 1
    assert result["score"] == 1.0


def test_explicit_args_still_overrides_stdin(
    monkeypatch: pytest.MonkeyPatch, rubrics: Path
) -> None:
    """The override wins outright — a half-read of both channels would be unexplainable."""
    result = _run(
        monkeypatch,
        ["--rubrics", str(rubrics), "--args", json.dumps([_row(status="MET")])],
        json.dumps([_row(status="UNMET")]),
    )

    assert result["score"] == 1.0


_CASES = 12
_CRITERIA = 53  # DRACO case 1 has 53, across the paper's four axes
_PASSES = 3  # judge_runs


def test_a_payload_past_the_argv_ceiling_aggregates(
    monkeypatch: pytest.MonkeyPatch, rubrics: Path
) -> None:
    """THE REGRESSION, at DRACO's real shape.

    Sized the way a run actually is — 53 criteria × 3 passes per case — rather than by padding
    to a number, so the ceiling this crosses is the one production crosses.

    TWELVE cases clears `MAX_ARG_STRLEN` (131,072) with the MINIMAL verdict shape used here
    (~75 bytes escaped). Real verdicts carry longer criterion ids, so production crosses it
    sooner — somewhere in the single digits. Either way the old argv handoff died with
    `OSError [Errno 7]` at exec, before the scorer ever started, on a 100-case run.
    """
    wide = {
        "sections": [
            {
                "id": "Factual Accuracy",
                "criteria": [
                    {"id": f"c{n}", "weight": 1, "requirement": "x"} for n in range(_CRITERIA)
                ],
            }
        ]
    }
    for case_id in range(1, _CASES + 1):
        (rubrics / f"{case_id}.json").write_text(json.dumps(wide), encoding="utf-8")

    rows = [
        " ".join(
            json.dumps({"case_id": case, "criterion_id": f"c{n}", "criterion_status": "MET"})
            for _ in range(_PASSES)
            for n in range(_CRITERIA)
        )
        for case in range(1, _CASES + 1)
    ]
    payload = json.dumps(rows)
    assert len(payload) > 131_072, f"payload is only {len(payload)} bytes — not past the ceiling"

    result = _run(monkeypatch, ["--rubrics", str(rubrics)], payload)

    assert result["case_count"] == _CASES
    assert result["failures"] == []
    assert result["metrics"]["n_runs"] == _PASSES
    assert result["score"] == 1.0


def test_unreadable_stdin_payload_is_a_named_failure(
    monkeypatch: pytest.MonkeyPatch, rubrics: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty pipe must not score as an empty-but-successful run."""
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    assert agg.main(["--rubrics", str(rubrics)]) == 1
    assert "not JSON" in capsys.readouterr().err
