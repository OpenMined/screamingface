"""Verify every public notebook's authored cells match the deterministic builder."""

from __future__ import annotations

from pathlib import Path

import nbformat
from build_notebooks import notebooks
from nbformat import NotebookNode

_STORY_MARKERS = (
    "sf.Client(",
    "sf.AsyncClient(",
    "sf.models.list()",
    "sf.models.get(",
    "sf.benchmarks.list()",
    "sf.benchmarks.get(",
    "sf.leaderboards.list()",
    "sf.leaderboards.get(",
    "sf.leaderboards.submit(",
    "sf.leaderboards.get_score(",
    "sf.evaluate(published_score.url4)",
    "published_score.url4.to_python()",
    "client.connections.list()",
    "client.connect(",
    "client.disconnect(",
    "hosted.login(",
    "hosted.logout()",
    "sf.Model(",
    "sf.Fusion(",
    "on_event=",
    "progress=True",
    "limit=1",
    "finish_reason",
    ".grade",
    ".checks",
    ".evidence",
    ".failures",
    ".usage",
    ".to_json()",
    "report.export()",
    "sf.ScreamingFaceError",
)

# The presentation notebook is intentionally hand-authored and carries real executed outputs plus
# embedded artwork. The deterministic builder owns the instructional notebooks; this explicit set
# keeps the public directory closed to accidental additions without rewriting presentation state.
_CURATED_NOTEBOOKS = frozenset({"09_demo.ipynb"})


def main() -> None:
    root = Path(__file__).parents[1]
    mismatches: list[str] = []
    expected_notebooks = notebooks()
    actual_names = {path.name for path in (root / "examples").glob("*.ipynb")}
    expected_names = set(expected_notebooks) | _CURATED_NOTEBOOKS
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise SystemExit(f"notebook set mismatch: missing={missing}, unexpected={unexpected}")
    for notebook_name, expected in expected_notebooks.items():
        actual = nbformat.read(root / "examples" / notebook_name, as_version=4)
        # Execution counts, outputs, cell ids, and kernel metadata are notebook-session state.
        # Preserve them when a researcher runs the examples; the checked contract is the ordered
        # cell types and source authored by the builder.
        actual_source = tuple((cell.cell_type, cell.source) for cell in actual.cells)
        expected_source = tuple((cell.cell_type, cell.source) for cell in expected.cells)
        if actual_source != expected_source:
            mismatches.append(notebook_name)
    if mismatches:
        names = ", ".join(mismatches)
        raise SystemExit(f"generated notebooks are stale: {names}")
    _check_public_story(expected_notebooks)


def _check_public_story(values: dict[str, NotebookNode]) -> None:
    authored = "\n".join(cell.source for notebook in values.values() for cell in notebook.cells)
    missing = [marker for marker in _STORY_MARKERS if marker not in authored]
    if missing:
        raise SystemExit(f"notebook story is missing public surface markers: {missing}")
    code = "\n".join(
        cell.source
        for notebook in values.values()
        for cell in notebook.cells
        if cell.cell_type == "code"
    )
    if any(line.strip() == "RUN_EVALUATION = True" for line in code.splitlines()):
        raise SystemExit("public notebooks must not enable paid evaluation by default")


if __name__ == "__main__":
    main()
