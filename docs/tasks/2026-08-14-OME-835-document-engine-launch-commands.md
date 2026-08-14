---
id: OME-835
linear_url: https://linear.app/openmined/issue/OME-835/document-engine-launch-commands
status: In Review
type: Task
priority: P2
labels: [py-screamingface, agentic, autonomous, task]
created: 2026-08-14
---

# Document engine launch commands

Update public documentation and generated client notebooks to describe the packaged local
Engine flow:

- `pip install "screamingface[runtime,notebook]"`
- `screamingface prepare draco`
- `screamingface up`
- `screamingface status`
- `screamingface down`

Also document that a self-run Engine needs `TAVILY_API_KEY` when the provider routes in use do
not offer their own web-search tool.

Ledger: `docs/work/2026-08-14-OME-835-document-engine-launch-commands.md`
