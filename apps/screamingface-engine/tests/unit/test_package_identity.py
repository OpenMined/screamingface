"""The distribution, the import package and the console scripts carry the Engine's name (OME-876).

FEATURE: the repo-side identity of the Engine app matches the product name already used in Linear
and in the published image prefix.

STORY: as a developer I run `screamingface-engine serve --local` and import `screamingface_engine`,
and neither name mentions url4-cloud.

WHY the legacy aliases are asserted too: the cluster is live. During a rolling upgrade an App pod
running the OLD code schedules the NEW image, and the image reference comes from a ConfigMap while
the command comes from Python — so the two change at different moments. Keeping the old script
names resolvable makes that window survivable in both directions. They are removable one release
after this ships; `OME-877` carries that.

AIDEV-NOTE: read through `importlib.metadata` rather than by parsing pyproject.toml, so this
asserts what was actually INSTALLED. A pyproject edit that never made it into the venv is exactly
the failure this should catch.
"""

from __future__ import annotations

from importlib.metadata import distribution, entry_points

_DISTRIBUTION = "screamingface-engine"
_PACKAGE = "screamingface_engine"


def test_the_distribution_is_named_for_the_engine() -> None:
    """The installed distribution answers to the new name."""
    assert distribution(_DISTRIBUTION).metadata["Name"] == _DISTRIBUTION


def test_the_import_package_is_named_for_the_engine() -> None:
    """The import package is importable under the new name."""
    module = __import__(_PACKAGE)
    assert module.__name__ == _PACKAGE


def test_the_console_scripts_point_at_the_engine_package() -> None:
    """Both modes are reachable under the new script name, and both target the new package."""
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}

    assert scripts.get("screamingface-engine") == f"{_PACKAGE}.cli:main"
    assert scripts.get("screamingface-engine-runner") == f"{_PACKAGE}.runner.main:main"


def test_the_legacy_console_scripts_still_resolve() -> None:
    """The old names survive this release for the rolling-upgrade window.

    INVARIANT: these two entries may only be removed once no App pod running the previous release
    can still schedule this image. Deleting them in the same release as the rename reintroduces
    the skew they exist to absorb.
    """
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}

    assert scripts.get("url4-cloud") == f"{_PACKAGE}.cli:main"
    assert scripts.get("url4-cloud-runner") == f"{_PACKAGE}.runner.main:main"
