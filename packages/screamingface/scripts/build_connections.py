"""Build the Phase 6C provider-connections notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free provider connection guide."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace · service connections

Connect the model providers and tool services advertised by your configured ScreamingFace engine,
then see how execution preflight prevents repeated authentication failures before any model spend.

Start the local stack first:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

For model providers the boundary is **SDK → screamingface-engine → AI Gateway → provider**.
Tavily is engine-owned: **SDK → screamingface-engine → Tavily**. The SDK never sends credentials
directly to AI Gateway, a model provider, or Tavily."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Open the provider panel"),
        nbformat.v4.new_code_cell("import screamingface as sf\n\npanel = sf.connect()\npanel"),
        nbformat.v4.new_markdown_cell(
            """The panel reads fresh status from the configured engine and shows where credentials
will be stored. API-key inputs are masked and cleared after every attempt. OAuth displays an
authorization link only after you press its button; it **does not open a browser automatically**.

For model providers, connected means the engine's AI Gateway holds a credential. For Tavily, it
means Tavily validated the key and this local engine process currently holds it; restart requires
reconnection. Neither status claims that every advertised model or future tool action will
succeed."""
        ),
        nbformat.v4.new_markdown_cell("## 2 · Read status from Python"),
        nbformat.v4.new_code_cell("connections = sf.connections.list()\nconnections"),
        nbformat.v4.new_markdown_cell(
            """Scripts use explicit targeted calls and never receive a hidden terminal prompt.
OAuth returns a bounded `OAuthFlow`; API keys travel once in the private request body. These
examples are comments so running this guide never starts or replaces a connection unexpectedly."""
        ),
        nbformat.v4.new_code_cell(
            "# OAuth — inspect flow.authorize_url, then call flow.wait() after authorizing:\n"
            '# flow = sf.connect("codex", method="oauth")\n\n'
            "# API key — read it from your process environment, never a shared notebook literal:\n"
            "# import os\n"
            '# gemini = sf.connect("gemini", api_key=os.environ["GEMINI_API_KEY"])\n\n'
            "# Tavily is validated directly and retained only by this local engine process:\n"
            '# tavily = sf.connect("tavily", api_key=os.environ["TAVILY_API_KEY"])\n'
            '# sf.connections.get("tavily")\n\n'
            "# Disconnect is idempotent:\n"
            '# sf.disconnect("gemini")'
        ),
        nbformat.v4.new_markdown_cell("## 3 · Execution checks requirements once"),
        nbformat.v4.new_code_cell(
            "def connection_actions(error: sf.ConnectionRequiredError) -> dict[str, object]:\n"
            '    """Turn one preflight error into script-friendly details."""\n\n'
            "    return {\n"
            '        "providers": error.providers,\n'
            '        "models": error.models,\n'
            '        "roles": error.roles,\n'
            '        "message": str(error),\n'
            "    }"
        ),
        nbformat.v4.new_markdown_cell(
            """`benchmark.evaluate(recipe, ...)` checks the Recipe's member, reducer, grader, and
tool-service requirements once before sending the complete run URL4. Missing credentials raise one
actionable `ConnectionRequiredError`, not one failure per case. This guide performs **no paid
model call**.

Dataset access remains separate from inference-provider connections. The development engine reads
`HF_TOKEN` from its environment when a registered benchmark must load a gated Hugging Face source;
`sf.connect()` does not manage that dataset token. Tavily credentials are engine-owned and never
pass through AI Gateway."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"connections-{index:02d}"
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
    target = args.output or Path(__file__).parents[1] / "examples" / "06_connections.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
