"""Contract tests for the generated Phase 5B quickstart."""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK = Path(__file__).parents[1] / "examples" / "00_quickstart.ipynb"
GENERATOR = Path(__file__).parents[1] / "scripts" / "build_quickstart.py"


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


def test_quickstart_is_a_generated_output_free_notebook() -> None:
    assert GENERATOR.is_file()
    assert NOTEBOOK.is_file()

    document = _notebook()
    assert document["nbformat"] == 4
    cells = document["cells"]
    assert isinstance(cells, list)
    assert 7 <= len(cells) <= 10
    assert all(isinstance(cell, dict) and cell.get("outputs", []) == [] for cell in cells)
    assert all(
        isinstance(cell, dict) and cell.get("execution_count") is None
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
    )


def test_quickstart_code_cells_are_valid_python() -> None:
    document = _notebook()
    cells = document["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            source = "".join(cell["source"])
            compile(source, f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_quickstart_is_the_minimal_public_compose_evaluate_compare_flow() -> None:
    code = _sources("code")

    assert "import screamingface as sf" in code
    assert code.count("sf.Fusion(") == 1
    assert '"codex/gpt-5.5"' in code
    assert '"gemini/2.5-flash"' in code
    assert '"claude/sonnet-4.6"' in code
    assert code.count("sf.reducers.MajorityVote()") == 1
    assert code.count('fusion.evaluate("gpqa@1", first=5)') == 1
    assert "# Equivalent staged API:" in code
    assert '# benchmark = sf.benchmarks.load("gpqa@1")' in code
    assert "# run = fusion.run(benchmark, first=5)" in code
    assert "# grades = run.grade()" in code
    assert "# report = grades.aggregate()" in code
    assert code.rstrip().endswith("report")

    # INVARIANT: Deep execution and discovery APIs do not leak into the shortest path.
    assert "sf.models.list" not in code
    assert "fusion.url4" not in code
    assert "_compiler" not in code
    assert "httpx" not in code


def test_quickstart_is_safe_and_honest_by_default() -> None:
    code = _sources("code")
    markdown = _sources("markdown")

    assert "RUN_LIVE" not in code
    assert "if report" not in code
    assert "sf.config(" not in code
    assert "ENGINE_URL" not in code
    assert "mock" not in code.lower()
    assert "simulated" not in code.lower()

    assert "15 model calls" in markdown
    assert "compose → evaluate → compare" in markdown
    assert "Hugging Face" in markdown
    assert "provider credentials" in markdown
    assert "empty provider profile store" in markdown
    assert "authentication" in markdown
    assert "failures" in markdown
    assert "./dev.sh" in markdown
    assert "## Recap" not in markdown


def test_quickstart_keeps_architecture_details_out_of_the_main_path() -> None:
    markdown = _sources("markdown")

    assert "score" in markdown
    assert "baseline" in markdown
    assert "gain" in markdown
    assert "GET /v1" not in markdown
    assert ".well-known" not in markdown
    assert "plaintext" not in markdown
    assert "screamingface.fusion-result" not in markdown
    assert "run → grade → aggregate" not in markdown
