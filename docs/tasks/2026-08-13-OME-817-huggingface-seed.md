---
id: OME-817
linear_url: https://linear.app/openmined/issue/OME-817/expand-huggingface-model-seed-with-21-live-verified-router-backends
status: in_progress
type: task
priority: 3
labels: [aigateway, agentic, autonomous]
created: 2026-08-13
closed:
---

# OME-817 — Expand HuggingFace model seed with live-verified router backends

Sub-issue of epic OME-815. Append 19 live-verified router entries (verified 2026-08-13 vs
`router.huggingface.co/v1/models`) to `huggingface_provider/settings.py` `_default_model_slugs()`,
5 → 24. Landed with OME-818 in one aigateway PR. Ledger:
`docs/work/2026-08-13-OME-817-huggingface-seed.md`.
