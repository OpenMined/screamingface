"""Shared visual foundation for ScreamingFace notebook surfaces."""

from __future__ import annotations

STYLE = """<style>
.sf-ui {
  --sf-bg:#ffffff;--sf-surface:#f6f6f7;--sf-surface-2:#efeff1;
  --sf-ink:#16181d;--sf-ink-2:#585d67;--sf-ink-3:#8b909a;
  --sf-line:#e6e7ea;--sf-line-2:#d4d6db;
  --sf-gain:#0f7a3d;--sf-gain-bg:#e8f3ec;
  --sf-blind:#b23b3b;--sf-blind-bg:#f6e7e6;
  max-width:760px;color:var(--sf-ink);background:var(--sf-bg);
  font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:13px;line-height:1.45;
}
@media (prefers-color-scheme:dark){.sf-ui{--sf-bg:#0a0b0d;--sf-surface:#131519;
  --sf-surface-2:#1a1d22;--sf-ink:#e8eaed;--sf-ink-2:#9aa0aa;--sf-ink-3:#686e78;
  --sf-line:#20232a;--sf-line-2:#2c303a;--sf-gain:#35d07f;--sf-gain-bg:#11241b;
  --sf-blind:#f0726f;--sf-blind-bg:#2a1715}}
.jp-mod-theme-dark .sf-ui,[data-jp-theme-light="false"] .sf-ui,
.vscode-dark .sf-ui,.vscode-high-contrast .sf-ui{--sf-bg:#0a0b0d;--sf-surface:#131519;
  --sf-surface-2:#1a1d22;--sf-ink:#e8eaed;--sf-ink-2:#9aa0aa;--sf-ink-3:#686e78;
  --sf-line:#20232a;--sf-line-2:#2c303a;--sf-gain:#35d07f;--sf-gain-bg:#11241b;
  --sf-blind:#f0726f;--sf-blind-bg:#2a1715}
.jp-mod-theme-light .sf-ui,[data-jp-theme-light="true"] .sf-ui,.vscode-light .sf-ui{
  --sf-bg:#ffffff;--sf-surface:#f6f6f7;--sf-surface-2:#efeff1;
  --sf-ink:#16181d;--sf-ink-2:#585d67;--sf-ink-3:#8b909a;
  --sf-line:#e6e7ea;--sf-line-2:#d4d6db;--sf-gain:#0f7a3d;--sf-gain-bg:#e8f3ec;
  --sf-blind:#b23b3b;--sf-blind-bg:#f6e7e6}
.sf-ui,.sf-ui *{box-sizing:border-box}
</style>"""

__all__ = ["STYLE"]
