---
ticket: OME-635
stack: screamingface
status: done
started: 2026-07-27
finished: 2026-07-27
---

# OME-635 — recipe full-form pretty-print + Fusion member/reducer detail

## Intent

User feedback on the OME-630 recipe view: keep the url4 in its **full form** (don't extract
params/prompt into labelled fields) and just reflow it by bracket/section boundaries; and add
the members'/reducer's prompts + params to the Fusion card as a collapsed section. Also fixes
the `$…$` MathJax hazard (JupyterLab runs a latexTypesetter on HTML output) by rendering the
recipe inside a `<pre>` (MathJax skips pre/code).

## Planned changes

- `_url4_format.py`: replace `_structured_html` (AST field extraction) with `_pretty_url4`
  (quote/backslash-aware reflow that indents on `(){}` and top-level `,`, keeping every other
  character verbatim). `recipe_details_html` renders the reflow inside `<pre class='sf-url4__pre'>`;
  copy button copies the exact raw via a `data-url4` attribute (no hidden element). Drop the
  `url4.build`/Url4Error path (string reflow cannot raise).
- `_card_display.py`: add `_fusion_detail_html(fusion)` — a collapsed `<details>` listing each
  member's prompt + params and the reducer's prompt + params; embed it in `fusion_card_html`.
  Update `.sf-url4*` CSS (pre) and add `.sf-detail*` classes.
- `_card_display.py` (scope 3, added per user): a shared `_prompt_field`/`_collapsible` helper
  that renders long text (prompts) as a collapsed `<details>` with a short preview; make the
  **Benchmark card verbose** — grader (Rubric → model/passes/params/prompt-collapsed),
  aggregator, tools, max_tool_calls, source (engine vs N local cases), engine routes
  (collapsed); make the **Rubric card** collapse its prompt; Model/Fusion prompts use the same
  collapsible.
- Tests: new `tests/test_ome635_recipe_fullform.py` + benchmark/grader verbosity assertions.

## Test plan (RED first)

- `_pretty_url4`: brackets indent; top-level commas break; a quoted intent containing
  `,`, `(`, `)`, and an escaped `\'` is preserved verbatim (no breaks inside the quote).
- `recipe_details_html`: output contains `<pre`, the copy button carries the exact raw in
  `data-url4`, collapsed by default; the full recipe text (minus added whitespace) is present.
- Fusion card: contains a collapsed "members" detail with a member prompt and a param, and the
  reducer's prompt (Model reducer) / "deterministic" (MajorityVote).

## Acceptance

- Recipe shows the full url4, indented by sections, inside a `<pre>`; copy copies exact raw.
- Fusion card exposes member/reducer prompts+params collapsed. Full gates green.

## Outcome

- **Actual files:** new `src/screamingface/_card_style.py` (stylesheet split out to keep
  `_card_display.py` under 450 lines); `_url4_format.py` rewritten to a quote/escape-aware
  string reflow (`_pretty_url4` + `_copy_quoted`); `_card_display.py` — imported stylesheet,
  `_long_value`/`_prompt_block` collapsers, `_fusion_detail_html`/`_member_detail`/
  `_reducer_detail`, verbose `benchmark_card_html` (`_grader_detail`, `_benchmark_source`,
  `_benchmark_routes`), Model/Rubric prompt collapse. New `tests/test_ome635_recipe_fullform.py`
  (12 tests).
- **Commit:** feat(screamingface): full-form url4 reflow + verbose fusion/benchmark cards
  (Refs: OME-635).
- **Gates:** `run_gates.py screamingface --skip-append-only` → ALL GATES GREEN. Full SDK suite
  742 prior + 12 new = 754 passing.
- **Deviations:**
  - **Append-only skip (owner-directed).** The user explicitly redirected the recipe design
    ("keep the url4 in full form instead of extracting params/prompt"), which supersedes two
    same-session, unmerged OME-630 tests. `test_ome630_url4_view.py` (structured-view
    assertions → full-form) and `test_ome630_recipe_wrap.py` (flex min-width → `<pre>` wrap)
    were updated to the new behavior; the gate ran with `--skip-append-only`. No merged/other
    test was touched.
  - Investigated the reported "gold band": `#f5c800` is JupyterLab's sole search-match color
    (inline `!important`); rendering the recipe in a `<pre>` also removes it from the
    `latexTypesetter`'s reach so `$member_*` is shown literally. Any residual gold is the Find
    highlight (user-side).
