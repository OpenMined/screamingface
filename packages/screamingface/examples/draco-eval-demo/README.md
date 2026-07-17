# DRACO / eval demo

`eval_demo_ux.ipynb` — the four-step eval pipeline (load → compose → run → grade) as
desired `sf` UX. Runs top-to-bottom with **no API keys**: `sf_stubs.py` patches the
target API onto today's SDK and simulates the LLM calls (grading uses the real
validated grader).

## Run it

```bash
uv sync
uv run jupyter lab eval_demo_ux.ipynb   # pick the .venv kernel, Run All
```

`[stub · …]` lines mark simulated steps; everything else is real SDK.

Note: `data/draco-demo-slice-5.jsonl` is private — do not post anywhere crawlable.
