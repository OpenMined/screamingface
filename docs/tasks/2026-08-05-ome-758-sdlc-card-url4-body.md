---
id: OME-758
linear_url: https://linear.app/openmined/issue/OME-758/add-sdlc-card-body-sections-for-the-url4-and-url4-cloud-stacks
status: backlog
type: task
priority: P3
labels: [repo, autonomous, agentic, task]
created: 2026-08-05
closed:
---

# OME-758 — sdlc card body sections for url4 and url4-cloud

`.claude/sdlc.local.md` declares five stacks in frontmatter but its body covers only `aigateway`,
`aigateway-ui` and `scoreboard`. Nothing for **`url4`** or **`url4-cloud`**, so the `sdlc-python`
skill's required "read the card BODY for the active stack" step binds nothing on either.

Hit during `OME-744` and `OME-745`. Gate *lists* are complete for both — this is body prose only.

Conventions worth capturing, learned the hard way: `packages/url4/pyproject.toml` omits
`src/url4/streaming/*` from coverage on purpose (its tests live with url4-cloud, gated there via
`--cov=url4.streaming`) — a fact that moved a file between two issues mid-flight; url4's coverage
floor is 95% against the others' 80%; `url4.observe` is a stdlib-only leaf; and in url4-cloud only
`runner/executor.py` and `runner/connector.py` may import the engine.

Companion to `OME-743`.
