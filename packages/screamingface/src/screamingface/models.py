"""Model discovery through the lazy default Client."""

from collections.abc import Sequence

from screamingface._default_client import default_client
from screamingface.discovery import ModelInfo


def list() -> Sequence[ModelInfo]:
    """List Models currently addressable through the configured SF Engine."""

    return default_client().models.list()


__all__ = ["list"]
