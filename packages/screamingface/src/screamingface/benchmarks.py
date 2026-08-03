"""Benchmark discovery through the lazy default Client."""

from collections.abc import Sequence

from screamingface._default_client import default_client
from screamingface.discovery import Benchmark


def list() -> Sequence[Benchmark]:
    """List the Benchmarks currently exposed by the configured SF Engine."""

    return default_client().benchmarks.list()


def get(benchmark_id: str, *, method: str | None = None) -> Benchmark:
    """Fetch one Benchmark's identity card by its catalog id.

    ``method`` selects a protocol variant's identity (e.g. ifeval's
    ``"single_pass"``); ``None`` shows the Benchmark's default method.
    """

    return default_client().benchmarks.get(benchmark_id, method=method)


__all__ = ["get", "list"]
