"""Drift alarms against the brand mockup this landing page was copied from (OME-874).

These are **smoke tests, never gates**: they fetch `brand.screamingface.ai`, a site we do not
own and that changes on someone else's schedule. A failure here means *"the source moved, go
look"* — not *"this branch is broken"*. Excluded from the default run and from CI by the
`smoke` marker; run them deliberately:

    uv run pytest -m smoke

WHY they exist at all: the landing copy and the hero mark are vendored **copies**. A copy with
nothing watching it silently becomes a fork. The alternative — asserting brand strings in the
unit suite — makes an editor at another company able to turn our build red, which is why the
equivalent assertions were taken back out of `tests/unit/test_portal_static.py`.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.smoke

MOCKUP_URL = "https://brand.screamingface.ai/leaderboard-mvp/"
MARK_URL = "https://brand.screamingface.ai/assets/mark/sf-mark-640.png"
TIMEOUT = 15.0

# Recorded 2026-08-18 when the page was vendored — see portal/assets/mark/PROVENANCE.md.
VENDORED_MARK_SOURCE_SHA256 = "cdf5d9dbce79a8e9a2cb04eaec551de1c333c1c58af5589d8c2c35e68a5e56d8"

_PORTAL = Path(__file__).resolve().parents[2] / "portal"


def _fetch(url: str) -> httpx.Response:
    try:
        response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as exc:  # pragma: no cover - network shape varies
        pytest.skip(f"brand site unreachable: {exc}")
    if response.status_code != 200:  # pragma: no cover - depends on their deploy
        pytest.skip(f"brand site returned {response.status_code}")
    return response


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_the_glossary_definitions_still_match_the_mockup() -> None:
    """The three `<dd>` definitions we copied verbatim are still the ones published."""
    mockup = _collapse(_fetch(MOCKUP_URL).text)
    ours = _collapse((_PORTAL / "index.html").read_text(encoding="utf-8"))

    definitions = re.findall(r"<dd>(.*?)</dd>", mockup)
    assert definitions, "the mockup no longer publishes a <dd> glossary — layout changed"

    drifted = [text for text in definitions if text not in ours]
    assert not drifted, (
        "the brand mockup's glossary changed and our copy did not:\n  "
        + "\n  ".join(drifted)
        + f"\n\nUpdate portal/index.html to match {MOCKUP_URL}, or decide deliberately not to."
    )


def test_the_read_this_first_note_still_matches_the_mockup() -> None:
    mockup = _collapse(_fetch(MOCKUP_URL).text)
    ours = _collapse((_PORTAL / "index.html").read_text(encoding="utf-8"))

    match = re.search(r"Read this first</span>(.*?)</div>", mockup)
    assert match is not None, "the mockup's Read-this-first box moved or was renamed"

    published = _collapse(match.group(1))
    assert published in ours, (
        "the brand mockup's Read-this-first copy changed and ours did not:\n  "
        f"{published}\n\nUpdate portal/index.html, or decide deliberately not to."
    )


def test_the_vendored_hero_mark_still_matches_upstream() -> None:
    """Our 128px mark is a resample of upstream's 640px source; alarm if that source moved.

    Compares the SOURCE bytes, not our resample — resizing is lossy and reproducing it
    byte-for-byte across libraries is not a promise worth making.
    """
    if VENDORED_MARK_SOURCE_SHA256 == "PENDING":  # pragma: no cover - set on first run
        pytest.skip("baseline digest not recorded yet; see PROVENANCE.md")

    digest = hashlib.sha256(_fetch(MARK_URL).content).hexdigest()

    assert digest == VENDORED_MARK_SOURCE_SHA256, (
        "the brand site reissued the mark. Re-vendor it with the commands in "
        "portal/assets/mark/PROVENANCE.md and update the digest here in the same change."
    )
