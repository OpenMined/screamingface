#!/usr/bin/env python3
"""Portal smoke + brand-compliance tests (SF-266).

Self-contained: serves web/portal statically, stubs the scoreboard API with
fixtures that mirror the live response shapes (captured 2026-06-11), and
asserts both preserved behavior (security posture, status regions, deploy
marker) and the screamingface brand system (tokens, fonts, square corners,
rail/theming, no anti-rule layout).

Run:  <playwright-venv-python> web/tests/portal_smoke.py
Exit code 0 = all tests pass.

These tests intentionally live OUTSIDE web/portal/ — the Pages deploy
workflow copies web/portal/. wholesale into the published artifact.
"""

from __future__ import annotations

import json
import re
import sys
import threading
from functools import partial
from http.server import (
    BaseHTTPRequestHandler,
    SimpleHTTPRequestHandler,
    ThreadingHTTPServer,
)
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "web" / "portal"

# ---- fixtures (shapes mirror live scoreboard.screamingface.ai responses) ----

BENCHMARKS = {
    "benchmarks": [
        {
            "id": "livetruth",
            "display_name": "News Livetruth",
            "description": "OpenMined Livetruth benchmark",
            "dataset_url": "https://screamingface.ai/livetruth-masking.dataset.jsonl",
            "created_at": "2026-06-03T17:29:17.819465Z",
        },
        {
            "id": "hle",
            "display_name": "News Hallucinations",
            "description": "OpenMined HLE benchmark",
            "dataset_url": "https://github.com/openmined/HLE.jsonl",
            "created_at": "2026-06-02T17:14:22.289835Z",
        },
    ]
}

LEADERBOARD = {
    "benchmark": BENCHMARKS["benchmarks"][0],
    "entries": [
        {
            "rank": 1,
            "spec_id": "direct-google-gemini-3-1-pro-preview",
            "accuracy": 0.4545454545,
            "total_questions": 11,
            "ran_with_providers": ["google"],
            "submitted_at": "2026-06-03T18:21:29.317138Z",
            "submitted_by": "openmined-livetruth",
            "verified_by_openmined": True,
            "url4_expression": "direct-eval:results.jsonl#model=google/gemini-3.1-pro-preview",
        },
        {
            "rank": 2,
            "spec_id": "direct-openai-gpt-4-1",
            "accuracy": 0.4545454545,
            "total_questions": 11,
            "ran_with_providers": ["openai"],
            "submitted_at": "2026-06-03T18:21:29.717432Z",
            "submitted_by": "openmined-livetruth",
            "verified_by_openmined": False,
            "url4_expression": "direct-eval:results.jsonl#model=openai/gpt-4.1",
        },
        {
            "rank": 3,
            "spec_id": "direct-anthropic-claude-sonnet-4-6",
            "accuracy": 0.0,
            "total_questions": 11,
            "ran_with_providers": ["anthropic"],
            "submitted_at": "2026-06-03T18:21:30.111111Z",
            "submitted_by": None,
            "verified_by_openmined": False,
            "url4_expression": "direct-eval:results.jsonl#model=anthropic/claude-sonnet-4-6",
        },
        {
            # Defensive-path fixture: no url4_expression — the run cell must
            # render absence (em dash), never a malformed sf:// link.
            "rank": 4,
            "spec_id": "no-expression-spec",
            "accuracy": 0.1,
            "total_questions": 11,
            "ran_with_providers": ["ollama"],
            "submitted_at": "2026-06-03T18:21:31.000000Z",
            "submitted_by": None,
            "verified_by_openmined": False,
        },
    ],
}

HISTORY = {
    "spec_id": "direct-google-gemini-3-1-pro-preview",
    "benchmark_id": "livetruth",
    "submissions": [
        {
            "id": "c24aa88f-8fa7-48f8-a808-ec3040e5a6fe",
            "accuracy": 0.4545454545,
            "total_questions": 11,
            "correct_questions": 5,
            "submitted_at": "2026-06-03T18:21:29.317138Z",
            "submitted_by": "openmined-livetruth",
            "verified_by_openmined": True,
        }
    ],
}

SCORE = {
    "id": "c24aa88f-8fa7-48f8-a808-ec3040e5a6fe",
    "url4_expression": "direct-eval:results.jsonl#model=google/gemini-3.1-pro-preview",
}


class StubApi(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/v1/benchmarks":
            return self._json(200, BENCHMARKS)
        if path == "/v1/leaderboard/livetruth":
            return self._json(200, LEADERBOARD)
        if path == "/v1/leaderboard/empty":
            return self._json(
                200,
                {"benchmark": {"id": "empty", "display_name": "Empty"}, "entries": []},
            )
        if re.match(r"^/v1/leaderboard/livetruth/[^/]+/history$", path):
            return self._json(200, HISTORY)
        if path.startswith("/v1/scores/"):
            return self._json(200, SCORE)
        return self._json(404, {"detail": "not found"})


FIXTURE_JSONL = "\n".join(
    [
        '{"qa_id": "q1", "dataset": "d", "question": "What?"}',
        '{"qa_id": "q2", "question": "Who?", "meta": {"k": 1}}',
        '{"qa_id": "q3", "dataset": "d", "question": ""}',
    ]
)


class QuietStatic(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        # Site-root data file, as published by the deploy workflow.
        if self.path.split("?")[0] == "/fixture.dataset.jsonl":
            body = FIXTURE_JSONL.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


results: list[tuple[str, str, str]] = []


def check(test_id: str, desc: str, ok: bool, detail: str = ""):
    results.append(
        (test_id, desc, "PASS" if ok else "FAIL" + (f" — {detail}" if detail else ""))
    )


def section(test_id: str, desc: str, fn):
    """Run a test block; an exception (e.g. selector timeout) records a FAIL
    for the whole block instead of aborting the suite."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — harness boundary, reported not hidden
        check(
            test_id,
            desc,
            False,
            f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}",
        )


def main() -> int:
    # ---- static (non-browser) gates ----
    marker = '<script src="main.js" defer></script>'
    for name in ("index.html", "benchmark.html", "spec.html"):
        text = (PORTAL / name).read_text()
        check("T1", f"deploy marker present in {name}", marker in text)

    js_sources = "".join(p.read_text() for p in PORTAL.glob("*.js"))
    # Property-access patterns only — the word "innerHTML" legitimately appears
    # in main.js's security-posture comment.
    for sink in (
        r"\.innerHTML\b",
        r"\.insertAdjacentHTML\s*\(",
        r"document\.write\s*\(",
    ):
        check(
            "T2", f"no {sink} usage in portal JS", re.search(sink, js_sources) is None
        )

    # Published data receipts: sf.json URL4 specs and the scoreboard's
    # livetruth dataset_url reference these at the site root — the deploy
    # workflow must package them or the live URLs 404 (regression of
    # 2026-06-11: a main deploy dropped the probe-branch-published copies).
    workflow_text = (ROOT / ".github" / "workflows" / "deploy-website.yml").read_text()
    for artifact in (
        "output_artifacts/eval_results/livetruth-latest.eval.jsonl",
        "output_artifacts/eval_results/livetruth-masking.dataset.jsonl",
    ):
        check(
            "T21",
            f"deploy workflow publishes {Path(artifact).name}",
            artifact in workflow_text,
        )
        check(
            "T21", f"{Path(artifact).name} tracked in repo", (ROOT / artifact).is_file()
        )

    # GitHub Pages serves .jsonl as application/octet-stream (forced
    # download) and custom MIME types are not configurable — .txt twins
    # render inline in the browser.
    for twin in (
        "livetruth-latest.eval.jsonl.txt",
        "livetruth-masking.dataset.jsonl.txt",
    ):
        check(
            "T22",
            f"deploy workflow publishes browser-viewable twin {twin}",
            twin in workflow_text,
        )

    api_srv = ThreadingHTTPServer(("127.0.0.1", 0), StubApi)
    api_port = api_srv.server_address[1]
    threading.Thread(target=api_srv.serve_forever, daemon=True).start()

    static_srv = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietStatic, directory=str(PORTAL))
    )
    static_port = static_srv.server_address[1]
    threading.Thread(target=static_srv.serve_forever, daemon=True).start()

    base = f"http://127.0.0.1:{static_port}"
    api = f"http://127.0.0.1:{api_port}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        ctx.add_init_script(f"window.SCOREBOARD_API_BASE = {json.dumps(api)};")
        page = ctx.new_page()
        # Uncaught JS exceptions only — console "error" entries include the
        # deliberate 404 fetch exercised by the error-path test.
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        pages = {
            "index": f"{base}/index.html",
            "benchmark": f"{base}/benchmark.html?id=livetruth",
            "spec": (
                f"{base}/spec.html?benchmark=livetruth&spec=direct-google-gemini-3-1-pro-preview"
            ),
        }

        # ---- brand shell assertions on every page ----
        for label, url in pages.items():
            page.goto(url)
            page.wait_for_load_state("networkidle")

            check(
                "T3",
                f"{label}: tokens.css linked",
                page.locator('link[href="tokens.css"]').count() == 1,
            )
            check(
                "T3",
                f"{label}: style.css linked",
                page.locator('link[href="style.css"]').count() == 1,
            )
            check(
                "T3",
                f"{label}: data-theme set on <html>",
                page.get_attribute("html", "data-theme") in ("light", "dark"),
            )
            check(
                "T3",
                f"{label}: rail with brand + theme toggle",
                page.locator(".rail .brand").count() == 1
                and page.locator("#theme-toggle").count() == 1,
            )
            check("T3", f"{label}: .foot present", page.locator(".foot").count() == 1)

            check(
                "T4",
                f"{label}: no hero/proof-card anti-rule layout",
                page.locator(
                    ".hero, .proof-grid, .proof-card, .summary-card, .card-grid"
                ).count()
                == 0,
            )

            h1_font = page.locator("h1").first.evaluate(
                "el => getComputedStyle(el).fontFamily"
            )
            body_font = page.locator("body").evaluate(
                "el => getComputedStyle(el).fontFamily"
            )
            check(
                "T5", f"{label}: h1 is EB Garamond", "EB Garamond" in h1_font, h1_font
            )
            check(
                "T5",
                f"{label}: body is IBM Plex Sans",
                "IBM Plex Sans" in body_font,
                body_font,
            )

            ext = page.locator('.foot a[href^="https://"]')
            rels = [ext.nth(i).get_attribute("rel") or "" for i in range(ext.count())]
            check(
                "T14",
                f"{label}: external footer links rel-hardened",
                len(rels) >= 2 and all("noopener" in r for r in rels),
                str(rels),
            )
            check(
                "T15",
                f"{label}: theme toggle has accessible name",
                bool(page.get_attribute("#theme-toggle", "aria-label")),
            )

        # ---- index: live leaderboard reference page ----
        def t_index():
            page.goto(pages["index"])
            page.wait_for_selector("#live-table tbody tr", timeout=8000)
            rows = page.locator("#live-table tbody tr")
            check(
                "T7",
                "index: headline matches live brand reference",
                page.locator("h1").first.text_content() == "The leaderboard, live.",
            )
            check(
                "T7",
                "index: live scoreboard status note rendered",
                page.locator("#live-status.note.gain").count() == 1
                and "scoreboard.screamingface.ai"
                in (page.locator("#live-status").text_content() or ""),
            )
            check(
                "T7",
                "index: one live leaderboard row per API entry",
                rows.count() == 4,
                f"got {rows.count()}",
            )
            check(
                "T7",
                "index: live table uses configuration label",
                "direct-google-gemini-3-1-pro-preview"
                in (rows.first.text_content() or ""),
            )
            check(
                "T7",
                "index: live chart has one row per API entry",
                page.locator("#live-chart .row").count() == 4,
                f"got {page.locator('#live-chart .row').count()}",
            )
            check(
                "T7",
                "index: only top-ranked live chart fill is green",
                page.locator("#live-chart .fill.sota").count() == 1
                and page.locator("#live-chart .fill.ens").count() == 3,
            )
            check(
                "T7",
                "index: first live table row is highlighted as SOTA",
                page.locator("#live-table tbody tr.sota").count() == 1,
            )
            check(
                "T7",
                "index: run links use branded run affordance",
                rows.first.locator("a.btn.ghost").count() == 1
                and "▸ run" in (rows.first.locator("a.btn.ghost").text_content() or "")
                and (
                    rows.first.locator("a.btn.ghost").get_attribute("href") or ""
                ).startswith("sf://run?spec="),
            )

        section("T7", "index: live leaderboard block", t_index)

        # ---- benchmark: table, sota, badge, sorting, radius ----
        def t_benchmark():
            page.goto(pages["benchmark"])
            page.wait_for_selector("#leaderboard-body tr", timeout=8000)
            check(
                "T8",
                "benchmark: 4 leaderboard rows",
                page.locator("#leaderboard-body tr").count() == 4,
            )
            check(
                "T8",
                "benchmark: tr.sota marks tied-best rows",
                page.locator("#leaderboard-body tr.sota").count() == 2,
                f"got {page.locator('#leaderboard-body tr.sota').count()}",
            )
            check(
                "T16",
                "benchmark: sota rows carry sr-only text (not color-only)",
                page.locator("#leaderboard-body tr.sota .sr-only").count() == 2,
            )
            no_expr_cells = page.locator(
                "#leaderboard-body tr", has_text="no-expression-spec"
            ).locator("td.col-run")
            check(
                "T17",
                "benchmark: missing url4_expression renders em dash, no control",
                no_expr_cells.count() == 1
                and no_expr_cells.first.locator("a, button").count() == 0
                and "—" in (no_expr_cells.first.text_content() or ""),
            )
            check(
                "T19",
                "benchmark: rows with expressions get compact Copy buttons",
                page.locator("#leaderboard-body td.col-run button.btn.ghost").count()
                == 3
                and (
                    page.locator(
                        "#leaderboard-body td.col-run button.btn.ghost"
                    ).first.text_content()
                    or ""
                ).strip()
                == "Copy",
            )

            # Cells must keep the brand table padding — the old `wrap` cell
            # class collided with the brand's `.wrap` page-column class and
            # inherited 40px/96px page padding, inflating rows to ~180px.
            spec_pad = (
                page.locator("#leaderboard-body tr")
                .first.locator("td")
                .nth(1)
                .evaluate("el => getComputedStyle(el).padding")
            )
            check(
                "T20",
                "benchmark: spec cell keeps table padding (no .wrap collision)",
                spec_pad == "8px 12px",
                spec_pad,
            )
            row_h = page.locator("#leaderboard-body tr").first.evaluate(
                "el => el.offsetHeight"
            )
            check(
                "T20",
                "benchmark: row height is content-sized (< 90px)",
                row_h < 90,
                f"{row_h}px",
            )

            # ---- climb accuracy chart (viz-a direction, SF-266 phase 2a) ----
            climb = page.locator("#leaderboard-climb")
            check(
                "T18",
                "benchmark: climb chart present and visible",
                climb.count() == 1 and climb.is_visible(),
            )
            check(
                "T18",
                "benchmark: climb has one row per entry",
                climb.locator(".row").count() == 4,
                f"got {climb.locator('.row').count()}",
            )
            check(
                "T18",
                "benchmark: tied-best entries get sota fills",
                climb.locator(".fill.sota").count() == 2
                and climb.locator(".fill.base").count() == 2,
            )
            best_width = climb.locator(".fill.sota").first.evaluate(
                "el => el.style.width"
            )
            check(
                "T18",
                "benchmark: fill width is the accuracy percentage",
                best_width == "45.5%",
                best_width,
            )
            zero_row = climb.locator(
                ".row", has_text="direct-anthropic-claude-sonnet-4-6"
            )
            check(
                "T18",
                "benchmark: 0% entry renders a 0-width base fill",
                zero_row.locator(".fill.base").first.evaluate("el => el.style.width")
                == "0%",
            )
            check(
                "T18",
                "benchmark: climb rows show formatted values",
                "45.5%" in (climb.locator(".val").first.text_content() or ""),
            )
            check(
                "T18",
                "benchmark: climb is aria-hidden (table is the accessible source)",
                climb.get_attribute("aria-hidden") == "true",
            )
            check(
                "T8",
                "benchmark: best accuracy stat in gain style",
                page.locator(".stats .v.gain").count() >= 1
                and "45.5%" in (page.locator("#summary-best").text_content() or ""),
            )
            badge = page.locator(".badge-verified").first
            check("T8", "benchmark: verified badge present", badge.count() == 1)
            radius = badge.evaluate("el => getComputedStyle(el).borderRadius")
            check("T6", "benchmark: badge has square corners", radius == "0px", radius)
            acc_th = page.locator('th[aria-sort="descending"]')
            check(
                "T8",
                "benchmark: default sort accuracy desc",
                acc_th.count() == 1 and "Accuracy" in (acc_th.text_content() or ""),
            )
            page.locator(".sort-button", has_text="Rank").click()
            check(
                "T8",
                "benchmark: clicking Rank updates aria-sort",
                page.locator('th[aria-sort="ascending"]').count() == 1,
            )
            note_radius = page.locator(".note").first.evaluate(
                "el => getComputedStyle(el).borderRadius"
            )
            check(
                "T6",
                "benchmark: note square corners",
                note_radius == "0px",
                note_radius,
            )

        section("T8", "benchmark: leaderboard block", t_benchmark)

        # ---- spec: history + run button ----
        def t_spec():
            page.goto(pages["spec"])
            page.wait_for_selector("#history-body tr", timeout=8000)
            check(
                "T9",
                "spec: history row rendered",
                page.locator("#history-body tr").count() == 1,
            )
            page.wait_for_selector("#run-region button.btn", timeout=8000)
            btn = page.locator("#run-region button.btn")
            check(
                "T9",
                "spec: Copy button rendered with accessible name",
                btn.count() == 1
                and (btn.text_content() or "").strip() == "Copy"
                and "direct-google" in (btn.get_attribute("aria-label") or ""),
            )
            btn.click()
            clipboard = page.evaluate("() => navigator.clipboard.readText()")
            check(
                "T9",
                "spec: click copies sf://run link with encoded expression",
                clipboard.startswith("sf://run?spec=")
                and "expression=" in clipboard
                and "%23model%3D" in clipboard,
                clipboard,
            )
            check(
                "T9",
                "spec: button gives copied feedback",
                "copied" in (btn.text_content() or "").lower(),
            )
            btn_radius = btn.evaluate("el => getComputedStyle(el).borderRadius")
            check("T6", "spec: .btn square corners", btn_radius == "0px", btn_radius)

        section("T9", "spec: history block", t_spec)

        # ---- data viewer (jsonl rendered in-page, SF-266) ----
        def t_viewer():
            page.goto(f"{base}/data.html?file=fixture.dataset.jsonl")
            page.wait_for_selector("#data-body tr", timeout=8000)
            rows = page.locator("#data-body tr")
            check("T23", "viewer: one table row per jsonl line", rows.count() == 3)
            head = page.locator("#data-head").text_content() or ""
            check(
                "T23",
                "viewer: columns are the union of row keys",
                all(k in head for k in ("qa_id", "dataset", "question", "meta")),
                head,
            )
            q2 = page.locator("#data-body tr", has_text="q2")
            check(
                "T23",
                "viewer: missing field renders em dash",
                "—" in (q2.text_content() or ""),
            )
            check(
                "T23",
                "viewer: nested object rendered as JSON",
                '{"k":1}' in (q2.text_content() or "").replace(" ", ""),
            )
            check(
                "T23",
                "viewer: meta line shows row count",
                "3 rows" in (page.locator("#data-meta").text_content() or ""),
            )
            raw_href = page.locator("#data-raw").get_attribute("href") or ""
            check(
                "T23",
                "viewer: raw download link",
                raw_href == "/fixture.dataset.jsonl",
                raw_href,
            )

            page.goto(f"{base}/data.html?file=missing.jsonl")
            page.wait_for_selector(".state-error", timeout=8000)
            check("T23", "viewer: missing file shows error state", True)
            page.goto(f"{base}/data.html?file=../../etc/passwd")
            page.wait_for_selector(".state-error", timeout=8000)
            check("T23", "viewer: invalid file param rejected", True)

        section("T23", "data viewer block", t_viewer)

        # ---- theme toggle persistence ----
        def t_theme():
            page.goto(pages["index"])
            page.wait_for_selector("#theme-toggle", timeout=8000)
            page.click("#theme-toggle")
            check(
                "T10",
                "theme: toggle switches to dark",
                page.get_attribute("html", "data-theme") == "dark",
            )
            page.reload()
            page.wait_for_load_state("domcontentloaded")
            check(
                "T10",
                "theme: dark persists across reload",
                page.get_attribute("html", "data-theme") == "dark",
            )
            page.click("#theme-toggle")  # back to light for cleanliness

        section("T10", "theme toggle block", t_theme)

        # ---- error + empty states ----
        def t_states():
            page.goto(f"{base}/benchmark.html?id=missing")
            page.wait_for_selector(".state-error", timeout=8000)
            check(
                "T11",
                "error state on unknown benchmark",
                "not found"
                in (page.locator(".state-error").text_content() or "").lower(),
            )
            page.goto(f"{base}/benchmark.html?id=empty")
            page.wait_for_selector(".state-empty", timeout=8000)
            check(
                "T12",
                "empty state on zero entries",
                page.locator(".state-empty").count() == 1,
            )

        section("T11", "error/empty state block", t_states)

        check(
            "T13",
            "no uncaught JS exceptions across pages",
            not page_errors,
            "; ".join(page_errors[:3]),
        )

        browser.close()

    api_srv.shutdown()
    static_srv.shutdown()

    width = max(len(d) for _, d, _ in results)
    failed = 0
    for tid, desc, outcome in results:
        print(f"{tid:4} {desc:<{width}}  {outcome}")
        if outcome.startswith("FAIL"):
            failed += 1
    print(f"\n{len(results) - failed}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
