# OME-841 — Implementation plan

Spec: `docs/spec/2026-08-15-OME-841-notebook-verified-comment.md` · Ledger:
`docs/work/2026-08-15-OME-841-notebook-verified-comment.md`

Two comments in one file.

## Step 1 — `_ui/leaderboard_view.py:119-121`

The load-bearing one. Replace the uniformity claim with the certifies-nothing reason, keeping the
"removed, not relabelled" framing and the `OME-821` pointer.

## Step 2 — `_ui/leaderboard_view.py:63-64`

Same word, smaller stakes: "became uniform and asserted nothing". Keep "asserted nothing", drop
"uniform".

## Step 2b — the third occurrence, in the `_row_chip` docstring

Found by Step 3, not by reading. Same correction.

## Step 3 — prove the diff is inert

Not by reading it. Tokenize both revisions, drop COMMENT and NL tokens, compare the rest. A
"comment-only" change that quietly moved a line of code is exactly the failure this catches — and it
is why the check must use the tokenizer rather than a regex, since this file is full of HTML string
literals containing `#`.

It also distinguishes a comment from a docstring, which a `grep '^#'` cannot: docstrings survive
tokenization as STRING tokens, so a docstring edit shows up here as a real difference and has to be
justified rather than assumed harmless.

## Step 4 — gates, ledger, commit, PR

`run_gates.py screamingface --base origin/main`. Note the suite is heavier than scoreboard's: it
includes the notebook determinism check, `uv build`, and a distribution check.

## Risks

- **Low blast radius, wrong reviewers.** `.github/CODEOWNERS` assigns `/packages/screamingface/` to
  `@IonesioJunior @keelancj`, not the scoreboard owner. The PR body has to carry enough context that a
  reader who was not in the `#588` review can judge it without reading `#588`.
- **Wording drift.** Three places now describe this flag. The replacement text should echo `OME-820`'s
  phrasing rather than invent a fourth variant.
