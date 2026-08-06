"""The dev Benchmark image follows the control-plane image into every registry.

FEATURE: Helm-derived Runner images exist wherever the dev control-plane image is published.
STORY: as a dev-cluster operator using ACR, I can submit an Evaluation without its Runner Job
failing at image pull.

The chart derives the default Runner repository by appending ``-benchmark`` to the configured
control-plane repository. That makes registry parity a build-output contract: publishing the base
to ACR while publishing its Benchmark pair only to GHCR renders a valid-looking image reference
that does not exist.
"""

from __future__ import annotations

import re
from pathlib import Path

_WORKFLOW = Path(__file__).resolve().parents[4] / ".github/workflows/dev-build-url4-cloud.yml"


def _benchmark_job() -> str:
    workflow = _WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^  benchmark-image:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)", workflow
    )
    assert match is not None, "the dev workflow no longer declares a benchmark-image job"
    return match.group("body")


def test_the_dev_benchmark_image_is_published_to_ghcr_and_acr() -> None:
    """INVARIANT: a derived Runner repository must name an image the same workflow publishes."""
    job = _benchmark_job()
    suffix = "main-${{ needs.image.outputs.short }}"

    assert "azure/login@v3" in job
    assert "az acr login --name acropenmined" in job
    assert f"ghcr.io/openmined/screamingface-url4-cloud-benchmark:{suffix}" in job
    assert f"acropenmined.azurecr.io/screamingface-url4-cloud-benchmark:{suffix}" in job
