---
id: OME-635
linear_url: https://linear.app/openmined/issue/OME-635
status: duplicate  # merged into OME-626 (2026-07-27)
type: feature
priority: 3
labels: [py-screamingface, agentic, autonomous]
created: 2026-07-27
closed:
---

Card display refinements (all `_card_display.py` / `_url4_format.py`, display-only):

1. url4 recipe kept in full form, reflowed by `(){}`/comma sections inside a `<pre>`
   (MathJax-safe); collapsed `<details>` + copy of the exact raw.
2. Fusion card: collapsed "members & reducer" section with each member's prompt + params and
   the reducer's prompt + params.
3. Verbose Benchmark and Rubric grader cards — surface all interesting fields; long fields
   (prompts) rendered as collapsed `<details>`.

- Governing spec: `docs/spec/2026-07-27-OME-626-sdk-display-contract.md`
- Plan: `docs/plan/2026-07-27-OME-635-recipe-fullform-and-fusion-detail.md`
- Ledger: `docs/work/2026-07-27-OME-635-recipe-fullform-and-fusion-detail.md`
