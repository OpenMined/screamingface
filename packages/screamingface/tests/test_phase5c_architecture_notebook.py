"""Contract tests for the generated Phase 5C architecture notebook."""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).parents[1] / "examples"
SCRIPTS = Path(__file__).parents[1] / "scripts"
NOTEBOOK = EXAMPLES / "01_architecture.ipynb"
GENERATOR = SCRIPTS / "build_architecture.py"


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


def test_architecture_notebook_replaces_the_phase1_development_walkthrough() -> None:
    assert GENERATOR.is_file()
    assert NOTEBOOK.is_file()
    assert not (EXAMPLES / "phase_1_engine_profile.ipynb").exists()
    assert not (SCRIPTS / "build_phase1_engine_profile.py").exists()

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


def test_architecture_notebook_code_cells_are_valid_python() -> None:
    document = _notebook()
    cells = document["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            source = "".join(cell["source"])
            compile(source, f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_architecture_notebook_shows_configuration_registry_and_recipe() -> None:
    code = _sources("code")

    assert "sf.config(engine=ENGINE_URL)" in code
    assert 'f"{ENGINE_URL}/.well-known/screamingface"' in code
    assert "registry_response.text" in code
    assert "json.loads(registry_response.text)" in code
    assert "sf.models.list()" in code
    assert code.count("sf.Fusion(") == 1
    assert "fusion.url4" in code


def test_architecture_notebook_uses_public_url4_builders_for_one_real_get() -> None:
    code = _sources("code")

    assert "from url4 import Expression, RelExpr, render, src, struct" in code
    assert 'path="/reducers/majority-vote"' in code
    assert 'name="member_answers"' in code
    assert 'name="recipe_answer"' in code
    assert 'httpx.Request("GET", f"{ENGINE_URL}/v1", params={"q": expression})' in code
    assert "client.send(request)" in code
    assert "response.text" in code
    assert "json.loads(response.text)" in code

    # INVARIANT: This proof never reaches a model, provider, dataset, or private implementation.
    assert "fusion.run(" not in code
    assert "fusion.evaluate(" not in code
    assert "sf.benchmarks" not in code
    assert "aigateway" not in code.lower()
    assert "_compiler" not in code
    assert "Url4Node" not in code


def test_architecture_notebook_explains_the_approved_ownership_boundary() -> None:
    markdown = _sources("markdown")

    assert "Researcher process" in markdown
    assert "ScreamingFace SDK" in markdown
    assert "screamingface-engine" in markdown
    assert "AI Gateway" in markdown
    assert "Tavily" in markdown
    assert "Benchmark source and references" in markdown
    assert "Exact grading and aggregation" in markdown
    assert "GET /v1?q=<encoded URL4 expression>" in markdown
    assert "plaintext" in markdown
    assert "No provider credentials" in markdown
    assert "does not load a benchmark" in markdown
