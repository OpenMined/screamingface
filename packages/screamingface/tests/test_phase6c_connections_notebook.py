from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK = Path(__file__).parents[1] / "examples" / "06_connections.ipynb"
GENERATOR = Path(__file__).parents[1] / "scripts" / "build_connections.py"
QUICKSTART = Path(__file__).parents[1] / "examples" / "00_quickstart.ipynb"
README = Path(__file__).parents[1] / "README.md"
WORKFLOW = Path(__file__).parents[3] / ".github" / "workflows" / "screamingface-tests.yml"


def _document(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def _sources(path: Path, cell_type: str) -> str:
    cells = _document(path)["cells"]
    assert isinstance(cells, list)
    return "\n".join(
        "".join(cell["source"])
        for cell in cells
        if isinstance(cell, dict) and cell.get("cell_type") == cell_type
    )


def test_connection_guide_is_generated_output_free_and_valid_python() -> None:
    assert GENERATOR.is_file()
    assert NOTEBOOK.is_file()
    document = _document(NOTEBOOK)
    cells = document["cells"]
    assert isinstance(cells, list)
    assert 8 <= len(cells) <= 14
    assert all(isinstance(cell, dict) and cell.get("outputs", []) == [] for cell in cells)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            source = "".join(cell["source"])
            assert cell.get("execution_count") is None
            compile(source, f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_connection_guide_teaches_the_exact_public_boundary_without_secrets() -> None:
    code = _sources(NOTEBOOK, "code")
    markdown = _sources(NOTEBOOK, "markdown")

    assert code.count("sf.connect()") == 1
    assert "sf.connections.list()" in code
    assert "sf.disconnect(" in code
    assert 'sf.connect("codex", method="oauth")' in code
    assert 'sf.connect("gemini", api_key=' in code
    assert "ConnectionRequiredError" in code
    assert "input(" not in code
    assert "getpass" not in code
    assert "AIGATEWAY" not in code
    assert "9105" not in code
    assert "api-key-here" not in code.lower()
    assert "SDK → screamingface-engine → AI Gateway → provider" in markdown
    assert "does not open a browser automatically" in markdown
    assert "Hugging Face" in markdown
    assert "separate" in markdown
    assert "no paid model call" in " ".join(markdown.split()).lower()


def test_quickstart_connects_before_compose_without_losing_its_short_path() -> None:
    code = _sources(QUICKSTART, "code")
    markdown = _sources(QUICKSTART, "markdown")

    assert code.count("sf.connect()") == 1
    assert code.index("sf.connect()") < code.index("sf.Fusion(")
    assert "connect → compose → evaluate → compare" in markdown
    assert "ConnectionRequiredError" in markdown
    assert "AI Gateway starts with an empty provider profile store" in markdown


def test_connection_guide_is_linked_and_regeneration_is_enforced() -> None:
    readme = README.read_text()
    workflow = WORKFLOW.read_text()

    assert "examples/06_connections.ipynb" in readme
    assert "scripts/build_connections.py" in readme
    assert "python scripts/check_notebooks.py" in workflow
