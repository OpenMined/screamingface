"""Contract tests for the generated Phase 5F custom-benchmark notebook."""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = Path(__file__).parents[1] / "examples"
SCRIPTS = Path(__file__).parents[1] / "scripts"
PACKAGE = Path(__file__).parents[1]
REPOSITORY = Path(__file__).parents[3]
NOTEBOOK = EXAMPLES / "04_custom_benchmarks.ipynb"
GENERATOR = SCRIPTS / "build_custom_benchmarks.py"


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


def test_custom_benchmarks_notebook_is_a_generated_output_free_artifact() -> None:
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


def test_custom_benchmarks_notebook_code_cells_are_valid_python() -> None:
    document = _notebook()
    cells = document["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, dict) and cell.get("cell_type") == "code":
            source = "".join(cell["source"])
            compile(source, f"{NOTEBOOK.name}:{cell['id']}", "exec")


def test_custom_benchmarks_notebook_builds_three_real_cases() -> None:
    code = _sources("code")

    assert code.count("sf.Case(") == 3
    assert '"astronomy-1"' in code
    assert '"biology-1"' in code
    assert '"physics-1"' in code
    assert 'reference="B"' in code
    assert 'reference="C"' in code
    assert 'reference="A"' in code
    assert 'metadata={"topic": "astronomy"}' in code
    assert 'metadata={"topic": "biology"}' in code
    assert 'metadata={"topic": "physics"}' in code


def test_custom_benchmarks_notebook_builds_the_typed_definition() -> None:
    code = _sources("code")

    assert "benchmark = sf.Benchmark(" in code
    assert '"tiny-science@1"' in code
    assert 'title="Tiny Science"' in code
    assert "cases=cases" in code
    assert "grader=sf.graders.ExactChoice()" in code
    assert "aggregator=sf.aggregators.Mean()" in code
    assert "benchmark.id" in code
    assert "benchmark.title" in code
    assert "benchmark.grader" in code
    assert "benchmark.aggregator" in code
    assert "benchmark.tools" in code
    assert "cases[0].reference" in code

    # INVARIANT: Researchers inspect their own list; the SDK exposes no case-iteration DSL.
    assert "benchmark.cases" not in code
    assert "iter_cases" not in code
    assert "_materialize_cases" not in code


def test_custom_benchmarks_notebook_keeps_loading_and_tools_at_the_right_boundary() -> None:
    code = _sources("code")
    markdown = _sources("markdown")

    assert "def load_cases():" in markdown
    assert "read_my_source()" in markdown
    assert "Researcher-owned loading and cleaning" in markdown
    assert 'tools=("web_search",)' in markdown
    assert "every answer-producing member" in markdown
    assert "ScreamingFace starts at validated `sf.Case` values" in markdown
    assert "reference never enters a model request" in markdown

    assert "read_my_source" not in code
    assert "load_cases" not in code
    assert "sf.benchmarks.load(" not in code


def test_custom_benchmarks_notebook_live_path_is_honest_and_default_off() -> None:
    code = _sources("code")
    markdown = _sources("markdown")

    assert "RUN_LIVE = False" in code
    assert "if RUN_LIVE:" in code
    assert "sf.config(engine=ENGINE_URL)" in code
    assert "fusion = sf.Fusion(" in code
    assert "reducer=sf.reducers.MajorityVote()" in code
    assert "report = fusion.evaluate(benchmark)" in code
    assert "report = None" in code
    assert "nine provider calls" in markdown
    assert "No substitute report" in markdown
    assert "Hugging Face" in markdown

    assert "httpx" not in code
    assert "mock" not in code.lower()
    assert "yaml" not in code.lower()
    assert "_compiler" not in code


def test_custom_benchmarks_notebook_is_public_and_ci_regenerated() -> None:
    readme = (PACKAGE / "README.md").read_text()
    workflow = (REPOSITORY / ".github/workflows/screamingface-tests.yml").read_text()

    assert "examples/04_custom_benchmarks.ipynb" in readme
    assert "scripts/build_custom_benchmarks.py" in readme
    assert "python scripts/check_notebooks.py" in workflow
