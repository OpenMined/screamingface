"""Contract tests for the generated Phase 5D discovery notebook."""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).parents[1] / "examples"
SCRIPTS = Path(__file__).parents[1] / "scripts"
PACKAGE = Path(__file__).parents[1]
REPOSITORY = Path(__file__).parents[3]
NOTEBOOK = EXAMPLES / "02_discovery.ipynb"
GENERATOR = SCRIPTS / "build_discovery.py"


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


def test_discovery_notebook_is_a_generated_output_free_artifact() -> None:
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


def test_discovery_notebook_code_cells_are_valid_python() -> None:
    document = _notebook()
    cells = document["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            source = "".join(cell["source"])
            compile(source, f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_discovery_notebook_teaches_engine_backed_model_filters() -> None:
    code = _sources("code")

    assert "sf.config(engine=ENGINE_URL)" in code
    assert "sf.models.list()" in code
    assert 'sf.models.list(query="gemini")' in code
    assert 'sf.models.list(tools=("web_search",))' in code
    assert "sf.models.list(limit=2)" in code


def test_discovery_notebook_teaches_engine_benchmark_filters() -> None:
    code = _sources("code")

    assert "sf.benchmarks.list()" in code
    assert 'sf.benchmarks.list(query="gpqa")' in code
    assert 'sf.benchmarks.list(tools=("web_search",))' in code
    assert "sf.benchmarks.list(limit=1)" in code


def test_discovery_notebook_loads_only_the_engine_manifest() -> None:
    code = _sources("code")
    markdown = _sources("markdown")

    assert 'gpqa = sf.benchmarks.load("gpqa@1")' in code
    assert "Hugging Face" in markdown
    assert "does not download cases" in markdown
    assert "Docker" in markdown

    # INVARIANT: Discovery never becomes an execution, mock, auth, or private-API tutorial.
    assert "sf.Fusion(" not in code
    assert ".run(" not in code
    assert ".evaluate(" not in code
    assert "httpx" not in code
    assert "aigateway" not in code.lower()
    assert "mock" not in code.lower()
    assert "connect(" not in code
    assert "setup(" not in code
    assert "_profile" not in code
    assert "_DEFINITIONS" not in code


def test_discovery_notebook_explains_the_two_ownership_boundaries() -> None:
    markdown = _sources("markdown")

    assert "configured engine" in markdown
    assert "executable model IDs" in markdown
    assert "benchmark manifests" in markdown
    assert "plain IDs" in markdown
    assert "does not prove that provider credentials are connected" in markdown
    assert "same engine registry" in markdown


def test_discovery_notebook_is_public_and_ci_regenerated() -> None:
    readme = (PACKAGE / "README.md").read_text()
    workflow = (REPOSITORY / ".github/workflows/screamingface-tests.yml").read_text()

    assert "examples/02_discovery.ipynb" in readme
    assert "scripts/build_discovery.py" in readme
    assert "python scripts/check_notebooks.py" in workflow
