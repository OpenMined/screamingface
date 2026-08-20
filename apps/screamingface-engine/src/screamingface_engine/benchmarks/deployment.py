"""Compose runtime Benchmarks with the immutable assets their deployment requires."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from screamingface_engine.benchmarks.definition import Benchmark
from screamingface_engine.benchmarks.registry import BenchmarkRegistry

type BenchmarkAssetPreparer = Callable[[Path], None]

_ASSET_BUNDLE_ID = re.compile(r"[a-z0-9][a-z0-9._-]*")


@dataclass(frozen=True, slots=True)
class BenchmarkAssetBundle:
    """One physical directory of immutable assets, shared by one or more Benchmarks."""

    id: str
    prepare: BenchmarkAssetPreparer

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or _ASSET_BUNDLE_ID.fullmatch(self.id) is None:
            raise ValueError("BenchmarkAssetBundle id must be one lowercase path-safe identifier")
        if not callable(self.prepare):
            raise TypeError("BenchmarkAssetBundle prepare must be callable")


@dataclass(frozen=True, slots=True)
class BenchmarkRegistration:
    """One runtime Benchmark plus every asset bundle it requires.

    ``assets`` deliberately has no default: an assetless Benchmark must say ``assets=()`` so a
    forgotten preparation declaration cannot look like an intentional no-assets protocol.
    """

    benchmark: Benchmark
    assets: tuple[BenchmarkAssetBundle, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark, Benchmark):
            raise TypeError("BenchmarkRegistration benchmark must be a Benchmark")
        if not isinstance(self.assets, tuple):
            raise TypeError("BenchmarkRegistration assets must be a tuple")
        selected: set[str] = set()
        for bundle in self.assets:
            if not isinstance(bundle, BenchmarkAssetBundle):
                raise TypeError("BenchmarkRegistration assets must contain BenchmarkAssetBundles")
            if bundle.id in selected:
                raise ValueError(
                    f"Benchmark {self.benchmark.id!r} declares asset bundle {bundle.id!r} twice"
                )
            selected.add(bundle.id)


class BenchmarkDeployment:
    """One validated deployment of Benchmarks and their build-time assets.

    The runtime consumes ``benchmarks``. The benchmark-image build calls ``prepare_assets``.
    Both views derive from the same registrations, so the image cannot advertise a Benchmark
    whose asset requirement was omitted from a parallel Dockerfile list.
    """

    __slots__ = ("_asset_bundles", "_benchmarks", "_registrations")

    def __init__(self, registrations: Iterable[BenchmarkRegistration]) -> None:
        selected = tuple(registrations)
        self._registrations = selected
        self._benchmarks = BenchmarkRegistry(registration.benchmark for registration in selected)

        bundles: dict[str, BenchmarkAssetBundle] = {}
        for registration in selected:
            for bundle in registration.assets:
                installed = bundles.get(bundle.id)
                if installed is not None and installed is not bundle:
                    raise ValueError(f"conflicting BenchmarkAssetBundles declare id {bundle.id!r}")
                bundles[bundle.id] = bundle
        self._asset_bundles = tuple(bundles[bundle_id] for bundle_id in sorted(bundles))

    @property
    def benchmarks(self) -> BenchmarkRegistry:
        """The runtime registry derived from this deployment's registrations."""

        return self._benchmarks

    @property
    def registrations(self) -> tuple[BenchmarkRegistration, ...]:
        """The immutable composition declarations, exposed for deployment audits."""

        return self._registrations

    def prepare_assets(self, root: Path) -> tuple[Path, ...]:
        """Prepare every unique required bundle beneath ``root``, in stable ID order."""

        root.mkdir(parents=True, exist_ok=True)
        prepared: list[Path] = []
        for bundle in self._asset_bundles:
            out = root / bundle.id
            out.mkdir(parents=True, exist_ok=True)
            bundle.prepare(out)
            prepared.append(out)
        return tuple(prepared)


__all__ = [
    "BenchmarkAssetBundle",
    "BenchmarkAssetPreparer",
    "BenchmarkDeployment",
    "BenchmarkRegistration",
]
