"""Stylesheet for ScreamingFace notebook cards, catalogs, and the url4 recipe view.

Split out of `_card_display` to keep each module focused and under the size budget. Every value
is a `.sf-ui` token from `_display.STYLE` — no raw colors (brand law).
"""

from __future__ import annotations

from screamingface._display import STYLE

# WHY: the gold→blue fusion signature (sampled from the 😱 mark) is defined here, not in the
# shared STYLE, so gradient-free surfaces (e.g. the connection panel) never inherit it. The
# stops run gold→blue only — never violet — per brand.
CARD_STYLE = (
    STYLE
    + """<style>
.sf-ui{--sf-gain-grad:linear-gradient(100deg,#d08511 0%,#e7a105 16%,#dbb13b 40%,
  #8e9dab 60%,#9fb8f8 80%,#346cf9 100%)}
.sf-card{border:1px solid var(--sf-line-2);background:var(--sf-bg)}
.sf-card__accent{height:3px;background:var(--sf-gain-grad)}
.sf-card__accent--solid{background:var(--sf-gain)}
.sf-card__head{display:flex;align-items:baseline;gap:8px;padding:12px;
  border-bottom:1px solid var(--sf-line)}
.sf-card__title{font-family:var(--sf-display);font-size:20px;font-weight:500;
  letter-spacing:-.01em;line-height:1.15;color:var(--sf-ink);overflow-wrap:anywhere}
.sf-card__kicker{margin-left:auto;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--sf-gain)}
.sf-card__grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--sf-line)}
.sf-card__field{background:var(--sf-bg);padding:8px 12px;min-width:0}
.sf-card__field.wide{grid-column:1 / -1}
.sf-card__k{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--sf-ink-3)}
.sf-card__v{margin-top:2px;overflow-wrap:anywhere}
.sf-card__hint{color:var(--sf-ink-3)}
.sf-card__list{margin:2px 0 0;padding:0;list-style:none}
.sf-card__list li{padding:1px 0}
.sf-card__recipe{padding:8px 12px;background:var(--sf-surface);min-width:0;
  border-top:1px solid var(--sf-line)}
.sf-mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}
.sf-card__meta{margin-top:3px;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;color:var(--sf-ink-3);overflow-wrap:anywhere}
/* big-number stat grid (mirrors the evaluation report widget) */
.sf-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;
  background:var(--sf-line)}
.sf-stat{background:var(--sf-bg);padding:12px;min-width:0}
.sf-stat__k{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--sf-ink-3)}
.sf-stat__v{margin-top:6px;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:20px;
  font-weight:600;font-variant-numeric:tabular-nums;color:var(--sf-ink);line-height:1.15;
  overflow-wrap:anywhere}
@media (max-width:620px){.sf-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
.sf-chips{display:flex;flex-wrap:wrap;gap:6px;padding:10px 12px;
  border-top:1px solid var(--sf-line)}
.sf-chip{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;color:var(--sf-ink-2);
  border:1px solid var(--sf-line-2);padding:1px 8px}
/* catalogs */
.sf-catalog{border:1px solid var(--sf-line-2)}
.sf-catalog-widget.widget-vbox{border:0!important;box-shadow:none!important}
.sf-catalog__head{display:flex;align-items:center;gap:8px;height:44px;padding:0 12px;
  border-bottom:1px solid var(--sf-line-2)}
.sf-catalog__title{font-family:var(--sf-display);font-size:16px;font-weight:500;
  letter-spacing:-.01em}
.sf-catalog__count{margin-left:auto;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;color:var(--sf-ink-3)}
.sf-catalog__row{display:grid;grid-template-columns:minmax(0,2fr) 1fr;gap:12px;
  align-items:center;padding:8px 12px;border-bottom:1px solid var(--sf-line)}
.sf-catalog__row:last-child{border-bottom:0}
.sf-catalog__id{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  font-weight:600;overflow-wrap:anywhere}
.sf-catalog__sub{color:var(--sf-ink-2)}
.sf-catalog__meta{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;
  color:var(--sf-ink-3);text-align:right;overflow-wrap:anywhere}
.sf-catalog__empty{padding:16px 12px;color:var(--sf-ink-3);text-align:center;
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}
.sf-catalog-widget .widget-text input{border-radius:0!important;box-shadow:none!important;
  background-image:none!important;height:32px!important;padding:0 8px!important;
  border:1px solid var(--sf-line-2)!important;background:var(--sf-bg)!important;
  color:var(--sf-ink)!important;
  font:12px/1 "IBM Plex Mono",ui-monospace,monospace!important}
.sf-catalog-widget .widget-text{width:auto!important;margin:8px 12px!important}
/* collapsible summary shared chrome */
.sf-summary{cursor:pointer;display:flex;align-items:center;gap:8px;list-style:none}
.sf-summary::-webkit-details-marker{display:none}
.sf-summary::before{content:'▸';color:var(--sf-ink-3);font-size:10px}
details[open] > .sf-summary::before{content:'▾'}
/* long-field collapse (prompts, routes) */
.sf-more{margin-top:2px}
.sf-more__preview{color:var(--sf-ink-3);font-style:italic}
.sf-more__full{margin-top:4px;white-space:pre-wrap;overflow-wrap:anywhere;
  background:var(--sf-surface);padding:6px 8px;font-size:12px;color:var(--sf-ink-2)}
/* always-visible detail sections (members, reducer, grader) */
.sf-section{margin-top:8px;border-top:1px solid var(--sf-line);padding:8px 12px 0}
.sf-section__title{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--sf-ink-3)}
.sf-detail__item{border-left:2px solid var(--sf-line-2);padding:2px 0 6px 10px;margin-top:6px}
.sf-detail__name{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  font-weight:600;color:var(--sf-gain)}
.sf-detail__route{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;
  color:var(--sf-ink-2);overflow-wrap:anywhere}
.sf-detail__params{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;
  color:var(--sf-ink-2);overflow-wrap:anywhere}
/* url4 recipe: full form, reflowed, in a <pre> (MathJax skips pre/code) */
.sf-url4{border:0;min-width:0}
.sf-url4__copy{margin-left:auto;cursor:pointer;border-radius:0;
  border:1px solid var(--sf-line-2);background:var(--sf-bg);color:var(--sf-ink-2);
  padding:2px 8px;font:11px/1 "IBM Plex Mono",ui-monospace,monospace}
.sf-url4__copy:hover{border-color:var(--sf-ink-3);color:var(--sf-ink)}
.sf-url4__pre{margin:8px 0 0;padding:8px;background:var(--sf-bg);
  border:1px solid var(--sf-line);color:var(--sf-ink);
  font:11px/1.5 "IBM Plex Mono",ui-monospace,monospace;
  white-space:pre-wrap;overflow-wrap:anywhere;tab-size:2}
</style>"""
)

__all__ = ["CARD_STYLE"]
