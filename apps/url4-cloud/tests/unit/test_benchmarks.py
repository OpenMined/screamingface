from __future__ import annotations

import io
import json

from url4_cloud.benchmarks.__main__ import main


def test_command_entrypoint_reads_reducer_rows_from_url4_intent(monkeypatch, capsys) -> None:
    grade = {
        "case_id": "1",
        "score": 0.75,
        "metrics": {"normalized_score": 0.75, "coverage": 1.0},
        "criteria": [],
    }
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"benchmark": "draco-lite", "action": "aggregate"})),
    )

    main(["--intent", json.dumps([grade])])

    report = json.loads(capsys.readouterr().out)
    assert report["case_count"] == 1
    assert report["score"] == 0.75
