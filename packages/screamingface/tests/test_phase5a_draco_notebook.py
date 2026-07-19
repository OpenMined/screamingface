"""Contract tests for the generated Phase 5A DRACO walkthrough."""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK = Path(__file__).parents[1] / "examples" / "05_draco.ipynb"
GENERATOR = Path(__file__).parents[1] / "scripts" / "build_draco_walkthrough.py"


def _notebook() -> dict[str, object]:
    return json.loads(NOTEBOOK.read_text())


def _sources(cell_type: str) -> str:
    document = _notebook()
    cells = document["cells"]
    assert isinstance(cells, list)
    return "\n".join(
        "".join(cell["source"])
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == cell_type
    )


def test_draco_walkthrough_is_generated_from_a_tracked_builder() -> None:
    assert GENERATOR.is_file()
    assert NOTEBOOK.is_file()

    document = _notebook()
    assert document["nbformat"] == 4
    cells = document["cells"]
    assert isinstance(cells, list)
    assert cells
    assert all(isinstance(cell, dict) and cell.get("outputs", []) == [] for cell in cells)
    assert all(
        isinstance(cell, dict) and cell.get("execution_count") is None
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
    )


def test_draco_walkthrough_code_cells_are_valid_python() -> None:
    document = _notebook()
    cells = document["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            source = "".join(cell["source"])
            compile(source, f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_draco_walkthrough_uses_only_the_approved_public_workflow() -> None:
    code = _sources("code")

    assert "sf.config(engine=ENGINE_URL)" in code
    assert 'sf.benchmarks.load("draco@1")' in code
    assert '"gemini/2.5"' in code
    assert '"claude/sonnet-4.6"' in code
    assert "sf.reducers.Model(" in code
    assert 'model="codex/gpt-5.5"' in code
    assert "fusion.url4" in code
    assert "run = fusion.run(benchmark, first=1)" in code
    assert "grades = run.grade()" in code
    assert "report = grades.aggregate()" in code

    # INVARIANT: The teaching notebook never bypasses the SDK's HTTP URL4 boundary.
    assert "aigateway" not in code.lower()
    assert "_compiler" not in code
    assert "compile_fusion" not in code


def test_draco_walkthrough_is_no_spend_and_no_mock_by_default() -> None:
    code = _sources("code")
    markdown = _sources("markdown")

    assert "RUN_LIVE = False" in code
    assert "if RUN_LIVE:" in code
    assert code.index("if RUN_LIVE:") < code.index("run = fusion.run(benchmark, first=1)")
    assert "fusion.evaluate(" not in code
    assert "mock" not in code.lower()
    assert "simulated" not in code.lower()

    assert "hundreds of independent judge requests" in markdown
    assert "does not fabricate a result" in markdown
    assert "full DRACO reproduction" in markdown
    assert "does **not**" in markdown
    assert "fusion.evaluate(benchmark, first=1)" in markdown


def test_draco_walkthrough_explains_the_real_execution_boundary() -> None:
    markdown = _sources("markdown")

    assert "Hugging Face" in markdown
    assert "researcher's Python process" in markdown
    assert "GET /v1?q=<URL-encoded-expression>" in markdown
    assert "plaintext" in markdown
    assert "AI Gateway" in markdown
    assert "SearXNG" in markdown
    assert "deterministic local Python" in markdown
    assert "seven standalone models" in markdown
    assert "nine named fusions" in markdown
