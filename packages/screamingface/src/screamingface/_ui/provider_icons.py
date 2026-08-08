"""Real, verbatim provider logo marks for the connection panel.

See assets/provider_icons/NOTICE.md for provenance.
"""

from __future__ import annotations

from functools import cache
from importlib import resources

_ASSETS_PACKAGE = "screamingface._ui"
_ASSETS_PATH = ("assets", "provider_icons")

# provider id -> (light-bg svg filename, dark-bg svg filename or None if one file reads on both)
_ICON_FILES: dict[str, tuple[str, str | None]] = {
    "anthropic": ("icon.svg", "icon-dark.svg"),
    "openrouter": ("icon.svg", "icon-dark.svg"),
    "ollama": ("icon.svg", "icon-dark.svg"),
    "huggingface": ("icon.svg", None),
    "gemini-cli": ("icon.svg", None),
}


@cache
def _read(provider: str, filename: str) -> str:
    root = resources.files(_ASSETS_PACKAGE)
    return root.joinpath(*_ASSETS_PATH, provider, filename).read_text(encoding="utf-8")


def provider_icon_html(provider: str) -> str | None:
    """Return the sf-tile-icon HTML for a known provider's real logo, else None."""

    files = _ICON_FILES.get(provider)
    if files is None:
        return None
    light_file, dark_file = files
    light = _read(provider, light_file)
    if dark_file is None:
        return f"<span class='sf-tile-icon sf-tile-icon--logo' aria-hidden='true'>{light}</span>"
    dark = _read(provider, dark_file)
    return (
        "<span class='sf-tile-icon sf-tile-icon--logo' aria-hidden='true'>"
        f"<span class='sf-icon-light'>{light}</span>"
        f"<span class='sf-icon-dark'>{dark}</span></span>"
    )


__all__: list[str] = []
