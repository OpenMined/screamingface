"""Text and notebook presentation for immutable benchmark reports."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from screamingface.report import Report

type ReportStatus = Literal["complete", "partial", "failed"]

_STYLE = """<style>
.sf-report {
  --sf-bg: #ffffff;
  --sf-surface: #f6f6f7;
  --sf-surface-2: #efeff1;
  --sf-ink: #16181d;
  --sf-ink-2: #585d67;
  --sf-ink-3: #8b909a;
  --sf-line: #e6e7ea;
  --sf-line-2: #d4d6db;
  --sf-gain: #0f7a3d;
  --sf-gain-bg: #e8f3ec;
  --sf-blind: #b23b3b;
  --sf-blind-bg: #f6e7e6;
  max-width: 760px;
  color: var(--sf-ink);
  background: var(--sf-bg);
  border: 1px solid var(--sf-line-2);
  font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 13px;
  line-height: 1.45;
}
@media (prefers-color-scheme: dark) {
  .sf-report {
    --sf-bg: #0a0b0d;
    --sf-surface: #131519;
    --sf-surface-2: #1a1d22;
    --sf-ink: #e8eaed;
    --sf-ink-2: #9aa0aa;
    --sf-ink-3: #686e78;
    --sf-line: #20232a;
    --sf-line-2: #2c303a;
    --sf-gain: #35d07f;
    --sf-gain-bg: #11241b;
    --sf-blind: #f0726f;
    --sf-blind-bg: #2a1715;
  }
}
.jp-mod-theme-dark .sf-report,
[data-jp-theme-light="false"] .sf-report,
.vscode-dark .sf-report,
.vscode-high-contrast .sf-report {
  --sf-bg: #0a0b0d;
  --sf-surface: #131519;
  --sf-surface-2: #1a1d22;
  --sf-ink: #e8eaed;
  --sf-ink-2: #9aa0aa;
  --sf-ink-3: #686e78;
  --sf-line: #20232a;
  --sf-line-2: #2c303a;
  --sf-gain: #35d07f;
  --sf-gain-bg: #11241b;
  --sf-blind: #f0726f;
  --sf-blind-bg: #2a1715;
}
.jp-mod-theme-light .sf-report,
[data-jp-theme-light="true"] .sf-report,
.vscode-light .sf-report {
  --sf-bg: #ffffff;
  --sf-surface: #f6f6f7;
  --sf-surface-2: #efeff1;
  --sf-ink: #16181d;
  --sf-ink-2: #585d67;
  --sf-ink-3: #8b909a;
  --sf-line: #e6e7ea;
  --sf-line-2: #d4d6db;
  --sf-gain: #0f7a3d;
  --sf-gain-bg: #e8f3ec;
  --sf-blind: #b23b3b;
  --sf-blind-bg: #f6e7e6;
}
.sf-report, .sf-report * { box-sizing: border-box; }
.sf-report-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 16px;
  border-bottom: 1px solid var(--sf-line);
}
.sf-report-title { font-size: 16px; font-weight: 600; color: var(--sf-ink); }
.sf-report-meta,
.sf-report-status,
.sf-report-label,
.sf-report-member-id,
.sf-report-score,
.sf-report-foot {
  font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}
.sf-report-meta { margin-top: 4px; font-size: 12px; color: var(--sf-ink-3); }
.sf-report-status {
  padding-top: 2px;
  color: var(--sf-ink-2);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
  white-space: nowrap;
}
.sf-report-status.complete { color: var(--sf-gain); }
.sf-report-status.failed { color: var(--sf-blind); }
.sf-report-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-bottom: 1px solid var(--sf-line);
}
.sf-report-stat { min-width: 0; padding: 16px; border-right: 1px solid var(--sf-line); }
.sf-report-stat:last-child { border-right: 0; }
.sf-report-value {
  margin-top: 8px;
  color: var(--sf-ink);
  font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 30px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1.16;
}
.sf-report-value.gain { color: var(--sf-gain); }
.sf-report-value.blind { color: var(--sf-blind); }
.sf-report-unit { margin-left: 2px; font-size: .45em; font-weight: 400; opacity: .5; }
.sf-report-label {
  color: var(--sf-ink-3);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .1em;
  text-transform: uppercase;
}
.sf-report-section { padding: 16px; border-bottom: 1px solid var(--sf-line); }
.sf-report-section .sf-report-label { display: block; margin-bottom: 8px; }
.sf-report-extra {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  border: 1px solid var(--sf-line);
}
.sf-report-extra .sf-report-stat { background: var(--sf-surface); }
.sf-report-member {
  display: grid;
  grid-template-columns: minmax(180px, 1.25fr) 2fr 86px;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}
.sf-report-member-model { color: var(--sf-ink); font-weight: 600; }
.sf-report-member-id { color: var(--sf-ink-3); font-size: 12px; }
.sf-report-track {
  height: 16px;
  overflow: hidden;
  border: 1px solid var(--sf-line);
  background: var(--sf-surface);
}
.sf-report-fill { height: 100%; background: var(--sf-ink-3); }
.sf-report-fill.best { background: var(--sf-gain); }
.sf-report-score { text-align: right; color: var(--sf-ink); font-variant-numeric: tabular-nums; }
.sf-report-best {
  display: block;
  color: var(--sf-gain);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .1em;
}
.sf-report-note {
  margin: 16px;
  padding: 16px;
  border: 1px solid var(--sf-line);
  border-left: 2px solid var(--sf-blind);
  background: var(--sf-blind-bg);
  color: var(--sf-ink);
}
.sf-report-note-title { font-size: 16px; font-weight: 600; }
.sf-report-note-copy { margin-top: 4px; color: var(--sf-ink-2); }
.sf-report-failures {
  margin: 0;
  padding: 0;
  list-style: none;
  color: var(--sf-ink-2);
}
.sf-report-failures li { padding: 8px 0; border-top: 1px solid var(--sf-line); }
.sf-report-failures li:first-child { border-top: 0; }
.sf-report-count { color: var(--sf-ink-3); font-family: "IBM Plex Mono", ui-monospace, monospace; }
.sf-report-more {
  margin-top: 8px;
  color: var(--sf-ink-3);
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 12px;
}
.sf-report-foot { padding: 12px 16px; color: var(--sf-ink-3); font-size: 12px; }
@media (max-width: 620px) {
  .sf-report-head { display: block; }
  .sf-report-status { margin-top: 12px; white-space: normal; }
  .sf-report-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .sf-report-stat:nth-child(2) { border-right: 0; }
  .sf-report-stat:nth-child(-n+2) { border-bottom: 1px solid var(--sf-line); }
  .sf-report-member { grid-template-columns: 1fr 64px; }
  .sf-report-track { display: none; }
}
</style>"""


def report_repr(report: Report) -> str:
    """Return a concise representation without fabricating missing scores."""

    status = _status(report)
    identity = (
        f"fusion_name={report.fusion_name!r}, benchmark_id={report.benchmark_id!r}, "
        f"status={status!r}, scored={report.n_scored}/{report.n_cases}"
    )
    if report.n_scored == 0:
        return f"Report({identity}, failures={len(report.failures)})"
    score = _required(report.score, "score")
    baseline = _required(report.baseline, "baseline")
    gain = _required(report.gain, "gain")
    return (
        f"Report({identity}, score={score:.3f}, baseline={baseline:.3f}, "
        f"gain={gain:+.3f}, failures={len(report.failures)})"
    )


def report_html(report: Report) -> str:
    """Return a dependency-free rich display for Jupyter-compatible clients."""

    status = _status(report)
    return (
        f"{_STYLE}<div class='sf-report' aria-label='ScreamingFace benchmark report'>"
        f"{_header(report, status)}"
        f"{_headline(report)}"
        f"{_additional_metrics(report)}"
        f"{_member_rows(report)}"
        f"{_failure_rows(report, status)}"
        f"{_footer(report)}"
        "</div>"
    )


def _status(report: Report) -> ReportStatus:
    if report.n_scored == 0:
        return "failed"
    if report.n_scored == report.n_cases and report.complete:
        return "complete"
    return "partial"


def _header(report: Report, status: ReportStatus) -> str:
    return (
        "<div class='sf-report-head'><div>"
        f"<div class='sf-report-title'>{escape(report.fusion_name)}</div>"
        f"<div class='sf-report-meta'>{escape(report.benchmark_id)}</div>"
        "</div>"
        f"<div class='sf-report-status {status}'>"
        f"{status} · {report.n_scored}/{report.n_cases} cases scored</div></div>"
    )


def _headline(report: Report) -> str:
    if report.n_scored == 0:
        return (
            "<div class='sf-report-note'>"
            "<div class='sf-report-label'>Evaluation stopped</div>"
            "<div class='sf-report-note-title'>No benchmark score was calculated.</div>"
            "<div class='sf-report-note-copy'>Every selected case failed before a complete "
            "Fusion-versus-members comparison was available.</div></div>"
        )
    return (
        "<div class='sf-report-stats'>"
        f"{_metric(_percent(report.score), 'fusion score')}"
        f"{_metric(_gain(report.gain), 'gain over best', gain=report.gain)}"
        f"{_metric(_percent(report.baseline), 'best member')}"
        f"{_metric(str(report.n_scored) + '/' + str(report.n_cases), 'coverage')}"
        "</div>"
    )


def _additional_metrics(report: Report) -> str:
    if not report.metrics:
        return ""
    metrics = "".join(
        _metric(_percent(value), escape(name.replace("_", " ")))
        for name, value in report.metrics.items()
    )
    return (
        "<div class='sf-report-section'><span class='sf-report-label'>Additional metrics</span>"
        f"<div class='sf-report-extra'>{metrics}</div></div>"
    )


def _metric(value: str, label: str, *, gain: float | None = None) -> str:
    value_class = ""
    if gain is not None:
        value_class = " gain" if gain > 0 else (" blind" if gain < 0 else "")
    return (
        "<div class='sf-report-stat'>"
        f"<div class='sf-report-label'>{label}</div>"
        f"<div class='sf-report-value{value_class}'>{value}</div></div>"
    )


def _member_rows(report: Report) -> str:
    if report.n_scored == 0:
        return ""
    rows = "".join(
        _member_row(member_id, member.model, member.score, member.score == report.baseline)
        for member_id, member in report.members.items()
    )
    return (
        "<div class='sf-report-section'><span class='sf-report-label'>Member scores</span>"
        f"{rows}</div>"
    )


def _member_row(member_id: str, model: str, score: float | None, best: bool) -> str:
    if score is None:
        return ""
    best_class = " best" if best else ""
    best_label = "<span class='sf-report-best'>best</span>" if best else ""
    return (
        "<div class='sf-report-member'>"
        f"<div><div class='sf-report-member-model'>{escape(model)}</div>"
        f"<div class='sf-report-member-id'>{escape(member_id)}</div></div>"
        f"<div class='sf-report-track'><div class='sf-report-fill{best_class}' "
        f"style='width:{score * 100:.1f}%'></div></div>"
        f"<div class='sf-report-score'>{score:.1%}{best_label}</div></div>"
    )


def _failure_rows(report: Report, status: ReportStatus) -> str:
    if not report.failures:
        return ""
    counts: dict[str, int] = {}
    for failure in report.failures:
        counts[failure.message] = counts.get(failure.message, 0) + 1
    items = list(counts.items())
    visible = items[:3]
    rows = "".join(
        f"<li>{escape(message)} <span class='sf-report-count'>×{count}</span></li>"
        for message, count in visible
    )
    remainder = len(items) - len(visible)
    more = (
        ""
        if remainder == 0
        else f"<div class='sf-report-more'>+{remainder} more failure types</div>"
    )
    label = "Evaluation failures" if status == "failed" else "Partial coverage"
    return (
        "<div class='sf-report-section'>"
        f"<span class='sf-report-label'>{label} · {len(report.failures)}</span>"
        f"<ul class='sf-report-failures'>{rows}</ul>{more}</div>"
    )


def _footer(report: Report) -> str:
    return (
        "<div class='sf-report-foot'>"
        f"paired coverage {report.coverage:.1%} · "
        "scores use complete Fusion-versus-members cases only"
        "</div>"
    )


def _percent(value: float | None) -> str:
    number = _required(value, "score")
    return f"{number * 100:.1f}<span class='sf-report-unit'>%</span>"


def _gain(value: float | None) -> str:
    number = _required(value, "gain")
    return f"{number * 100:+.1f}<span class='sf-report-unit'> pp</span>"


def _required(value: float | None, label: str) -> float:
    if value is None:
        raise ValueError(f"a displayed {label} cannot be missing")
    return value
