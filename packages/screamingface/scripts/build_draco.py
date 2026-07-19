"""Build the ScreamingFace-native DRACO benchmark notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def notebook() -> nbformat.NotebookNode:
    cells = [
        nbformat.v4.new_markdown_cell(
            """# DRACO with the ScreamingFace SDK

Build an open-ended research fusion, execute every model through URL4, and compare its weighted
DRACO rubric score with the same panel members scored individually.

**Path: benchmark adapter.** This is the long-form example: experiment-owned prompts, a
model-backed reducer, benchmark-owned rubric judging, and the production URL4 requirements are
shown separately.

The saved run uses two bundled DRACO-shaped cases and an in-process URL4 node with deterministic
model routes. It validates the complete ScreamingFace request and response contract without setup,
credentials, or a provider-quality claim.

The final section identifies the remaining production boundary: the configured URL4 model routes
must execute the capabilities and parameters that ScreamingFace emits."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Import and configure"),
        nbformat.v4.new_code_cell(
            "import screamingface as sf\n\n"
            "# Optional: send every model and judge call to an HTTP URL4 engine.\n"
            '# sf.config("http://127.0.0.1:4404")  # first run ./scripts/dev-url4.sh\n'
            '# sf.config("https://url4.example")'
        ),
        nbformat.v4.new_markdown_cell(
            """## 2 · Define the research behavior

These prompts belong to the experiment, not the DRACO dataset adapter. `$question` is resolved for
each case. The reducer additionally receives the labeled `$member_answers` produced by URL4."""
        ),
        nbformat.v4.new_code_cell(
            'DRACO_PANEL_PROMPT = """\n'
            "You are answering a research-quality prompt. Provide a thorough, "
            "well-reasoned answer\n"
            "in prose. Address every aspect, preserve specific facts and sources, and use clear\n"
            "structure.\n\n"
            "Research prompt:\n"
            '$question\n""".strip()\n\n'
            'DRACO_REDUCER_PROMPT = """\n'
            "Produce one comprehensive answer to the research prompt by combining the strongest\n"
            "facts, arguments, and citations from every labeled panel answer. Resolve "
            "disagreements\n"
            "in favor of the more specific and better-supported claim. Return only the "
            "unified prose\n"
            "answer.\n\n"
            "Research prompt:\n"
            "$question\n\n"
            "Panel answers:\n"
            '$member_answers\n""".strip()'
        ),
        nbformat.v4.new_markdown_cell("## 3 · Compose the fusion"),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "draco-frontier-trio",\n'
            "    models=[\n"
            '        "codex/gpt-5.5",\n'
            '        "gemini-cli/gemini-2.5-pro",\n'
            '        "anthropic/claude-sonnet-4-6",\n'
            "    ],\n"
            "    prompt=DRACO_PANEL_PROMPT,\n"
            '    tools=["web_search"],\n'
            "    reducer=sf.ModelReducer(\n"
            '        model="codex/gpt-5.5",\n'
            "        prompt=DRACO_REDUCER_PROMPT,\n"
            '        params={"temperature": 0.0, "max_tokens": 8192},\n'
            "    ),\n"
            ")\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell(
            """The shareable fusion URL4 contains the unresolved panel and reducer graph. It does
not contain the DRACO dataset or rubric, and displaying it executes nothing."""
        ),
        nbformat.v4.new_code_cell("fusion.url4"),
        nbformat.v4.new_markdown_cell(
            """## 4 · Evaluate

For each case, ScreamingFace sends one fusion expression to `/v1`. After receiving the panel and
synthesized answers, the DRACO grader sends one additional URL4 model request for every
answer × rubric criterion × judge pass. No SDK code calls AI Gateway or a provider directly."""
        ),
        nbformat.v4.new_code_cell('run = fusion.evaluate("draco", first=2, seed=0)\nrun'),
        nbformat.v4.new_markdown_cell("## 5 · Read the comparison"),
        nbformat.v4.new_code_cell(
            "{\n"
            '    "primary_metric": run.primary_metric,\n'
            '    "fusion_score": run.score,\n'
            '    "best_member": run.baseline,\n'
            '    "gain": run.gain,\n'
            '    "rubric_metrics": dict(run.metrics),\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """## 6 · Judge request and response

DRACO grading is engine work too. For every answer × criterion × judge pass, ScreamingFace sends a
single-model URL4 expression shaped like this after decoding the HTTP `q` parameter:

```url4
/gemini/3.1-pro-preview
  ?temperature=0.2
  &reasoning=low
  &max_tokens=4096
  &q=(<criterion type, criterion, original query, and response>)
  !'<paper-aligned judge system prompt>'
```

Here URL4 context (`q=(...)`) becomes the judge's user content and URL4 intent (`!...`) becomes its
system instruction. The model route returns JSON text:

```json
{
  "explanation": "The response satisfies the criterion because …",
  "criterion_status": "MET"
}
```

`UNMET` is the other valid status. The grader parses each independent verdict, applies positive and
negative rubric weights, and records verdict coverage. The default deterministic route produces
stable verdicts so this machinery is runnable; a production route must preserve the same request
semantics and return contract."""
        ),
        nbformat.v4.new_markdown_cell(
            """`normalized_score` is DRACO's weighted score: positive criteria add their weights,
MET negative criteria subtract their weights, and the result is divided by total positive weight
and clamped to 0–100. `gain` compares the synthesis with the best panel member on the same cases
and judge protocol.

## 7 · What the production URL4 engine must handle

The bundled in-process URL4 node validates the request and response shapes deterministically.
Replacing it with a production HTTP URL4 engine requires the engine to:

- accept each complete expression at `GET /v1?q=<url4 expression>` and execute its dependency graph;
- dispatch every `/provider/model` node to the corresponding production model route;
- translate `tools=web_search` on panel nodes into each provider's native search capability;
- preserve judge-request URL4 intent as the system message and context as the user message;
- forward `temperature=0.2`, `reasoning=low`, and `max_tokens=4096` for judge calls;
- run repeated judge expressions as independent samples rather than collapsing or caching them;
- keep research tools disabled for judge calls, which only grade supplied responses;
- contact AI Gateway internally—ScreamingFace never contacts it or a provider directly;
- return panel/fusion outputs and raw judge JSON in the response shapes demonstrated above; and
- eventually return usage, cost, failure, retry, search, and citation telemetry.

Until those production routes exist, the saved result demonstrates the complete SDK ↔ URL4
expression and response contract but makes no claim about provider quality or production DRACO
scores."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"draco-{index:02d}"
    return nbformat.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = args.output or Path(__file__).parents[1] / "examples" / "draco.ipynb"
    document = notebook()
    if args.execute:
        document = NotebookClient(
            document,
            timeout=120,
            kernel_name="python3",
            resources={"metadata": {"path": str(target.parent)}},
        ).execute()
        for cell in document.cells:
            cell.metadata.pop("execution", None)
            if "outputs" in cell:
                cell.outputs = [
                    output
                    for output in cell.outputs
                    if "application/vnd.jupyter.widget-view+json" not in output.get("data", {})
                ]
        document.metadata.pop("widgets", None)
        document.metadata["language_info"] = {"name": "python", "version": "3.12"}
    nbformat.write(document, target)


if __name__ == "__main__":
    main()
