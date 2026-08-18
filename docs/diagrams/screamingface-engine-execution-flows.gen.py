#!/usr/bin/env python3
"""OME-555 — screamingface-engine execution flow diagrams (diagramming skill design system).

Sequence-style flow: coloured actor boxes + lifelines + numbered interaction arrows with label
chips, on the dark slate canvas with the universal text halo. Emits standalone SVG (deliverable is
SVG+PNG per repo convention, not the skill's HTML wrapper).
"""

import html
import pathlib
import subprocess

OUT = pathlib.Path(__file__).parent

# actor id -> (label, colour-key)
ACTORS = [
    ("client", "Client", "external"),
    ("app", "App  ·  REST + WS", "backend"),
    ("nats", "NATS  ·  JetStream", "bus"),
    ("runner", "Runner  ·  k8s Job", "compute"),
]
COLOURS = {  # fill, stroke
    "external": ("rgba(30,41,59,0.55)", "#94a3b8"),
    "backend": ("rgba(6,78,59,0.45)", "#34d399"),
    "bus": ("rgba(251,146,60,0.32)", "#fb923c"),
    "compute": ("rgba(8,51,68,0.5)", "#22d3ee"),
}
KEY_OF = {aid: key for aid, _, key in ACTORS}

LANE_GAP = 320
MARGIN_X = 180
BOX_W, BOX_H = 200, 54
TOP = 92
FIRST_STEP = TOP + BOX_H + 66
STEP_GAP = 60
FONT = "JetBrains Mono, ui-monospace, monospace"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def chip(
    cx: float, cy: float, text: str, size: int = 11, colour: str = "#e2e8f0"
) -> str:
    w = len(text) * size * 0.6 + 14
    h = size * 1.05 + 8
    x = cx - w / 2
    y = cy - h / 2
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" '
        f'fill="rgba(15,23,42,0.92)" stroke="rgba(148,163,184,0.55)" stroke-width="1"/>'
        f'<text x="{cx:.1f}" y="{cy + size * 0.36:.1f}" text-anchor="middle" '
        f'font-size="{size}" fill="{colour}">{esc(text)}</text>'
    )


def make(
    title: str, subtitle: str, steps: list[tuple[str, str, str, str]], fname: str
) -> None:
    n_actors = len(ACTORS)
    lane_x = {aid: MARGIN_X + i * LANE_GAP for i, (aid, _, _) in enumerate(ACTORS)}
    width = MARGIN_X * 2 + (n_actors - 1) * LANE_GAP
    life_bottom = FIRST_STEP + (len(steps) - 1) * STEP_GAP + 34
    height = life_bottom + 66

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="{FONT}" font-weight="500">'
    )
    parts.append(
        "<style>svg text{paint-order:stroke fill;stroke:rgba(2,6,23,0.75);stroke-width:1;"
        "stroke-linejoin:round;stroke-linecap:round;}</style>"
    )
    # defs: grid + one arrowhead per actor stroke colour
    heads = "".join(
        f'<marker id="ah-{k}" markerWidth="9" markerHeight="7" refX="8" refY="3.5" '
        f'orient="auto"><polygon points="0 0, 9 3.5, 0 7" fill="{c[1]}"/></marker>'
        for k, c in COLOURS.items()
    )
    parts.append(
        '<defs><pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">'
        '<path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" stroke-width="0.5"/>'
        f"</pattern>{heads}</defs>"
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="#020617"/>')
    parts.append(f'<rect width="{width}" height="{height}" fill="url(#grid)"/>')

    # title + subtitle
    parts.append(
        f'<text x="{width / 2:.0f}" y="40" text-anchor="middle" font-size="19" '
        f'font-weight="700" fill="#f1f5f9">{esc(title)}</text>'
    )
    parts.append(
        f'<text x="{width / 2:.0f}" y="62" text-anchor="middle" font-size="11" '
        f'fill="#94a3b8">{esc(subtitle)}</text>'
    )

    # lifelines + actor header boxes
    for aid, label, key in ACTORS:
        fill, stroke = COLOURS[key]
        cx = lane_x[aid]
        parts.append(
            f'<line x1="{cx}" y1="{TOP + BOX_H}" x2="{cx}" y2="{life_bottom}" '
            f'stroke="{stroke}" stroke-width="1" stroke-dasharray="3,5" opacity="0.4"/>'
        )
        bx = cx - BOX_W / 2
        parts.append(
            f'<rect x="{bx}" y="{TOP}" width="{BOX_W}" height="{BOX_H}" rx="6" fill="#0f172a"/>'
        )
        parts.append(
            f'<rect x="{bx}" y="{TOP}" width="{BOX_W}" height="{BOX_H}" rx="6" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{cx}" y="{TOP + BOX_H / 2 + 4:.0f}" text-anchor="middle" font-size="12" '
            f'font-weight="600" fill="#e2e8f0">{esc(label)}</text>'
        )

    # steps
    dash = {"return": "6,4", "async": "2,3"}
    for i, (frm, to, label, kind) in enumerate(steps):
        y = FIRST_STEP + i * STEP_GAP
        x1, x2 = lane_x[frm], lane_x[to]
        key = KEY_OF[frm]
        stroke = COLOURS[key][1]
        d = dash.get(kind)
        inset = 7 if x2 > x1 else -7
        da = f' stroke-dasharray="{d}"' if d else ""
        parts.append(
            f'<line x1="{x1 + inset}" y1="{y}" x2="{x2 - inset}" y2="{y}" stroke="{stroke}" '
            f'stroke-width="1.6"{da} marker-end="url(#ah-{key})"/>'
        )
        parts.append(chip((x1 + x2) / 2, y - 16, label, 11, "#e2e8f0"))

    parts.append(
        f'<text x="{width / 2:.0f}" y="{height - 24:.0f}" text-anchor="middle" font-size="10" '
        f'fill="#475569">screamingface-engine · {esc(fname)} · 2026-07-22 · companion to docs/protocol.md · OME-555</text>'
    )
    parts.append("</svg>")

    svg = "\n".join(parts)
    svg_path = OUT / f"{fname}.svg"
    svg_path.write_text(svg)
    # render PNG (verify the SVG is valid + renders) — feedback rule: rsvg-convert
    png_path = OUT / f"{fname}.png"
    try:
        subprocess.run(
            ["rsvg-convert", "-w", str(width * 2), "-o", str(png_path), str(svg_path)],
            check=True,
            capture_output=True,
        )
        print(f"OK  {svg_path.name}  +  {png_path.name}  ({width}x{height})")
    except FileNotFoundError:
        print(f"OK  {svg_path.name}  (rsvg-convert NOT found — PNG skipped)")
    except subprocess.CalledProcessError as exc:
        print(f"SVG written but rsvg failed: {exc.stderr.decode()[:200]}")


SYNC = [
    ("client", "app", "1  POST /token", "call"),
    ("app", "client", "2  200 { token }   (topic = sub)", "return"),
    ("client", "app", "3  WS /ws?ticket=token", "call"),
    ("app", "nats", "4  subscribe(topic)   ·   428 gate opens", "call"),
    ("client", "app", "5  GET /?q=url4   (URL4-Capability)", "call"),
    ("app", "runner", "6  schedule Job(topic, url4)", "call"),
    ("runner", "nats", "7  Started · log · span · cost.usage", "call"),
    ("nats", "client", "8  live CloudEvents (WS)", "async"),
    ("runner", "nats", "9  Result · Terminated(succeeded)", "call"),
    ("nats", "app", "10  terminal frame   (≤ SYNC_MAX_WAIT)", "async"),
    ("app", "client", "11  200  Result body", "return"),
]

make(
    "Synchronous execution",
    "GET / holds until the terminal frame (bounded by SYNC_MAX_WAIT) and returns the Result body",
    SYNC,
    "screamingface-engine-execution-sync",
)

ASYNC = [
    ("client", "app", "1  POST /token", "call"),
    ("app", "client", "2  200 { token }", "return"),
    ("client", "app", "3  WS /ws?ticket=token", "call"),
    ("app", "nats", "4  subscribe(topic)", "call"),
    ("client", "app", "5  GET /?q=url4   (Prefer: respond-async)", "call"),
    ("app", "runner", "6  schedule Job(topic, url4)", "call"),
    ("app", "client", "7  202 + Location / Link   (Preference-Applied)", "return"),
    ("runner", "nats", "8  Started · log · cost · Result · Terminated", "call"),
    ("nats", "client", "9  CloudEvents stream (WS) — Result arrives here", "async"),
]

make(
    "Asynchronous execution",
    "Prefer: respond-async returns 202 immediately; the Result arrives on the WebSocket stream",
    ASYNC,
    "screamingface-engine-execution-async",
)

STREAM = [
    ("client", "app", "1  WS /ws?ticket=token", "call"),
    ("app", "nats", "2  subscribe(topic)", "call"),
    ("runner", "nats", "3  Started (seq 1) · log (2) · span (3)", "call"),
    ("nats", "client", "4  frames carry a monotonic sequence", "async"),
    ("client", "app", "5  (disconnect)", "return"),
    ("client", "app", "6  WS /ws?ticket=token   (re-attach)", "call"),
    ("client", "app", "7  ai.url4.attach { from_sequence: 3 }", "call"),
    ("app", "nats", "8  replay from seq 4", "call"),
    ("nats", "client", "9  cost.usage (4) · Result (5) · Terminated (6)", "async"),
    ("client", "app", "10  ai.url4.stop   (optional cancel)", "call"),
    ("app", "runner", "11  stop Job + purge stream", "call"),
]

make(
    "Streaming · resume · cancel",
    "WebSocket frames carry a monotonic sequence; a client can re-attach and replay, or cancel",
    STREAM,
    "screamingface-engine-execution-stream",
)
