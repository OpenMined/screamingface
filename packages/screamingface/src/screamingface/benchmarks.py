"""Benchmark discovery through the lazy default Client."""

from collections.abc import Sequence

from screamingface._default_client import default_client
from screamingface.discovery import BenchmarkInfo


def list() -> Sequence[BenchmarkInfo]:
    """List Benchmarks currently exposed by the configured SF Engine."""

    return default_client().benchmarks.list()


__all__ = ["list"]
