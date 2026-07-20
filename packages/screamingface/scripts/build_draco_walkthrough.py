"""Build the concise DRACO Preview SDK notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free DRACO Preview quickstart."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace · DRACO Preview

Run one real DRACO research question through the complete ScreamingFace workflow: connect,
compose, evaluate, and compare.

This notebook uses `draco-preview@1`, not canonical `draco@1`. Preview keeps the pinned real
100-question source, one real positive rubric criterion per question, the official per-criterion
judge prompt, and the same grading and aggregation implementation. One case makes six model calls:
two research calls, one synthesis call, and three judge calls.

It deliberately differs from canonical DRACO:

| | DRACO Preview | Canonical DRACO |
|---|---|---|
| research | two independently prompted Claude calls | seven-model, nine-Fusion lineup |
| search | engine-hosted SearXNG | earlier reproduction used OpenRouter |
| synthesis | Codex GPT-5.5 | pinned pipeline-specific synthesizers |
| judging | Gemini 2.5 Flash, one criterion, one pass | Gemini 3.1 Pro, full rubric, three passes |
| claim | architecture validation | score-comparable reproduction |

The two Claude calls are independent: one builds an evidence-led answer and the other searches for
omissions and counterevidence. Both receive `web_search`. Codex is the model reducer because its
current route is tool-free; it combines the resolved research answers without performing another
search. Gemini 2.5 Flash is tool-free and used only as the judge. Gemini 3 research is not
advertised because its function-calling continuation requires an encrypted `thoughtSignature`
that the current AI Gateway normalization does not preserve.

The earlier reproduction routed research and its Gemini 3.1 Pro judge through OpenRouter. AI
Gateway OpenRouter support is tracked in OME-428. Until that lands, Preview must not be presented
as a DRACO score or compared with the paper. A typical canonical case would make about 354 judge
calls for this three-answer target shape; Preview makes three.

## Before you run it

Start the local stack:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

It provides the ScreamingFace engine at `http://127.0.0.1:4404`, AI Gateway behind it, and private
SearXNG search. Only the engine contacts AI Gateway. Each case is sent as one
`GET /v1?q=<URL-encoded-expression>` URL4 request; the engine returns plaintext that the SDK parses
into immutable values.

DRACO is downloaded by this Python process through your Hugging Face session. Run
`huggingface-cli login` if the dataset requires it; that token is never sent to the engine. Connect
Claude, Codex, and Gemini below before evaluating. The live progress panel reports actual cases and
judge responses while the synchronous call runs."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Connect"),
        nbformat.v4.new_code_cell("import screamingface as sf\n\nsf.connect()"),
        nbformat.v4.new_markdown_cell("## 2 · Compose"),
        nbformat.v4.new_code_cell(
            'EVIDENCE_PROMPT = """Research the question before answering. Build an evidence-led\n'
            "account with specific facts and sources, cover every part of the prompt, and return\n"
            'clear, structured prose."""\n\n'
            'CHALLENGE_PROMPT = """Research the question independently. Look for omissions,\n'
            "counterevidence, and weak assumptions before producing a complete answer with\n"
            'specific facts and sources."""\n\n'
            'SYNTHESIS_PROMPT = """Produce one comprehensive answer by combining the strongest\n'
            "facts, arguments, and citations from every labeled member answer. Resolve\n"
            "disagreements in favor of the more specific and better-supported claim. Return only\n"
            'the unified prose answer."""\n\n'
            "fusion = sf.Fusion(\n"
            '    "draco-research-duo",\n'
            "    models=[\n"
            '        {"model": "claude/sonnet-4.6", "prompt": EVIDENCE_PROMPT},\n'
            '        {"model": "claude/sonnet-4.6", "prompt": CHALLENGE_PROMPT},\n'
            "    ],\n"
            "    reducer=sf.reducers.Model(\n"
            '        model="codex/gpt-5.5",\n'
            "        prompt=SYNTHESIS_PROMPT,\n"
            "    ),\n"
            ")\n\n"
            "fusion"
        ),
        nbformat.v4.new_markdown_cell("## 3 · Evaluate"),
        nbformat.v4.new_code_cell(
            'report = fusion.evaluate("draco-preview@1", first=1)\n\n'
            "# Equivalent staged API:\n"
            '# benchmark = sf.benchmarks.load("draco-preview@1")\n'
            "# run = fusion.run(benchmark, first=1)\n"
            "# grades = run.grade()\n"
            "# report = grades.aggregate()"
        ),
        nbformat.v4.new_markdown_cell("## 4 · Compare"),
        nbformat.v4.new_code_cell("report"),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"draco-preview-{index:02d}"
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = args.output or Path(__file__).parents[1] / "examples" / "05_draco.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
