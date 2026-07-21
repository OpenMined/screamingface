"""Contract tests for the generated concise DRACO Preview notebook."""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK = Path(__file__).parents[1] / "examples" / "05_draco.ipynb"
GENERATOR = Path(__file__).parents[1] / "scripts" / "build_draco_walkthrough.py"


def _notebook() -> dict[str, object]:
    return json.loads(NOTEBOOK.read_text())


def _sources(cell_type: str) -> str:
    cells = _notebook()["cells"]
    assert isinstance(cells, list)
    return "\n".join(
        "".join(cell["source"])
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == cell_type
    )


def test_draco_preview_is_generated_concise_and_output_free() -> None:
    assert GENERATOR.is_file()
    assert NOTEBOOK.is_file()

    document = _notebook()
    assert document["nbformat"] == 4
    cells = document["cells"]
    assert isinstance(cells, list)
    assert len(cells) == 9
    assert all(isinstance(cell, dict) and cell.get("outputs", []) == [] for cell in cells)
    assert all(
        isinstance(cell, dict) and cell.get("execution_count") is None
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
    )


def test_draco_preview_code_cells_are_valid_python() -> None:
    cells = _notebook()["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            compile("".join(cell["source"]), f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_draco_preview_matches_the_quickstart_public_workflow() -> None:
    code = _sources("code")
    markdown = _sources("markdown")

    assert "sf.connect()" in code
    assert 'sf.Model(\n    "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra"' in code
    assert 'sf.Model(\n    "huggingface/zai-org/GLM-5.2~deepinfra"' in code
    assert "prompt=EVIDENCE_PROMPT" in code
    assert "prompt=CHALLENGE_PROMPT" in code
    assert "sf.reducers.Model(" in code
    assert 'model="codex/gpt-5.5"' in code
    assert 'report = fusion.evaluate("draco-preview@1", first=1)' in code
    assert '# benchmark = sf.benchmarks.load("draco-preview@1")' in code
    assert "# run = fusion.run(benchmark, first=1)" in code
    assert "# grades = run.grade()" in code
    assert "# report = grades.aggregate()" in code

    assert markdown.index("## Before you run it") < markdown.index("## 1 · Connect")
    assert "## 1 · Connect" in markdown
    assert "## 2 · Compose" in markdown
    assert "## 3 · Evaluate" in markdown
    assert "## 4 · Compare" in markdown

    # INVARIANT: The teaching notebook never bypasses the SDK's HTTP URL4 boundary.
    assert "aigateway" not in code.lower()
    assert "_compiler" not in code
    assert "compile_recipe" not in code


def test_draco_preview_puts_every_material_caveat_before_execution() -> None:
    markdown = _sources("markdown")

    assert "not canonical `draco@1`" in markdown
    assert "Preview must not be presented\nas a DRACO score" in markdown
    assert "real DRACO" in markdown
    assert "Hugging Face" in markdown
    assert "researcher" not in markdown.lower()
    assert "at least six\nmodel calls" in markdown
    assert "about 354 judge" in markdown
    assert "two Hugging Face calls are independent" in markdown
    assert "Codex is the tool-free model reducer" in markdown
    assert "Gemini 2.5 Flash is used only as the tool-free judge" in markdown
    assert "Tavily" in markdown
    assert "OpenRouter" in markdown
    assert "OME-428" in markdown
    assert "GET /v1?q=<URL-encoded-expression>" in markdown
    assert "Only the\nengine contacts AI Gateway" in markdown
    assert "live progress panel" in markdown


def test_draco_preview_has_no_mock_or_default_off_control_flow() -> None:
    code = _sources("code")

    assert "RUN_PREVIEW" not in code
    assert "if RUN" not in code
    assert "mock" not in code.lower()
    assert "simulated" not in code.lower()
    assert "canonical_draco_pass_1" not in code
    assert "first_fusion_verdict" not in code
