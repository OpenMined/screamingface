"""Widgets — v0.1 ships the mock/static rendering path only (live = OME-407).

INVARIANT (contract "no dead ends"): every panel exposes `.value` — the real
object it produces — even in static mock mode.
INVARIANT (spec I5): importing screamingface must not import IPython/ipywidgets.
"""

from __future__ import annotations

import subprocess
import sys

import screamingface as sf
from screamingface.session import Session
from screamingface.widgets import MockHandle, setup_panel


def test_mock_widgets_toggle_is_available():
    sf.mock_widgets(True)  # the notebook's first line — must be a no-op-safe toggle
    sf.mock_widgets(False)
    sf.mock_widgets(True)


class TestSetupPanel:
    def test_renders_self_contained_html(self):
        handle = setup_panel()
        html = handle._repr_html_()
        assert "<style>" in html  # self-contained: styles inline
        assert "Connect a provider" in html
        assert "Anthropic" in html and "OpenAI" in html

    def test_value_is_the_session(self):
        handle = setup_panel()
        assert isinstance(handle.value, Session)

    def test_connected_provider_shows_masked_key_only(self):
        # INVARIANT I4: the rendered HTML never contains the raw key.
        sf.session.connect("anthropic", api_key="sk-visible-never-9876")
        html = setup_panel()._repr_html_()
        assert "sk-visible-never" not in html
        assert "9876" in html  # the mask's tail is fine

    def test_handle_is_mock_in_v01(self):
        assert isinstance(setup_panel(), MockHandle)


def test_import_does_not_pull_widget_machinery():
    # INVARIANT I5 — run in a clean interpreter so this test is hermetic.
    code = (
        "import sys; import screamingface; "
        "banned = [m for m in ('IPython', 'ipywidgets') if m in sys.modules]; "
        "assert not banned, f'import pulled {banned}'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
