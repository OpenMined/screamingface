"""Public IFEval notebook contracts.

FEATURE: OME-732 provider-stable first run.
STORY: As a researcher I can run notebook 07 from top to bottom before opting into a
provider-sensitive research configuration.
"""

from __future__ import annotations

from pathlib import Path

import nbformat

_NOTEBOOK = Path(__file__).parents[1] / "examples/07_ifeval_e2e.ipynb"


def _code_cells() -> tuple[str, ...]:
    notebook = nbformat.read(_NOTEBOOK, as_version=4)
    return tuple(cell.source for cell in notebook.cells if cell.cell_type == "code")


def test_required_ifeval_smoke_is_provider_stable_and_one_case() -> None:
    cells = _code_cells()
    required_evaluations = tuple(
        source
        for source in cells
        if "sf.evaluate(" in source and "if RUN_KIMI_RESEARCH:" not in source
    )

    # INVARIANT: one explicit opt-in exercises all four protocol shapes without Kimi K3.
    assert len(required_evaluations) == 4
    assert all("limit=1" in source for source in required_evaluations)
    assert all("progress=True" in source for source in required_evaluations)
    assert all("if RUN_EVALUATION" in source for source in required_evaluations)
    assert any(
        "smoke_model," in source and 'benchmark="ifeval",' in source
        for source in required_evaluations
    )
    assert any(
        "smoke_fusion," in source and 'benchmark="ifeval",' in source
        for source in required_evaluations
    )
    assert any(
        "smoke_model," in source and 'benchmark="ifeval/self-corrective",' in source
        for source in required_evaluations
    )
    assert any(
        "smoke_fusion," in source and 'benchmark="ifeval/verifying-ensemble",' in source
        for source in required_evaluations
    )
    assert all("kimi" not in source.lower() for source in required_evaluations)


def test_kimi_research_grid_is_explicitly_opt_in() -> None:
    cells = _code_cells()
    kimi_configuration = tuple(source for source in cells if "kimi-k3" in source)
    kimi_evaluations = tuple(
        source for source in cells if "sf.evaluate(" in source and "kimi" in source.lower()
    )

    assert len(kimi_configuration) == 1
    assert "RUN_KIMI_RESEARCH = False" in kimi_configuration[0]
    assert kimi_evaluations
    assert all("if RUN_KIMI_RESEARCH:" in source for source in kimi_evaluations)
