"""Benchmark asset preparation is immutable and participates in Benchmark identity."""

from pathlib import Path

from url4_cloud.benchmarks.draco.definition import (
    DATASET_PREPARER_REVISION as DRACO_PREPARER_REVISION,
)
from url4_cloud.benchmarks.ifeval.definition import (
    DATASET_PREPARER_REVISION as IFEVAL_PREPARER_REVISION,
)

_DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile.benchmark"


def test_benchmark_image_pins_the_declared_asset_preparer() -> None:
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")

    assert DRACO_PREPARER_REVISION == IFEVAL_PREPARER_REVISION
    version = DRACO_PREPARER_REVISION.removeprefix("datasets-")
    assert f'"datasets=={version}"' in dockerfile
    assert "uv:python3.12-bookworm-slim@sha256:" in dockerfile
