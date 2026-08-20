"""Prepare every immutable asset bundle required by the built-in Benchmark deployment."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from screamingface_engine.benchmarks.builtins import BUILTIN_DEPLOYMENT
from screamingface_engine.benchmarks.registry import DEFAULT_BENCHMARK_ASSETS_ROOT


def prepare_builtin_assets(root: Path) -> tuple[Path, ...]:
    """Build all unique assets declared by the built-in deployment."""

    return BUILTIN_DEPLOYMENT.prepare_assets(root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_BENCHMARK_ASSETS_ROOT)
    args = parser.parse_args(argv)

    prepared = prepare_builtin_assets(args.root)
    print(json.dumps({"root": str(args.root), "bundles": [path.name for path in prepared]}))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    raise SystemExit(main())


__all__ = ["prepare_builtin_assets"]
