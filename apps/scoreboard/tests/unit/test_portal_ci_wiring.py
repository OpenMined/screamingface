"""OME-798: every portal test file must be executed by both gates.

The explicit-path invocation protects against a RENAMED file (a missing path exits 1)
but not against an ADDED one: a new `tests/portal/foo.test.js` would simply never run,
at either call site, silently. That is the same "believed tested" failure the explicit
path was chosen to avoid, just relocated — found in review of #595.

Reading the two call sites as text is deliberate: a glob invocation would close the
additions hole but reopen the worse one, since Node exits 0 with "pass 0" when a glob
matches nothing. This test keeps the loud invocation and makes additions loud too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# parents: [0] tests/unit  [1] tests  [2] apps/scoreboard  [3] apps  [4] repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PORTAL_TESTS = Path(__file__).resolve().parents[1] / "portal"
_CALL_SITES = (
    _REPO_ROOT / ".github" / "workflows" / "scoreboard-tests.yml",
    _REPO_ROOT / ".claude" / "sdlc.local.md",
)


def _portal_test_files() -> list[Path]:
    return sorted(_PORTAL_TESTS.glob("*.test.js"))


def test_the_portal_test_directory_is_not_empty() -> None:
    """Guard the guard: an empty directory would make the check below vacuous."""
    assert _portal_test_files(), f"no *.test.js under {_PORTAL_TESTS}"


@pytest.mark.parametrize("call_site", _CALL_SITES, ids=lambda p: p.name)
def test_every_portal_test_file_is_wired_into(call_site: Path) -> None:
    assert call_site.is_file(), f"missing call site {call_site}"
    text = call_site.read_text()
    missing = [path.name for path in _portal_test_files() if path.name not in text]

    assert missing == [], (
        f"{call_site.name} does not run: {missing}. Add each file by name — the "
        "explicit-path invocation is deliberate (a glob exits 0 with 'pass 0' when it "
        "matches nothing), so a new test file must be wired in at both call sites."
    )
