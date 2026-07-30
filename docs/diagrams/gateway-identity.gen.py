#!/usr/bin/env python3
"""Regenerate the gateway-identity diagrams: `.mmd` -> `.svg` + `.png`, and sync the index page.

The `.mmd` files are the SOURCE. They stay diffable in review and render inline on GitHub, so the
thing a developer edits is the thing a reviewer reads; this script keeps the committed SVG/PNG — and
the inline copies in `gateway-identity.md` — in step with them. (The older
`url4-cloud-execution-flows.gen.py` hand-writes its SVG instead: that one needs pixel control over a
bespoke sequence layout, these do not.)

Usage:  python3 docs/diagrams/gateway-identity.gen.py

Requires `npx`, which fetches @mermaid-js/mermaid-cli (and a headless Chromium) on first run.

WHY mermaid-cli renders the PNG too, rather than `rsvg-convert` as the older generators do: mermaid
puts its labels in `<foreignObject>` (real HTML, which is what makes `<b>` and wrapped multi-line
labels work). rsvg-convert cannot render foreignObject, so it silently produced diagrams with EVERY
label missing. Forcing `htmlLabels: false` to avoid that is not a fix either — rsvg then collapses
the whitespace in mermaid's `tspan` output and every label comes out as "onePodperrun". Chromium
renders both faithfully, so both outputs come from mermaid-cli.

CONSEQUENCE, worth knowing before embedding these elsewhere: the SVGs contain foreignObject. They
render correctly in a browser, on GitHub, and in any docs site — but a plain SVG rasterizer will
drop the text. Use the PNG in those places.

Two mermaid traps to remember when editing a `.mmd`: a `;` inside label text is a STATEMENT
SEPARATOR and splits the line, and `<...>` in message text is parsed as an HTML tag. `Note over X`
also sizes to that participant's box rather than to its text, so long notes span two participants.
"""

import pathlib
import re
import subprocess
import sys

OUT = pathlib.Path(__file__).parent
MERMAID_CLI = "@mermaid-js/mermaid-cli@11.16.0"
PNG_SCALE = "2"
INDEX = OUT / "gateway-identity.md"

DIAGRAMS = [
    ("gateway-identity-flow", 1500),
    ("gateway-identity-topology", 1400),
    ("gateway-identity-auth-modes", 1400),
]


def _mermaid(mmd: pathlib.Path, out: pathlib.Path, width: int, *extra: str) -> None:
    subprocess.run(
        [
            "npx", "-y", MERMAID_CLI,
            "-i", str(mmd),
            "-o", str(out),
            # An explicit width keeps the layout stable across mermaid versions; the dark canvas
            # comes from each diagram's own `themeVariables`, so the page behind it stays neutral.
            "-w", str(width),
            "-b", "transparent",
            *extra,
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )


def render(stem: str, width: int) -> bool:
    mmd = OUT / f"{stem}.mmd"
    if not mmd.exists():
        print(f"MISSING  {mmd.name}")
        return False
    try:
        _mermaid(mmd, OUT / f"{stem}.svg", width)
        _mermaid(mmd, OUT / f"{stem}.png", width, "-s", PNG_SCALE)
    except FileNotFoundError:
        print("FAIL  npx not found — cannot render mermaid")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"FAIL  {mmd.name}: {exc.stderr.decode()[-400:]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"FAIL  {mmd.name}: mermaid render timed out")
        return False
    print(f"OK  {stem}.svg  +  {stem}.png")
    return True


def sync_index() -> bool:
    """Rewrite the fenced mermaid blocks in the index page from the `.mmd` files.

    The index embeds the diagrams inline so they render on GitHub, which would otherwise be a second
    copy free to drift from the source this script renders. Each block is delimited by an HTML
    comment naming its `.mmd`, so the `.mmd` stays the single source and the page cannot silently
    disagree with the committed SVG/PNG.

    The `%%{init}%%` line is stripped: the images carry the dark canvas, while the inline copy
    inherits GitHub's own light/dark theme.
    """
    if not INDEX.exists():
        print(f"MISSING  {INDEX.name}")
        return False
    text = INDEX.read_text()
    for stem, _ in DIAGRAMS:
        body = "\n".join(
            line
            for line in (OUT / f"{stem}.mmd").read_text().strip().splitlines()
            if not line.startswith("%%{init")
        ).strip()
        pattern = re.compile(
            rf"(<!-- source: {re.escape(stem)}\.mmd -->\n```mermaid\n).*?(\n```)",
            re.DOTALL,
        )
        if not pattern.search(text):
            print(f"FAIL  {INDEX.name}: no marked block for {stem}.mmd")
            return False
        text = pattern.sub(lambda m: m.group(1) + body + m.group(2), text, count=1)
    INDEX.write_text(text)
    print(f"OK  {INDEX.name}  (mermaid blocks synced from source)")
    return True


if __name__ == "__main__":
    ok = all(render(stem, w) for stem, w in DIAGRAMS)
    sys.exit(0 if (sync_index() and ok) else 1)
