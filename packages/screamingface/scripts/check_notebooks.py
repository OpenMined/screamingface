"""Verify every public notebook's authored cells match the deterministic builder."""

from __future__ import annotations

from pathlib import Path

import nbformat
from build_notebooks import notebooks


def main() -> None:
    root = Path(__file__).parents[1]
    mismatches: list[str] = []
    expected_notebooks = notebooks()
    actual_names = {path.name for path in (root / "examples").glob("*.ipynb")}
    if actual_names != set(expected_notebooks):
        missing = sorted(set(expected_notebooks) - actual_names)
        unexpected = sorted(actual_names - set(expected_notebooks))
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


if __name__ == "__main__":
    main()
