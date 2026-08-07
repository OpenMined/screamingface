"""Validated registry shared by Benchmark discovery and Runner installation."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from types import MappingProxyType

from url4 import Iteration, Node, RelExpr, render
from url4.core.nodes import walk
from url4.peer.server import Url4Node
from url4_cloud.benchmarks.definition import Benchmark

BENCHMARK_ASSETS_ENV = "URL4_BENCHMARK_ASSETS"
DEFAULT_BENCHMARK_ASSETS_ROOT = Path("/opt/benchmarks")


def assets_root(env: Mapping[str, str] | None = None) -> Path:
    """Resolve the immutable asset root once at the Runner composition boundary."""

    selected = os.environ if env is None else env
    return Path(selected.get(BENCHMARK_ASSETS_ENV) or DEFAULT_BENCHMARK_ASSETS_ROOT)


class BenchmarkRegistry:
    """One immutable set of Benchmarks installed on an Engine deployment."""

    __slots__ = ("_benchmarks",)

    def __init__(self, benchmarks: Iterable[Benchmark] = ()) -> None:
        selected: dict[str, Benchmark] = {}
        for benchmark in benchmarks:
            if benchmark.id in selected:
                raise ValueError(f"duplicate Benchmark id {benchmark.id!r}")
            selected[benchmark.id] = benchmark
        self._benchmarks: Mapping[str, Benchmark] = MappingProxyType(selected)

    def __len__(self) -> int:
        return len(self._benchmarks)

    def __iter__(self) -> Iterator[Benchmark]:
        for benchmark_id in sorted(self._benchmarks):
            yield self._benchmarks[benchmark_id]

    def get(self, benchmark_id: str) -> Benchmark | None:
        return self._benchmarks.get(benchmark_id)

    def install(
        self,
        node: Url4Node,
        *,
        assets_root: Path,
    ) -> None:
        """Install and validate every concrete protocol before its first paid request."""

        installed_runtimes: set[str] = set()
        for benchmark in self:
            if benchmark.runtime is not None and benchmark.runtime in installed_runtimes:
                continue
            benchmark.install(node, assets_root)
            if benchmark.runtime is not None:
                installed_runtimes.add(benchmark.runtime)
        declared = frozenset(node.processor_routes())
        for benchmark in self:
            protocol = benchmark.protocol(benchmark.case_count)
            # Rendering at installation catches malformed hand-built ASTs before discovery can
            # publish an expression that the Runner cannot execute.
            render(protocol)
            missing = sorted(_relative_endpoint_paths(protocol) - declared)
            if missing:
                raise ValueError(
                    f"Benchmark {benchmark.id!r} references uninstalled endpoint(s) {missing}"
                )


def _relative_endpoint_paths(protocol: Node) -> set[str]:
    """Collect literal endpoint paths, including those inside iteration templates."""

    found: set[str] = set()
    for child in walk(protocol):
        if isinstance(child, RelExpr):
            found.add(child.path)
        elif isinstance(child, Iteration):
            # Iteration bodies are deliberately lazy URL4 templates, not AST children. They may
            # contain outer bindings that only become concrete per row, so eagerly feeding the
            # body back through ``build`` is both semantically wrong and unable to parse valid
            # nested protocols. Route paths themselves remain literal and can be read lexically.
            for template in (child.body, child.intent, child.reducer):
                if template:
                    found.update(_RELATIVE_ROUTE.findall(template))
    return found


_RELATIVE_ROUTE = re.compile(
    r"(?<![A-Za-z0-9._~$-])(/[A-Za-z0-9._~$-]+(?:/[A-Za-z0-9._~$-]+)*)(?=[?(*])"
)


EMPTY_BENCHMARKS = BenchmarkRegistry()

__all__ = [
    "BENCHMARK_ASSETS_ENV",
    "DEFAULT_BENCHMARK_ASSETS_ROOT",
    "BenchmarkRegistry",
    "EMPTY_BENCHMARKS",
    "assets_root",
]
