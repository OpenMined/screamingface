"""Optional provider-sensitive cells for the generated IFEval notebook."""

from __future__ import annotations

import nbformat
from nbformat import NotebookNode


def kimi_appendix() -> tuple[NotebookNode, ...]:
    """Preserve Khoa's Kimi K3 research grid without putting it on Run All's paid path."""

    # WHY: keeping these cells separate makes the stable first-run contract visually and
    # structurally distinct from a provider-sensitive research reproduction.
    return (
        nbformat.v4.new_markdown_cell(
            """## Optional appendix — Khoa's Kimi K3 experiment

This preserves the original research lineup without making it the environment-health
check. It is disabled so **Run All does not spend on it or fail because of an upstream K3
completion**.

Observed failure meanings:

- `case … carried no valid IFEval check record` means a Candidate/provider failed to return
  a scorable answer. The Engine refuses to turn that into a plausible zero score.
- `aigateway returned neither answer content nor tool calls` commonly means a reasoning
  model exhausted its completion budget before emitting final answer text.
- An HTTP 200 from the upstream call does not prove answer content was present.

Set `RUN_KIMI_RESEARCH = True` only after the smoke grid succeeds. Start with one Case;
increase `KIMI_RESEARCH_LIMIT` deliberately. Kimi K3 may need a larger completion budget,
but a higher ceiling cannot repair an upstream provider error."""
        ),
        nbformat.v4.new_code_cell(
            """RUN_KIMI_RESEARCH = False
KIMI_RESEARCH_LIMIT = 1

kimi = sf.Model("openrouter/moonshotai/kimi-k3", params={"max_tokens": 4096})
haiku = sf.Model("openrouter/anthropic/claude-haiku-4.5")
kimi_fusion = sf.Fusion(
    [kimi, haiku],
    name="kimi-haiku",
    synthesizer="openrouter/moonshotai/kimi-k3",
    params={"max_tokens": 4096},
)

\"Enabled\" if RUN_KIMI_RESEARCH else \"Skipped — set RUN_KIMI_RESEARCH = True to opt in\""""
        ),
        nbformat.v4.new_code_cell(
            """if RUN_KIMI_RESEARCH:
    kimi_canonical = sf.evaluate(
        kimi,
        benchmark="ifeval",
        limit=KIMI_RESEARCH_LIMIT,
        progress=True,
    )
    kimi_blended = sf.evaluate(
        kimi_fusion,
        benchmark="ifeval",
        limit=KIMI_RESEARCH_LIMIT,
        progress=True,
    )
    kimi_self_corrective = sf.evaluate(
        kimi,
        benchmark="ifeval/self-corrective",
        limit=KIMI_RESEARCH_LIMIT,
        progress=True,
    )
    kimi_verifying_ensemble = sf.evaluate(
        kimi_fusion,
        benchmark="ifeval/verifying-ensemble",
        limit=KIMI_RESEARCH_LIMIT,
        progress=True,
    )
    kimi_results = {
        "① ifeval · kimi": kimi_canonical,
        "② ifeval · kimi-haiku": kimi_blended,
        "③ self-corrective · kimi": kimi_self_corrective,
        "④ verifying-ensemble · kimi-haiku": kimi_verifying_ensemble,
    }
else:
    kimi_results = {}

{
    name: {
        "score": report.candidates[0].score,
        "output_tokens": report.usage.output_tokens,
    }
    for name, report in kimi_results.items()
}"""
        ),
    )
