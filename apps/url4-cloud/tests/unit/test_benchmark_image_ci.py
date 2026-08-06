"""Pull requests build the same paired image shape that deployment publishes."""

from pathlib import Path

import yaml

_WORKFLOW = Path(__file__).resolve().parents[4] / ".github/workflows/url4-cloud-tests.yml"


def test_pull_request_ci_builds_the_benchmark_image_from_its_pr_base() -> None:
    workflow = yaml.safe_load(_WORKFLOW.read_text())
    image_job = workflow["jobs"]["image"]
    steps = image_job["steps"]
    setup = next(step for step in steps if step.get("uses") == "docker/setup-buildx-action@v4")
    benchmark = next(
        step
        for step in steps
        if step.get("with", {}).get("file") == "apps/url4-cloud/Dockerfile.benchmark"
    )

    assert setup["with"]["driver"] == "docker"
    assert benchmark["uses"] == "docker/build-push-action@v7"
    assert benchmark["with"]["push"] is False
    assert benchmark["with"]["load"] is True
    assert "url4-cloud-ci=docker-image://url4-cloud:ci" in benchmark["with"]["build-contexts"]
    assert "BASE=url4-cloud-ci" in benchmark["with"]["build-args"]
