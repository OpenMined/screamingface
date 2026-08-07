"""Test-only composition helper for the installed benchmark registry."""

from collections.abc import Collection
from pathlib import Path

from url4.peer.server import Url4Node
from url4_cloud.benchmarks import BENCHMARKS
from url4_cloud.benchmarks.candidate import install_candidate_invocation
from url4_cloud.benchmarks.draco.definition import JUDGE_MODEL

_DEFAULT_MODEL_ROUTES = (f"/{JUDGE_MODEL}",)


def _unused_model(_request: object) -> str:
    raise AssertionError("the test did not provide a model implementation")


def install_benchmarks(
    node: Url4Node,
    root: Path,
    *,
    model_routes: Collection[str] = (),
) -> None:
    for route in dict.fromkeys((*_DEFAULT_MODEL_ROUTES, *model_routes)):
        if route not in node.processor_routes():
            node.endpoint(route)(_unused_model)
    install_candidate_invocation(node)
    BENCHMARKS.install(node, assets_root=root)


__all__ = ["install_benchmarks"]
