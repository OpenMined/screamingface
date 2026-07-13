"""Widgets — v0.1: static mock rendering only.

INVARIANT ("no dead ends"): every panel exposes ``.value`` — the real object it
produces or edits — even as a static snapshot.
INVARIANT (spec I5): this module imports no IPython/ipywidgets machinery; the
renders are plain HTML strings via ``_repr_html_``.

``sf.mock_widgets(True)`` is the notebooks' first line. In v0.1 every widget is
static regardless (the toggle is honored for forward compatibility); live
ipywidgets twins land in OME-407.
"""

from __future__ import annotations

from collections.abc import Callable

from . import wv

_MOCK: bool = True


def mock_widgets(on: bool = True) -> None:
    """Render widgets as self-contained static HTML (survives GitHub/nbviewer).

    AIDEV-NOTE: v0.1 has no live widget path, so ``mock_widgets(False)`` still
    renders static panels — the flag exists so notebooks written against the
    final API don't change when OME-407 adds the live twins.
    """
    global _MOCK
    _MOCK = bool(on)


class MockHandle:
    """A static widget snapshot that still honors the ``.value`` contract."""

    def __init__(self, html: str, value_fn: Callable[[], object]):
        self._html = html
        self._value_fn = value_fn

    @property
    def value(self) -> object:
        return self._value_fn()

    def _repr_html_(self) -> str:
        return self._html

    def __repr__(self) -> str:
        return "<widget preview — .value holds the object>"


def setup_panel() -> MockHandle:
    """The connect panel; ``.value`` is the live Session."""
    from .session import session

    return MockHandle(wv.setup(session), lambda: session)
