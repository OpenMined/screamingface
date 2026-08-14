# OME-832 — Implementation plan

Spec: `docs/spec/2026-08-14-OME-832-hide-verified-chip.md` · Ledger:
`docs/work/2026-08-14-OME-832-hide-verified-chip.md`

One file of production code, one stack (`screamingface`). RED before GREEN.

## Step 1 — RED

Append to `packages/screamingface/tests/test_leaderboards.py`:

1. `"verified only"` absent from the rendered board.
2. The `verified` chip absent for a candidate with `verified_by_openmined=True` — the strong form
   the existing `:787` assertion does not cover.
3. `data-verified` absent.
4. The `baseline` chip still present for a baseline row.
5. **The mislabel guard:** a candidate with no forkable url4 is not labelled `baseline`. This is
   the assertion that catches spec §3's trap, and it should fail *both* before the change (chip
   says `verified`) and against a naive deletion (chip says `baseline`).

## Step 2 — GREEN

`_ui/leaderboard_view.py`:

- delete `verify_action` and the `sf-lb__checkbox` label markup;
- delete the `data-verified` attribute from `_board_row`;
- `_row_chip` becomes a single `kind == "single"` test returning the `baseline` chip.

`_ui/leaderboard_style.py`: note the now-unused `.sf-lb__checkbox*` rules, kept for `OME-821`.

## Step 3 — the prior assertion

`:354` asserts `"verified only" in html` and must invert. **Escalate first** (sdlc rule 5), then
change one line and note why in place.

## Step 4 — gates

`uv run .claude/scripts/run_gates.py screamingface --base origin/main`. Note this stack's list is
longer than scoreboard's: ruff, pyright, **pytest with a 95% coverage floor**, the notebook check,
`uv build`, and the distribution check. Removing code can move coverage in either direction, so
read the number rather than assuming.

## Risks

- **The mislabel** (spec §3) is the whole risk. A deletion that passes tests is not evidence; the
  guard in step 1.5 is what makes it evidence.
- The notebook check and `uv build` gates are slower and unrelated to this change; if one fails it
  is probably pre-existing, so verify against `origin/main` before treating it as mine.
