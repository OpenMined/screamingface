---
ticket: OME-<N>   # DEFERRED — Linear MCP OAuth unreachable ("invalid uri"); owner authorized proceeding. File + backfill Refs before merge.
stack: screamingface
status: in_progress
started: 2026-08-13
finished:
---

# OME-<N> — Report panel: markdown answers, tighter spacing, better URL4

## Intent

The notebook Report panel (`report = sf.evaluate(...)` → `_repr_html_`) renders the model
**answer** as raw escaped text in a monospace `<pre>`, so markdown reads as literal noise;
the **domain tag** sits flush against the **question**; the **case / answer / criteria**
blocks run together; and the **URL4** disclosure shows its expression flush to the panel
edges, with the operation-step chips jammed against it and no way to copy it. This unit
renders the answer as safe markdown and gives the pane + URL4 block a calmer reading rhythm —
staying within the existing hand-built HTML/CSS, no JS framework, no new core dependency.

## Planned changes

- **New** `packages/screamingface/src/screamingface/_ui/markdown.py` — `render_markdown(text)`:
  escape-first, XSS-safe markdown subset (tamed headings h4–h6, bold/italic, inline + fenced
  code, ul/ol, paragraphs, safe http/https/mailto links only).
- **Modify** `packages/screamingface/src/screamingface/_ui/report_view.py`:
  - `_pane_html` — answer becomes `<div class='sf-report__md'>{render_markdown(answer)}</div>`;
    domain chips get `.sf-pane__tags` (drop inline `margin-top:8px`).
  - `_recipe_html` — inset `.sf-report__url4` wrapper (side padding + gap from step chips) +
    a copy button (`onclick` `navigator.clipboard.writeText`, **full** url4 in `data-u4`).
  - `_STYLE` — add `.sf-report__md`, `.sf-pane__tags`, `.sf-report__url4*`, `.sf-report__copy`;
    bump `.sf-detail__k` to `margin:18px 0 6px`.
- **New** `packages/screamingface/tests/test_markdown.py`; **extend**
  `packages/screamingface/tests/test_report_panel.py`.

## Test plan (RED first)

- `test_markdown.py`: headings→tamed `<h4..6>`; `**bold**`→`<strong>`, `*em*`→`<em>`,
  `` `code` ``→`<code>`; fenced ```` ``` ````→`<pre><code>`; `-`/`1.`→`<ul>`/`<ol>`; safe
  `http(s)` link renders with `rel=noopener`; **`javascript:` link rejected** (rendered inert);
  **XSS: `<script>` / `<img onerror=...>` in input stays escaped** (invariant).
- `test_report_panel.py`: answer markdown renders (`## H`→`<h`, `**b**`→`<strong>`, fence→`<pre`);
  existing `test_untrusted_case_and_judge_text_is_escaped` stays green with a `<script>` answer;
  URL4 disclosure carries `sf-report__copy` whose `data-u4` holds the **full** url4; expression
  wrapped in `.sf-report__url4`; `.sf-pane__tags` present.

## Acceptance

- Answer renders as real markdown in the pane; untrusted text remains XSS-safe.
- Clear space between domain tag → question, and between case / answer / criteria.
- URL4 expression is inset with side padding, spaced from the step chips, and copyable
  (full expression), verified in light + dark.
- All card gates green (`run_gates.py screamingface`), coverage ≥95%.

## Outcome (fill at the end — required before COMMIT)

- **Actual files (as planned):**
  - new `src/screamingface/_ui/markdown.py` — `render_markdown` (escape-first, rule-table
    dispatch; asterisk-only emphasis so snake_case/dunder survive).
  - `src/screamingface/_ui/report_view.py` — answer → `.sf-report__md`; `.sf-pane__tags`;
    `.sf-detail__k` → `margin:18px 0 6px`; `_recipe_html` inset `.sf-report__url4` + copy button.
  - new `tests/test_markdown.py` (18 tests); `tests/test_report_panel.py` (+4 tests, +local
    `_answer_case` fixture — shared `case()`/`candidate()` left untouched per append-only).
- **Commits:** <sha — pending: `Refs` backfilled once OME-N is filed>
- **Gates:** `run_gates.py screamingface` → ALL GREEN (append-only, ruff, format, pyright,
  pytest cov≥95, check_notebooks, uv build, check_distribution). New tests: 22 (18 + 4).
- **Visual:** `/tmp/report_preview.html` — 14/14 structural checks (markdown answer, domain-tag
  row, inset URL4 + copy button). Owner light/dark eyeball pending.
- **Deviations:** Linear MCP OAuth was unreachable at start ("invalid uri") — owner authorized
  proceeding; branch/ledger use a descriptor, ticket + `Refs` backfilled before merge.
