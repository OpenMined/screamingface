"""Widget-view renderers — brand-styled, self-contained static HTML.

Each render embeds a scoped ``<style>`` (brand tokens + the ``.w-*`` widget
CSS) under a ``.sfw`` wrapper, so the output survives nbconvert / GitHub /
nbviewer with no external assets. Brand law per the screamingface-design
system: radius-0, hairline borders, IBM Plex Mono, gold ``#d88507`` accent.

AIDEV-NOTE: v0.1 ships only the setup panel (quickstart). The browse /
compose / run / inspect / leaderboard builders arrive with OME-407 / OME-402.
"""

from __future__ import annotations

import html as _html

_TOKENS = """
.sfw{
 --bg:#fff;--surface:#f6f6f7;--ink:#16181d;--ink-2:#585d67;--ink-3:#8b909a;
 --line:#e6e7ea;--line-2:#d4d6db;--gain:#d88507;--gain-bg:#fbf1da;--cat-blue:#4e79a7;
 --f-display:"EB Garamond","Iowan Old Style",Georgia,"Times New Roman",serif;
 --f-sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
 --f-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
 --text-lead:20px;--text-sm:13px;--text-micro:12px;--text-label:11px;
 --tracking-tight:-0.01em;--tracking-label:0.1em;
 --space-1:4px;--space-2:8px;--space-3:12px;--space-4:16px;
 background:var(--bg);color:var(--ink);font-family:var(--f-sans);
 font-size:var(--text-sm);line-height:1.6;max-width:720px;
}
.sfw *{box-sizing:border-box}
.sfw button{font:inherit}
"""

_WIDGET_CSS = """
.w{font-family:var(--f-sans);font-size:var(--text-sm);color:var(--ink)}
.w .w-head{display:flex;align-items:center;gap:var(--space-2);margin-bottom:var(--space-3);flex-wrap:wrap}
.w-title{font-family:var(--f-display);font-size:var(--text-lead);color:var(--ink);letter-spacing:var(--tracking-tight)}
.w-sub{font-family:var(--f-mono);font-size:var(--text-micro);color:var(--ink-3);text-transform:uppercase;letter-spacing:var(--tracking-label)}
.w-grouplabel{font-family:var(--f-mono);font-size:var(--text-label);text-transform:uppercase;letter-spacing:var(--tracking-label);color:var(--ink-3);margin:var(--space-4) 0 var(--space-2)}
.w-faint{color:var(--ink-3)}
.w-footline{display:flex;align-items:center;gap:var(--space-2);margin-top:var(--space-4);padding-top:var(--space-3);border-top:1px solid var(--line);font-family:var(--f-mono);font-size:var(--text-micro);color:var(--ink-3)}
.w-tag{font-family:var(--f-mono);font-size:var(--text-micro);color:var(--gain);border:1px solid var(--gain);padding:1px var(--space-2);white-space:nowrap}
.w-btn{font-family:var(--f-mono);font-size:var(--text-sm);cursor:pointer;border-radius:0;border:1px solid var(--ink);background:var(--bg);color:var(--ink);padding:var(--space-2) var(--space-4)}
.w-btn.tiny{padding:var(--space-1) var(--space-3);font-size:var(--text-micro)}
.w-btn.gain{border-color:var(--gain);color:var(--gain)}
.w-btn.ghost{border-color:var(--line-2);color:var(--ink-2)}
.w-dot{width:7px;height:7px;flex:0 0 auto;background:var(--line-2);display:inline-block}
.w-dot.on{background:var(--gain);box-shadow:0 0 0 3px var(--gain-bg)}
.w-tilegrid{display:grid;grid-template-columns:repeat(2,1fr);gap:var(--space-2)}
.w-tile{border:1px solid var(--line-2);padding:var(--space-3);background:var(--bg)}
.w-tile.on{border-left:2px solid var(--gain)}
.w-tile-top{display:flex;align-items:center;gap:var(--space-2)}
.w-tile-name{font-family:var(--f-sans);font-weight:600}
.w-tile-env{font-family:var(--f-mono);font-size:var(--text-micro);color:var(--ink-3);margin:var(--space-1) 0 var(--space-2)}
.w-tile-foot{display:flex;align-items:center;justify-content:space-between;gap:var(--space-2)}
.w-mask{font-family:var(--f-mono);font-size:var(--text-micro);color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
"""

_CSS = _TOKENS + _WIDGET_CSS


def _e(s: object) -> str:
    return _html.escape(str(s))


def frame(inner: str) -> str:
    """Wrap widget markup with the scoped stylesheet (self-contained output)."""
    return f"<div class='sfw'><style>{_CSS}</style>{inner}</div>"


def _foot(tag: str, note: str) -> str:
    return f"<div class='w-footline'><span class='w-tag'>{_e(tag)}</span> {_e(note)}</div>"


def setup(session) -> str:
    """The connect panel: one tile per provider, grouped, keys masked."""
    from .catalog import GROUP_ORDER, PROVIDERS
    from .session import KEY_NAMES, _mask

    body = (
        "<div class='w w-setup'><div class='w-head'>"
        "<span class='w-title'>Connect a provider</span>"
        "<span class='w-sub'>keys stay in memory · never printed · grading simulated</span>"
        "</div>"
    )
    for group in GROUP_ORDER:
        provs = [p for p in PROVIDERS.values() if p.group == group]
        if not provs:
            continue
        body += f"<div class='w-grouplabel'>{_e(group)}</div><div class='w-tilegrid'>"
        for prov in provs:
            conn = session.connections.get(prov.id)
            connected = bool(conn and conn.connected)
            key = session.keys.get(prov.id)
            via = (conn.source if conn else "") or ""
            # INVARIANT (spec I4): only the mask ever reaches the markup.
            mask = _mask(key) if key else ""
            foot = (
                f"<span class='w-mask'>🔑 {_e(mask or '—')} · {_e(via)}</span>"
                if connected
                else "<span class='w-faint'>not connected</span>"
            )
            btn = (
                f"<button class='w-btn tiny {'ghost' if connected else 'gain'}'>"
                f"{'disconnect' if connected else 'connect'}</button>"
            )
            body += (
                f"<div class='w-tile{' on' if connected else ''}'>"
                f"<div class='w-tile-top'><span class='w-dot{' on' if connected else ''}'></span>"
                f"<span class='w-tile-name'>{_e(prov.name)}</span></div>"
                f"<div class='w-tile-env'>{_e(KEY_NAMES.get(prov.id, ''))}</div>"
                f"<div class='w-tile-foot'>{foot}{btn}</div></div>"
            )
        body += "</div>"
    n = sum(1 for p in PROVIDERS if session.is_connected(p))
    note = f"Session · {n} provider{'' if n == 1 else 's'} connected"
    body += _foot(".value", note) + "</div>"
    return frame(body)
