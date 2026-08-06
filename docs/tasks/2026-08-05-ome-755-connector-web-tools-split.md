---
id: OME-755
linear_url: https://linear.app/openmined/issue/OME-755/split-the-tavily-web-tool-loop-out-of-url4-clouds-connectorpy
status: backlog
type: task
priority: P4
labels: [url4-cloud, autonomous, agentic, task]
created: 2026-08-05
closed:
---

# OME-755 — split the Tavily web-tool loop out of connector.py

`apps/url4-cloud/src/url4_cloud/runner/connector.py` is **648 lines**, over the 450-line guidance
in `sdlc-python`. It was 589 before `OME-745` added finish-reason capture.

The file does two unrelated jobs: building the aigateway-backed `Url4Node` world, and implementing
the Tavily web-tool loop. Moving the ~180-line tool-loop cluster (`_WEB_TOOLS`, `_execute_tool`,
`_dispatch_tool`, `_tool_args`, `_truncate_tool_result`, `_tavily_*`, `_build_tavily_client`) into
a `web_tools.py` sibling brings it to ~470.

Pure move, no behavior change — the existing suite is the regression proof. Kept out of `OME-745`
because folding a file split into a behavior-change PR makes review harder, the same reasoning
that kept the duplicated provider mapper out of `OME-746`.
