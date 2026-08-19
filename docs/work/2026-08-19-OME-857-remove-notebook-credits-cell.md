---
ticket: OME-857
stack: screamingface
status: done   # planned | in_progress | done | blocked
started: 2026-08-19
finished: 2026-08-19
---

# OME-857 — Remove the `openrouter_credits()` cell from the example notebooks

## Intent

The example notebooks each opened with an ad-hoc cell:

```python
from helpers import openrouter_credits

openrouter_credits()
```

`helpers.openrouter_credits()` reads a standalone `OPENROUTER_KEY` env var and prints that
key's OpenRouter balance — but that figure is **disconnected from the account actually
paying for the run in both provider modes**, so it misleads:

- **BYOK** — the connected key is stored encrypted + write-only in the AI Gateway
  credential store; the notebook cannot read it back, so the helper falls back to a
  *separate* `OPENROUTER_KEY` env var that generally is **not** the key the user configured
  their provider with.
- **Hosted / subsidized engine** — runs are powered by OpenMined's shared credentials; the
  user never sees or holds that key, so there is nothing meaningful to put in
  `OPENROUTER_KEY`.

Either way the printed credit belongs to the wrong (or no) account. Surfacing *real*
per-mode credit/balance is a product feature, tracked under `OME-893` (Surface available
provider credit/balance for BYOK and hosted). This unit removes the ad-hoc notebook cell;
the product surface is built under `OME-893`.

Folded into `OME-857` (Refresh the example notebooks: credits helper, …) per owner
decision — that ticket owns the credits-helper notebook cells.

## Planned changes

- `packages/screamingface/scripts/build_notebooks.py` — remove the three
  `new_code_cell("from helpers import openrouter_credits\n\nopenrouter_credits()")`
  blocks (00_quickstart, 01_client_tour, 08_healthbench_worst30).
- `packages/screamingface/examples/00_quickstart.ipynb` — drop the matching cell.
- `packages/screamingface/examples/01_client_tour.ipynb` — drop the matching cell.
- `packages/screamingface/examples/08_healthbench_worst30.ipynb` — drop the matching cell.
- `helpers.openrouter_credits` (in `examples/helpers.py`) is intentionally LEFT in place —
  it is the prototype the `OME-893` product surface will evolve from; keeping scope to the
  notebook cell removal the owner asked for.

## Test plan

- Executable contract = the existing deterministic-notebook gate
  `scripts/check_notebooks.py` (append-only; not modified). RED first: edit the generator
  only → gate reports "generated notebooks are stale". GREEN: drop the matching `.ipynb`
  cell → gate passes and the public-surface story markers still hold. No new unit test is
  warranted — this is generator/content removal, no `src/screamingface` logic changes.

## Acceptance

- `grep -r openrouter_credits packages/screamingface/examples/*.ipynb` returns nothing.
- `check_notebooks.py` green; full `run_gates.py screamingface` green.
- `OME-893` linked as `related` and referenced from the PR as the feature ticket.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** exactly as planned — `scripts/build_notebooks.py` (3 generator blocks
  removed) and the 3 notebooks (`00_quickstart`, `01_client_tour`,
  `08_healthbench_worst30`), one cell each. 48 pure deletions, 0 insertions, no reformatting
  (surgical `nbformat` read→filter→write kept outputs/ids/formatting intact).
- **Commits:** `chore(screamingface): remove the live openrouter_credits() cell from example
  notebooks` — sha in the PR / Linear close-comment.
- **Gates:** `run_gates.py screamingface` → ALL GATES GREEN (append-only ✓, ruff ✓,
  ruff format ✓, pyright ✓, pytest --cov≥95 ✓, check_notebooks ✓, uv build ✓,
  check_distribution ✓).
- **Deviations:** none. `helpers.openrouter_credits` intentionally retained as the prototype
  for the `OME-893` product surface (out of scope for this cell removal).
