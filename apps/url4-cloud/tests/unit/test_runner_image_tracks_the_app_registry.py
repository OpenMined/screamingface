"""A mirrored registry must carry the Runner Job image with it.

FEATURE: Runner Jobs run the benchmark image while the control plane runs the plain engine image.
STORY: as an operator mirroring this chart into a private or airgapped registry, I set my
registry once and both images come from it.

`runner.image.repository` carried the full public path as its DEFAULT, so `$override.repository`
was always truthy and the helper's `| default .Values.image.repository` fallback was unreachable.
Overriding `image.repository` alone therefore moved the control plane to the private registry and
left every Runner Job pointing at ghcr.io. The control plane installs cleanly; the failure waits
until the first submitted run and surfaces as ImagePullBackOff on a Job, one indirection away
from the value that caused it.

MEASURED before the fix, with `--set image.repository=registry.internal/url4-cloud`
and `--set image.tag=1.2.3`:

    URL4_CLOUD_RUNNER_IMAGE: "ghcr.io/openmined/screamingface-url4-cloud-benchmark:1.2.3"

INVARIANT: the runner image is the app image's repository plus the `-benchmark` suffix, unless an
operator names one explicitly. That keeps `186271ca`'s decision — a Runner defaults to a benchmark
image, because the plain engine image declares no `[data]` routes — while making it travel with
the registry rather than being welded to one.

These render the REAL chart with `helm template` rather than reasoning about the template text: a
lookalike of Helm's `default` semantics would prove nothing about what actually gets deployed.
Skipped where no helm binary exists, so the stack's gate still runs without one.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_CHART = Path(__file__).resolve().parents[2] / "deploy" / "helm"
_RUNNER_IMAGE_RE = re.compile(r'URL4_CLOUD_RUNNER_IMAGE:\s*"([^"]+)"')

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None, reason="helm binary not available in this environment"
)


def _render(**overrides: str) -> str:
    # natsUrl is required whenever the bundled NATS subchart is off, which it is by default.
    args = ["helm", "template", "t", str(_CHART), "--set", "config.natsUrl=nats://x:4222"]
    for key, value in overrides.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def _runner_image(**overrides: str) -> str:
    match = _RUNNER_IMAGE_RE.search(_render(**overrides))
    assert match is not None, "the chart no longer renders URL4_CLOUD_RUNNER_IMAGE"
    return match.group(1)


def test_the_runner_image_follows_a_mirrored_registry() -> None:
    """The headline: one override moves BOTH images."""
    image = _runner_image(image__repository="registry.internal/url4-cloud", image__tag="1.2.3")

    assert image == "registry.internal/url4-cloud-benchmark:1.2.3"


def test_the_default_runner_image_is_still_the_benchmark_image() -> None:
    """INVARIANT from `186271ca`: a Runner exists to execute a benchmark, and the plain engine
    image declares no `[data]` routes — so the working configuration must be the one you get by
    not thinking. Deriving the repository must not quietly undo that."""
    repository, _, _tag = _runner_image(image__tag="9.9.9").rpartition(":")

    assert repository.endswith("-benchmark")


def test_the_control_plane_image_is_never_the_benchmark_image() -> None:
    """INVARIANT: the benchmark image bakes in the private weighted rubrics — the answer key —
    and the control plane is the process that terminates CLIENT connections. Deriving one
    repository from the other must keep them two images, not collapse them into one."""
    image = _runner_image(image__repository="registry.internal/url4-cloud", image__tag="1.2.3")

    assert image != "registry.internal/url4-cloud:1.2.3"
    assert "-benchmark" in image


def test_an_explicit_runner_repository_still_wins() -> None:
    """The escape hatch stays: an operator whose benchmark image is not `<app>-benchmark` names
    it, and the derivation gets out of the way."""
    image = _runner_image(
        image__repository="registry.internal/url4-cloud",
        image__tag="1.2.3",
        runner__image__repository="elsewhere.internal/custom-bench",
    )

    assert image == "elsewhere.internal/custom-bench:1.2.3"


def test_the_runner_tag_still_tracks_the_app_tag() -> None:
    """Unchanged: engine and dataset stay on one version, so a published score can name the
    engine that produced it."""
    image = _runner_image(image__repository="registry.internal/url4-cloud", image__tag="4.5.6")

    assert image.endswith(":4.5.6")
