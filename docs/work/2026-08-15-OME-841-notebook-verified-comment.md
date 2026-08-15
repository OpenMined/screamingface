---
ticket: OME-841
stack: screamingface
status: in_review
started: 2026-08-15
finished: 2026-08-15
---

# OME-841 — correct the notebook view's justification for removing the verified filter

## Intent

`OME-832` (merged as `#601`) removed the `verified` chip and the "verified only" filter from the
client's notebook leaderboard view. **The removal was right and stays exactly as merged.** The reason
recorded beside it is wrong, and wrong in a way that undercuts the removal.

`_ui/leaderboard_view.py:119-121` on `main`:

> `OME-832`: the "verified only" checkbox lived here. Removed, not relabelled —
> `verified_by_openmined` is **uniform** since `OME-820`, so **no row carries `data-verified=false`**
> and the control removed nothing. `OME-821` restores it.

Two things are wrong with that:

1. **It is false.** `OME-820` forbids a backfill, so rows created before that change keep `false`.
   The field is not uniform and rows *do* carry `data-verified=false`.
2. **It is load-bearing.** It is the stated justification for deleting a user-facing control. A
   reader who checks it finds it untrue and may conclude the deletion was unjustified.

The real reason is stronger, and was established during the `#588` review: the field **certifies
nothing whatever it holds**. A filter on it would split rows by whether they predate the default
change while presenting itself as a verification filter — measuring submission date and looking like
it measured trust. That is worse than filtering nothing.

Found while verifying `#588`'s review asks. The corrected reasoning already lives in `OME-820`,
`OME-821` and `apps/scoreboard`; only this merged copy still carries the old claim.

## Decisions locked (2026-08-15)

| # | Decision | Choice |
|---|---|---|
| D1 | Comments only | The removal was correct. Nothing about behaviour, API or tests changes. |
| D2 | A dedicated PR, not folded into `OME-821` | Owner decision. `OME-821` rewrites this area and would carry the fix for free, but it is Backlog and blocked on `OME-820`/`#588`, which is itself waiting on a re-review — so folding in leaves a false claim on `main` indefinitely and drags a doc fix into a ticket with open product questions. |
| D3 | Fix both occurrences | `:63-64` also says "became uniform and asserted nothing". The second half is right; only the word is wrong. Leaving one occurrence would just relocate the error. |
| D4 | State the real reason, do not merely delete the word | Deleting "uniform" would leave a removal with no recorded justification, which is how the next person re-adds the control. |

## Planned changes

- `packages/screamingface/src/screamingface/_ui/leaderboard_view.py` — three corrections (two
  comments and one docstring; the third was found by the mechanical check, not by reading).

Nothing else. No test changes: there is no assertion that could express "this comment is true", and
inventing one would be worse than the defect.

## Test plan

There is no behaviour to test — this is a comment fix, so a RED test is not available and pretending
otherwise would be dishonest. Verification is:

- the full `screamingface` gate suite stays green (it must be unaffected — that is the claim);
- `git diff` shows **comment lines only**, checked mechanically rather than by eye;
- the word `uniform` survives only where it is explicitly **denied**, and the replacement reasoning
  matches what `OME-820` and `apps/scoreboard` already say, so the copies cannot drift again.

## Acceptance

- No comment or docstring claims the field is uniform.
- Both state the real reason: the value certifies nothing, so a filter would split by submission date.
- The diff changes no executable statement, proven by token comparison.
- Full gates green.

## Outcome

Status: **DONE** (2026-08-15)

- **Actual files:** one — `packages/screamingface/src/screamingface/_ui/leaderboard_view.py`
  (+19/−9, all of it prose).
- **Gates:** `run_gates.py screamingface --base origin/main` — **ALL 8 GREEN**: append-only, ruff
  check, ruff format, pyright, pytest ≥95% cov, notebook determinism, `uv build`, distribution check.

### What the mechanical check caught that reading would not have

The plan's Step 3 compared **tokenized** source rather than the diff text. It paid for itself twice:

1. **Three occurrences, not two.** I had found `:63-64` and `:119-121` by reading. The third lived in
   the `_row_chip` docstring, where `grep`-by-eye over a diff would not have put it.
2. **One of them is not a comment.** A docstring is a STRING token, so the acceptance criterion this
   ledger originally carried — *"the diff touches comment lines only"* — was itself false. Restated as
   "no executable statement changes", which is the property that actually matters.

An earlier run of that check also produced a **false pass**: the shell invocation used an unexpanded
`$F`, so `git diff` matched no path, the grep found nothing, and the "comment lines only" branch
fired on an empty diff. Caught by adding a `git diff --stat` sanity line first. Worth keeping: a
verification step that cannot fail is not a verification step.

### Docstring change justified rather than assumed harmless

Docstrings are runtime objects, so changing one is not automatically inert. Checked: nothing in
`src/`, `tests/` or `scripts/` reads `__doc__`, there are no doctests, and `_row_chip` is private
(its only other mention is inside a test's own comment).

### Deviations

1. **Three corrections, not the two planned** — see above.
2. **`uniform` still appears twice in the file, and that is deliberate.** Both remaining uses
   explicitly *deny* it (`"the value is NOT uniform"`, and a note that the old wording was wrong).
   Deleting the word entirely would lose the correction's own record.

### Found, not fixed — out of scope

**The `screamingface` gate card omits a prerequisite.** `run_gates.py screamingface` runs
`uv run pyright` on a plain checkout and produces **9 errors** for unresolved `ipywidgets` /
`IPython.display` imports across `connection_view.py`, `connections.py`, `evaluation_view.py` and
`test_connection_panel.py` — none of them related to the change under test. CI avoids this by running
`uv sync --extra notebook` first (`screamingface-tests.yml:48`); the card in `.claude/sdlc.local.md`
does not say so, so a local run and CI disagree about whether the stack is green.

Same class of gap as the Node prerequisite `OME-798` documented. Not fixed here: it is a
`.claude/sdlc.local.md` edit, which would pull a second set of reviewers onto a PR whose entire
argument is "prose only, zero risk".
