"""Subprocess entrypoint for the Runner's single `/benchmark` command route."""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Mapping
from typing import cast

from url4_cloud.benchmarks._types import decode_wire
from url4_cloud.benchmarks.registry import benchmark


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m url4_cloud.benchmarks")
    parser.add_argument(
        "--intent",
        default="",
        help="resolved URL4 intent (the iteration reducer supplies its rows here)",
    )
    args = parser.parse_args(argv)
    try:
        context = sys.stdin.read()
        control = _control(context)
        benchmark_id = _required(control, "benchmark")
        action = _required(control, "action")
        result = benchmark(benchmark_id).execute(action, context, args.intent)
    except (TypeError, ValueError) as exc:
        parser.exit(2, f"benchmark request failed: {exc}\n")
    sys.stdout.write(result)


def _control(value: str) -> Mapping[str, object]:
    decoded = decode_wire(value, "benchmark request")
    if not isinstance(decoded, Mapping):
        raise ValueError("benchmark request must be an object")
    return {
        _unquote(str(name)): _unquote(item) if isinstance(item, str) else item
        for name, item in cast(Mapping[object, object], decoded).items()
    }


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        decoded = ast.literal_eval(value)
        if isinstance(decoded, str):
            return decoded
    return value


def _required(control: Mapping[str, object], name: str) -> str:
    value = control.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"benchmark request {name!r} must be non-blank text")
    return value.strip()


if __name__ == "__main__":  # pragma: no cover - exercised through the subprocess adapter
    main()
