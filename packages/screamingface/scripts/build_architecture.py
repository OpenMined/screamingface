"""Build the Phase 5C ScreamingFace architecture notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat


def notebook() -> nbformat.NotebookNode:
    """Return the deterministic, output-free architecture walkthrough."""

    cells = [
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace · configuration and architecture

See exactly where ScreamingFace stops and its URL4 engine begins: configure one engine, inspect its
registry, distinguish a reusable Fusion recipe from an executed request, and send one real
provider-free URL4 transaction.

## Before you run it

Start the local development stack from the repository root:

```bash
cd packages/screamingface/apps/screamingface-engine
./dev.sh
```

No provider credentials are needed. The only executed expression calls the deterministic
majority-vote route with literal answers. This notebook does not load a benchmark, contact a model,
or use Hugging Face access."""
        ),
        nbformat.v4.new_markdown_cell("## 1 · Configure one engine"),
        nbformat.v4.new_code_cell(
            "import json\n"
            "import os\n\n"
            "import httpx\n"
            "from url4 import Expression, RelExpr, render, src, struct\n\n"
            "import screamingface as sf\n\n"
            'ENGINE_URL = os.environ.get("SCREAMINGFACE_ENGINE_URL", "http://127.0.0.1:4404")\n'
            "sf.config(engine=ENGINE_URL)\n\n"
            'httpx.get(f"{ENGINE_URL}/healthz", timeout=5).text'
        ),
        nbformat.v4.new_markdown_cell(
            """`sf.config(...)` stores and validates one HTTP(S) origin. It performs no network
request by itself. Localhost is temporarily the SDK default; the same API selects a future hosted
engine:

```python
sf.config(engine="https://screamingface.example")
```

The explicit health check above is this notebook's first request."""
        ),
        nbformat.v4.new_markdown_cell(
            """## 2 · The ownership boundary

```text
Researcher process
├─ ScreamingFace SDK
│  ├─ loads benchmark sources and keeps references sealed
│  ├─ compiles Fusion definitions into URL4
│  ├─ validates returned run evidence
│  ├─ performs deterministic graders
│  └─ aggregates paired comparisons
│
└─ HTTP GET
   └─ screamingface-engine · persistent Url4Node
      ├─ model routes ── AI Gateway ── model providers
      ├─ web_search ── private SearXNG service
      └─ deterministic reducer routes
```

The SDK never calls providers or AI Gateway directly. The generic URL4 engine evaluates the graph;
the ScreamingFace engine profile registers the model, tool, and reducer capabilities needed by the
SDK."""
        ),
        nbformat.v4.new_markdown_cell("## 3 · Inspect the engine registry"),
        nbformat.v4.new_code_cell(
            'registry_response = httpx.get(f"{ENGINE_URL}/.well-known/screamingface", timeout=5)\n'
            "registry_response.raise_for_status()\n\n"
            "{\n"
            '    "content_type": registry_response.headers["content-type"],\n'
            '    "raw_plaintext": registry_response.text,\n'
            "}"
        ),
        nbformat.v4.new_code_cell(
            "registry = json.loads(registry_response.text)\n\n"
            "{\n"
            '    "schema": registry["schema"],\n'
            '    "models": sf.models.list(),\n'
            '    "reducers": registry["reducers"],\n'
            '    "limits": registry["limits"],\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """The registry is JSON serialized inside a plaintext HTTP body. `sf.models.list()`
fetches and validates the complete `screamingface.registry.v1` document before returning model IDs.

The registry advertises executable routes and transport limits—not provider authentication and not
benchmark data. Benchmarks are installed SDK definitions because their sources and sealed
references belong in the researcher's process."""
        ),
        nbformat.v4.new_markdown_cell("## 4 · A Fusion recipe is URL4, but not yet a request"),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "architecture-example",\n'
            '    models=["codex/gpt-5.5", "gemini/2.5"],\n'
            '    prompt="Answer the question.",\n'
            "    reducer=sf.reducers.MajorityVote(),\n"
            ")\n\n"
            "fusion.url4"
        ),
        nbformat.v4.new_markdown_cell(
            """`fusion.url4` is a canonical parameterized recipe. Its `$question` binding is still
unresolved, so displaying it performs no model call. When a benchmark case is evaluated, the SDK
binds the concrete question and sends the complete encoded expression to the configured engine.

The recipe is shareable Fusion identity. The HTTP request is one execution of that recipe for one
concrete input."""
        ),
        nbformat.v4.new_markdown_cell("## 5 · Build one provider-free URL4 transaction"),
        nbformat.v4.new_code_cell(
            "expression = render(\n"
            "    Expression(\n"
            "        sources=(\n"
            "            src(\n"
            '                struct({"member_1": "A", "member_2": "B", "member_3": "A"}),\n'
            '                name="member_answers",\n'
            "            ),\n"
            "            src(\n"
            "                RelExpr(\n"
            '                    path="/reducers/majority-vote",\n'
            '                    context="$member_answers",\n'
            "                ),\n"
            '                name="fusion_answer",\n'
            "            ),\n"
            "            struct(\n"
            "                {\n"
            '                    "schema": "screamingface.fusion-result.v1",\n'
            '                    "answer": "$fusion_answer",\n'
            "                }\n"
            "            ),\n"
            "        )\n"
            "    )\n"
            ")\n\n"
            "expression"
        ),
        nbformat.v4.new_markdown_cell(
            """This expression is built from URL4's public Python builders and canonically rendered;
it is not copied from a private ScreamingFace compiler. Its graph binds three literal answers,
passes their resolved object to the registered majority-vote route, and returns one small
structured result.

No model route appears in the graph, so executing it cannot reach AI Gateway, a provider, or
SearXNG."""
        ),
        nbformat.v4.new_markdown_cell("## 6 · Send the encoded GET and inspect the plaintext"),
        nbformat.v4.new_code_cell(
            'request = httpx.Request("GET", f"{ENGINE_URL}/v1", params={"q": expression})\n\n'
            "with httpx.Client(timeout=5) as client:\n"
            "    response = client.send(request)\n\n"
            "response.raise_for_status()\n"
            "parsed_response = json.loads(response.text)\n"
            "assert parsed_response == {\n"
            '    "schema": "screamingface.fusion-result.v1",\n'
            '    "answer": "A",\n'
            "}\n\n"
            "{\n"
            '    "url4_expression": expression,\n'
            '    "encoded_request_url": str(request.url),\n'
            '    "raw_plaintext": response.text,\n'
            '    "parsed_result": parsed_response,\n'
            "}"
        ),
        nbformat.v4.new_markdown_cell(
            """The complete transactional shape is:

```text
GET /v1?q=<encoded URL4 expression>
```

URL encoding changes only the HTTP representation; the `q` value remains the same URL4 expression.
The engine resolves the graph and returns plaintext. ScreamingFace parses and validates structured
plaintext when it runs a Fusion; this cell performs those two steps visibly for teaching."""
        ),
        nbformat.v4.new_markdown_cell(
            """## 7 · Responsibility map

| Concern | Owner |
|---|---|
| Benchmark source and references | Researcher's SDK process |
| URL4 recipe compilation | ScreamingFace SDK |
| URL4 graph execution | `screamingface-engine` / URL4 |
| Provider calls | Engine through AI Gateway |
| Web research | Engine through SearXNG |
| Exact grading and aggregation | Researcher's SDK process |

Rubric grading is the one model-backed grading mode: the SDK schedules each judge task through the
same configured URL4 engine. The SDK still never opens a direct provider or Gateway connection.

## Recap

- `sf.config(...)` selects one URL4 engine.
- The engine registry describes what that deployment can execute.
- `fusion.url4` is a reusable parameterized recipe.
- one concrete execution is an encoded `GET /v1?q=...` transaction.
- successful bodies are plaintext that the SDK parses and validates.
- benchmark data and deterministic scoring remain in the researcher's process.

Continue to the quickstart to evaluate GPQA, or the DRACO walkthrough for web-research members,
model synthesis, and rubric judging."""
        ),
    ]
    for index, cell in enumerate(cells, start=1):
        cell["id"] = f"architecture-{index:02d}"
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
    target = args.output or Path(__file__).parents[1] / "examples" / "01_architecture.ipynb"
    nbformat.write(notebook(), target)


if __name__ == "__main__":
    main()
