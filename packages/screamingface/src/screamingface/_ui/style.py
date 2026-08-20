"""Shared visual foundation for ScreamingFace notebook surfaces."""

from __future__ import annotations

import re

_LIGHT = (
    "--sf-bg:#ffffff;--sf-surface:#f6f6f7;--sf-surface-2:#efeff1;"
    "--sf-ink:#16181d;--sf-ink-2:#585d67;--sf-ink-3:#8b909a;"
    "--sf-line:#e6e7ea;--sf-line-2:#d4d6db;--sf-gain:#b07d12;--sf-gain-bg:#faf1dd;"
    "--sf-blind:#b23b3b;--sf-blind-bg:#f6e7e6;"
    "--sf-accent:#4b91f0;--sf-accent-hover:#3a7ddb;--sf-accent-contrast:#ffffff;"
    "--sf-success:#14722a;--sf-success-solid:#64e47d;--sf-success-bg:#f0f9f2;"
    "--sf-warning:#9c4828;--sf-warning-solid:#f1622d;--sf-warning-bg:#fdf4f1;"
    "--sf-warning-border:#d7aa9b"
)
_DARK = (
    "--sf-bg:#0a0b0d;--sf-surface:#131519;--sf-surface-2:#1a1d22;"
    "--sf-ink:#e8eaed;--sf-ink-2:#9aa0aa;--sf-ink-3:#686e78;"
    "--sf-line:#20232a;--sf-line-2:#2c303a;--sf-gain:#e0a23c;--sf-gain-bg:#241c0e;"
    "--sf-blind:#f0726f;--sf-blind-bg:#2a1715;"
    "--sf-accent:#75affe;--sf-accent-hover:#8fbeff;--sf-accent-contrast:#0a0b0d;"
    "--sf-success:#97db9d;--sf-success-solid:#7cdf8c;--sf-success-bg:#0c100d;"
    "--sf-warning:#ffbca5;--sf-warning-solid:#e36f48;--sf-warning-bg:#130e0c;"
    "--sf-warning-border:#735248"
)

# The one sanctioned SFDS gradient (fusion-grad), as the brand repo renders it on a
# progress/score fill (product-demos/widgets-view/widgets.css .w-progfill). Held as a
# plain constant, NOT a custom property on .sf-ui: it stays opt-in per surface so it can
# only appear where the story earns it — a run in flight, or the leading candidate.
FUSION_GRADIENT = (
    "linear-gradient(90deg,#d8860e 0%,#dc9544 8%,#de9f5b 16%,#e2b280 27%,#e7c3a0 34%,"
    "#ebd4be 40%,#edddcd 43%,#f2e3df 46%,#eeebf3 49%,#e7edf5 52%,#dde6f4 56%,"
    "#d2dff2 60%,#bfd4f2 65%,#abc8f2 71%,#97bcf3 77%,#83b0f3 84%,#6fa4f3 90%,"
    "#5a98f3 96%,#4f91f2 100%)"
)


def _flow(gradient: str) -> str:
    """Mirror a ramp into a seamless palindrome (gold→blue→gold).

    Tiled at 200% and scrolled by background-position it loops without a visible seam,
    which is how SFDS renders `--fusion-grad-flow`. Built from the base stops rather than
    pasted as a second literal so the two can never drift apart.
    """

    stops = re.findall(r"(#[0-9a-f]{6}) ([0-9.]+)%", gradient)
    forward = [(color, float(pct) / 2) for color, pct in stops]
    mirrored = [(color, 100 - float(pct) / 2) for color, pct in stops]
    combined = forward + list(reversed(mirrored))
    body = ",".join(f"{color} {pct:.4g}%" for color, pct in combined)
    return f"linear-gradient(90deg,{body})"


FUSION_GRADIENT_FLOW = _flow(FUSION_GRADIENT)

# The vertical run of the same ramp, for the score cell's left edge band
# (product-demos/widgets-view/widgets.css .w-rescell-score::before).
FUSION_GRADIENT_Y = FUSION_GRADIENT.replace("linear-gradient(90deg", "linear-gradient(180deg")

# INVARIANT: shared surfaces use solid gold; the Fusion gradient is card-scoped.
STYLE = f"""<style>
.sf-ui{{
  {_LIGHT};
  max-width:920px;color:var(--sf-ink);background:var(--sf-bg);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:13px;line-height:1.45;
}}
@media (prefers-color-scheme:dark){{.sf-ui{{{_DARK}}}}}
.jp-mod-theme-dark .sf-ui,[data-jp-theme-light="false"] .sf-ui,
.vscode-dark .sf-ui,.vscode-high-contrast .sf-ui{{{_DARK}}}
.jp-mod-theme-light .sf-ui,[data-jp-theme-light="true"] .sf-ui,
.vscode-light .sf-ui{{{_LIGHT}}}
.sf-ui,.sf-ui *{{box-sizing:border-box}}
</style>"""

__all__: list[str] = []
