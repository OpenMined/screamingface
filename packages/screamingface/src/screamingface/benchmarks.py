"""Benchmark discovery through the lazy default Client."""

from collections.abc import Sequence

from screamingface._default_client import default_client


def list() -> Sequence[str]:
    """List Benchmark IDs currently exposed by the configured SF Engine."""

    return default_client().benchmarks.list()


__all__ = ["list"]
