"""Contract tests for the generated Phase 5E Fusion construction notebook."""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).parents[1] / "examples"
SCRIPTS = Path(__file__).parents[1] / "scripts"
PACKAGE = Path(__file__).parents[1]
REPOSITORY = Path(__file__).parents[3]
NOTEBOOK = EXAMPLES / "03_fusions.ipynb"
GENERATOR = SCRIPTS / "build_fusions.py"


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


def test_fusions_notebook_is_a_generated_output_free_artifact() -> None:
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


def test_fusions_notebook_code_cells_are_valid_python() -> None:
    document = _notebook()
    cells = document["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            source = "".join(cell["source"])
            compile(source, f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_fusions_notebook_starts_with_concise_members_and_majority_vote() -> None:
    code = _sources("code")

    assert "SHARED_PROMPT =" in code
    assert '"codex/gpt-5.5"' in code
    assert '"gemini/3.5-flash"' in code
    assert '"claude/sonnet-4.6"' in code
    assert "prompt=SHARED_PROMPT" in code
    assert "reducer=sf.reducers.MajorityVote()" in code


def test_fusions_notebook_uses_mappings_only_for_member_overrides() -> None:
    code = _sources("code")

    assert '"model": "gemini/3.5-flash"' in code
    assert '"prompt": "Check the scientific reasoning and answer directly."' in code
    assert '"params": {"temperature": 0.2, "max_tokens": 512}' in code
    assert "specialist_fusion.models" in code


def test_fusions_notebook_supports_duplicate_models_and_model_reduction() -> None:
    code = _sources("code")

    assert 'SELF_MODEL = "claude/sonnet-4.6"' in code
    assert code.count('"model": SELF_MODEL') == 2
    assert '"temperature": 0.2' in code
    assert '"temperature": 0.8' in code
    assert "reducer=sf.reducers.Model(" in code
    assert 'model="codex/gpt-5.5"' in code
    assert "self_fusion.model_ids" in code


def test_fusions_notebook_inspects_only_the_public_authoring_values() -> None:
    code = _sources("code")
    markdown = _sources("markdown")

    assert "frontier_fusion.models" in code
    assert "frontier_fusion.model_ids" in code
    assert "frontier_fusion.reducer" in code
    assert "frontier_fusion.url4" in code
    assert "stable" in markdown
    assert "one additional model call" in markdown
    assert "string, integer, finite float, or boolean" in markdown
    assert "`tools` is reserved" in markdown
    assert "compatibility is checked when execution begins" in markdown

    # INVARIANT: Authoring stays completely network-free and on the public SDK surface.
    assert "sf.config(" not in code
    assert "sf.models.list(" not in code
    assert "sf.benchmarks" not in code
    assert ".run(" not in code
    assert ".evaluate(" not in code
    assert "httpx" not in code
    assert "yaml" not in code.lower()
    assert "mock" not in code.lower()
    assert "connect(" not in code
    assert "setup(" not in code
    assert "_compiler" not in code
    assert "ENGINE_URL" not in code


def test_fusions_notebook_is_public_and_ci_regenerated() -> None:
    readme = (PACKAGE / "README.md").read_text()
    workflow = (REPOSITORY / ".github/workflows/screamingface-tests.yml").read_text()

    assert "examples/03_fusions.ipynb" in readme
    assert "scripts/build_fusions.py" in readme
    assert "python scripts/build_fusions.py" in workflow
    assert "git diff --exit-code -- examples/03_fusions.ipynb" in workflow
