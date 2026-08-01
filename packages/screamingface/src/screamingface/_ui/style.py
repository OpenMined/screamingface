"""Shared visual foundation for ScreamingFace notebook surfaces."""

from __future__ import annotations

_LIGHT = (
    "--sf-bg:#ffffff;--sf-surface:#f6f6f7;--sf-surface-2:#efeff1;"
    "--sf-ink:#16181d;--sf-ink-2:#585d67;--sf-ink-3:#8b909a;"
    "--sf-line:#e6e7ea;--sf-line-2:#d4d6db;--sf-gain:#b07d12;--sf-gain-bg:#faf1dd;"
    "--sf-blind:#b23b3b;--sf-blind-bg:#f6e7e6"
)
_DARK = (
    "--sf-bg:#0a0b0d;--sf-surface:#131519;--sf-surface-2:#1a1d22;"
    "--sf-ink:#e8eaed;--sf-ink-2:#9aa0aa;--sf-ink-3:#686e78;"
    "--sf-line:#20232a;--sf-line-2:#2c303a;--sf-gain:#e0a23c;--sf-gain-bg:#241c0e;"
    "--sf-blind:#f0726f;--sf-blind-bg:#2a1715"
)

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
