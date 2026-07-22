"""The core import graph stays framework-free.

STORY: as a library consumer I `import url4` in a process that has no web
framework — and in one that does — and either way the import pulls in no
server machinery. Serving is opt-in via the `url4[server]` extra, reached
lazily inside `_serve_forever` / `Url4Node.serve`.

# AIDEV-NOTE: this ran as a SUBPROCESS on purpose. Asserting against the test
# process's own `sys.modules` would be worthless — pytest, the conftest and
# sibling test modules have already imported plenty by then. A clean
# interpreter is the only place the claim means anything.
#
# The guarantee only has teeth when a framework is actually installed: with no
# uvicorn on the path, "url4 did not import uvicorn" is true for the boring
# reason. CI runs this suite in both configurations (see url4-tests.yml — the
# `test` job without the extra, the `serve` job with it) so the strong form is
# exercised too.
"""

from __future__ import annotations

import subprocess
import sys

_FRAMEWORKS = ("uvicorn", "starlette", "fastapi", "flask", "django")


def _loaded_after_import(module: str, watch: tuple[str, ...]) -> set[str]:
    """Which of ``watch`` are in `sys.modules` after importing ``module``, fresh.

    Reported as top-level names — a submodule (``json.decoder``) counts as its
    package, so the result is a clean set of "what got pulled in".
    """
    code = (
        f"import {module}, sys;"
        f"print(' '.join(sorted({{n.split('.')[0] for n in sys.modules}} & set({watch!r}))))"
    )
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell, test-controlled input
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(done.stdout.split())


def test_importing_url4_pulls_in_no_web_framework() -> None:
    assert _loaded_after_import("url4", _FRAMEWORKS) == set()


def test_importing_url4_dag_pulls_in_no_web_framework() -> None:
    assert _loaded_after_import("url4.dag", _FRAMEWORKS) == set()


def test_importing_the_cli_pulls_in_no_web_framework() -> None:
    # `url4 --version` and `url4 eval` must work on the base install, so the
    # CLI module itself may not import uvicorn at module scope.
    assert _loaded_after_import("url4.cli", _FRAMEWORKS) == set()


def test_the_probe_detects_a_module_that_IS_imported() -> None:
    # Sanity-check the detector: without this, a typo in the probe would make
    # every assertion above pass vacuously forever.
    assert _loaded_after_import("url4", ("json",)) == {"json"}
