"""Verify every generated notebook matches its deterministic Python builder."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path

import nbformat


def main() -> None:
    root = Path(__file__).parents[1]
    pairs = (
        ("build_quickstart.py", "00_quickstart.ipynb"),
        ("build_architecture.py", "01_architecture.ipynb"),
        ("build_discovery.py", "02_discovery.ipynb"),
        ("build_fusions.py", "03_fusions.ipynb"),
        ("build_custom_benchmarks.py", "04_custom_benchmarks.ipynb"),
        ("build_draco_walkthrough.py", "05_draco.ipynb"),
        ("build_connections.py", "06_connections.ipynb"),
    )
    mismatches: list[str] = []
    for builder_name, notebook_name in pairs:
        namespace = runpy.run_path(str(root / "scripts" / builder_name))
        build = namespace["notebook"]
        if not isinstance(build, Callable):
            raise TypeError(f"{builder_name} does not expose notebook()")
        expected = build()
        actual = nbformat.read(root / "examples" / notebook_name, as_version=4)
        if actual != expected:
            mismatches.append(notebook_name)
    if mismatches:
        names = ", ".join(mismatches)
        raise SystemExit(f"generated notebooks are stale: {names}")


if __name__ == "__main__":
    main()
