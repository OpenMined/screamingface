"""Concrete Benchmarks and immutable assets selected by this Engine deployment."""

from pathlib import Path

from screamingface_engine.benchmarks.deployment import (
    BenchmarkAssetBundle,
    BenchmarkDeployment,
    BenchmarkRegistration,
)
from screamingface_engine.benchmarks.draco.definition import (
    ASSET_BUNDLE_ID as DRACO_ASSET_BUNDLE_ID,
)
from screamingface_engine.benchmarks.draco.definition import DRACO, DRACO_3PASS
from screamingface_engine.benchmarks.healthbench.definition import (
    HEALTHBENCH_PROFESSIONAL,
    HEALTHBENCH_WORST30,
)
from screamingface_engine.benchmarks.healthbench.exam import (
    ASSET_BUNDLE_ID as HEALTHBENCH_ASSET_BUNDLE_ID,
)
from screamingface_engine.benchmarks.ifeval.definition import (
    ASSET_BUNDLE_ID as IFEVAL_ASSET_BUNDLE_ID,
)
from screamingface_engine.benchmarks.ifeval.definition import IFEVAL


def _prepare_draco(out: Path) -> None:
    # WHY lazy: image-building code and its optional dataset dependency stay out of the runtime
    # import graph. The deployment carries the adapter, but imports it only when building assets.
    from screamingface_engine.benchmarks.draco.prepare import prepare

    prepare(out)


def _prepare_ifeval(out: Path) -> None:
    from screamingface_engine.benchmarks.ifeval.prepare import prepare

    prepare(out)


def _prepare_healthbench(out: Path) -> None:
    from screamingface_engine.benchmarks.healthbench.prepare import prepare

    prepare(out)


DRACO_ASSETS = BenchmarkAssetBundle(id=DRACO_ASSET_BUNDLE_ID, prepare=_prepare_draco)
IFEVAL_ASSETS = BenchmarkAssetBundle(id=IFEVAL_ASSET_BUNDLE_ID, prepare=_prepare_ifeval)
HEALTHBENCH_ASSETS = BenchmarkAssetBundle(
    id=HEALTHBENCH_ASSET_BUNDLE_ID,
    prepare=_prepare_healthbench,
)

# WHY: this composition is the single source for both runtime discovery and image construction.
# Boards that read one physical asset set intentionally share a bundle and the deployment
# prepares it once: the two HealthBench boards are independent identities over one baked
# answer key, and the two DRACO boards re-run the same archived case/rubric assets with
# different judge-pass counts.
BUILTIN_DEPLOYMENT = BenchmarkDeployment(
    (
        BenchmarkRegistration(benchmark=DRACO, asset_bundle=DRACO_ASSETS),
        BenchmarkRegistration(benchmark=DRACO_3PASS, asset_bundle=DRACO_ASSETS),
        BenchmarkRegistration(benchmark=IFEVAL, asset_bundle=IFEVAL_ASSETS),
        BenchmarkRegistration(
            benchmark=HEALTHBENCH_WORST30,
            asset_bundle=HEALTHBENCH_ASSETS,
        ),
        BenchmarkRegistration(
            benchmark=HEALTHBENCH_PROFESSIONAL,
            asset_bundle=HEALTHBENCH_ASSETS,
        ),
    )
)
BUILTIN_BENCHMARKS = BUILTIN_DEPLOYMENT.benchmarks

__all__ = ["BUILTIN_BENCHMARKS", "BUILTIN_DEPLOYMENT"]
