"""Shared visual foundation for ScreamingFace notebook surfaces.

Tracks the current `screamingface-brand`: gain is gold (the SOTA/win signal — it replaced the
old green), display type is EB Garamond, and the brand webfonts are pulled with system
fallbacks. The gold→blue fusion-signature GRADIENT is deliberately NOT defined here — it lives
in `_card_style` so gradient-free surfaces (e.g. the connection panel) never inherit it.
"""

from __future__ import annotations

_FONTS = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=EB+Garamond:wght@500&family=IBM+Plex+Mono:wght@400;500;600&"
    "family=IBM+Plex+Sans:wght@400;500;600&display=swap');"
)

_DARK = (
    "--sf-bg:#0a0b0d;--sf-surface:#131519;--sf-surface-2:#1a1d22;"
    "--sf-ink:#e8eaed;--sf-ink-2:#9aa0aa;--sf-ink-3:#686e78;"
    "--sf-line:#20232a;--sf-line-2:#2c303a;--sf-gain:#e0a23c;--sf-gain-bg:#241c0e;"
    "--sf-blind:#f0726f;--sf-blind-bg:#2a1715"
)
_LIGHT = (
    "--sf-bg:#ffffff;--sf-surface:#f6f6f7;--sf-surface-2:#efeff1;"
    "--sf-ink:#16181d;--sf-ink-2:#585d67;--sf-ink-3:#8b909a;"
    "--sf-line:#e6e7ea;--sf-line-2:#d4d6db;--sf-gain:#b07d12;--sf-gain-bg:#faf1dd;"
    "--sf-blind:#b23b3b;--sf-blind-bg:#f6e7e6"
)

# INVARIANT: --sf-gain is GOLD (brand refresh — replaced green #0f7a3d/#35d07f). Never purple.
STYLE = f"""<style>
{_FONTS}
.sf-ui {{
  {_LIGHT};
  --sf-display:"EB Garamond","Iowan Old Style",Georgia,"Times New Roman",serif;
  --sf-sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --sf-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  max-width:760px;color:var(--sf-ink);background:var(--sf-bg);
  font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:13px;line-height:1.45;
}}
@media (prefers-color-scheme:dark){{.sf-ui{{{_DARK}}}}}
.jp-mod-theme-dark .sf-ui,[data-jp-theme-light="false"] .sf-ui,
.vscode-dark .sf-ui,.vscode-high-contrast .sf-ui{{{_DARK}}}
.jp-mod-theme-light .sf-ui,[data-jp-theme-light="true"] .sf-ui,.vscode-light .sf-ui{{{_LIGHT}}}
.sf-ui,.sf-ui *{{box-sizing:border-box}}
</style>"""

__all__ = ["STYLE"]
