"""Build the ScreamingFace architecture notebook."""

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
            "from url4 import Expression, RelExpr, Text, render, src, struct\n\n"
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
│  ├─ loads and validates engine benchmark manifests
│  ├─ compiles complete benchmark-run URL4
│  ├─ reads provider status and sends connection actions
│  └─ parses and validates the returned report
│
└─ screamingface-engine · persistent Url4Node
   ├─ plaintext URL4 data plane · GET /v1?q=...
   │  ├─ benchmark case data routes
   │  ├─ model routes ── AI Gateway ── model providers
   │  ├─ verified HF tool routes ── Tavily search/extract
   │  ├─ reducer and grader routes
   │  └─ aggregator routes
   └─ JSON connection control plane · /v1/connections/...
      ├─ AI Gateway model-provider credential profiles
      └─ process-local Tavily connection
```

Both planes end at the configured ScreamingFace engine. The SDK never calls providers or AI
Gateway directly. The generic URL4 engine evaluates the graph; the ScreamingFace engine profile
registers the model, tool, reducer, and connection capabilities needed by the SDK."""
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

The registry advertises executable model and benchmark routes, response schemas, transport limits,
and provider ownership/auth methods.
Fresh connection status comes from the engine's protected connection API rather than this public
capability document. Loading a benchmark validates its manifest but does not fetch its cases."""
        ),
        nbformat.v4.new_markdown_cell("## 4 · A Fusion recipe is URL4, but not yet a request"),
        nbformat.v4.new_code_cell(
            "fusion = sf.Fusion(\n"
            '    "architecture-example",\n'
            '    members=["codex/gpt-5.5", "gemini/2.5-flash"],\n'
            "    reducer=sf.reducers.MajorityVote(),\n"
            ")\n\n"
            "fusion.url4"
        ),
        nbformat.v4.new_markdown_cell(
            """`fusion.url4` is a canonical parameterized answer recipe. Its `$question` binding is
still unresolved, so displaying it performs no model call. `benchmark.evaluate(fusion, first=...)`
wraps it with the benchmark case route, stable slice, grader, and aggregator.

The returned `report.url4` is the complete shareable run: another compatible engine can read the
same expression and reproduce the selected slice."""
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
            '                    path="/reducers/majority-vote/1",\n'
            '                    intent=Text("$member_answers"),\n'
            "                ),\n"
            '                name="recipe_answer",\n'
            "            ),\n"
            "            src(\n"
            "                struct(\n"
            "                    {\n"
            '                        "schema": "screamingface.recipe-result.v1",\n'
            '                        "answer": "$recipe_answer",\n'
            "                    }\n"
            "                ),\n"
            '                name="recipe_result",\n'
            "            ),\n"
            "        ),\n"
            '        intent=Text("$recipe_result"),\n'
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
Tavily."""
        ),
        nbformat.v4.new_markdown_cell("## 6 · Send the encoded GET and inspect the plaintext"),
        nbformat.v4.new_code_cell(
            'request = httpx.Request("GET", f"{ENGINE_URL}/v1", params={"q": expression})\n\n'
            "with httpx.Client(timeout=5) as client:\n"
            "    response = client.send(request)\n\n"
            "response.raise_for_status()\n"
            "parsed_response = json.loads(response.text)\n"
            "assert parsed_response == {\n"
            '    "schema": "screamingface.recipe-result.v1",\n'
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
| Benchmark manifest | ScreamingFace SDK from engine registry |
| Benchmark source and references | ScreamingFace engine data route |
| Complete run URL4 compilation | ScreamingFace SDK |
| URL4 graph execution | `screamingface-engine` / URL4 |
| Provider calls | Engine through AI Gateway |
| Provider credential control | SDK through engine to AI Gateway |
| Web research | Engine directly through Tavily on verified HF routes |
| Grading and aggregation | ScreamingFace engine routes inside URL4 |

Model-backed graders call their judge route inside the same URL4 graph. The SDK never opens a
direct provider or Gateway connection.

## Recap

- `sf.config(...)` selects one URL4 engine.
- The engine registry describes what that deployment can execute.
- `sf.connect()` displays fresh connection state and sends credentials only to that engine.
- model-backed work checks required connections once before spend.
- `fusion.url4` is a reusable parameterized answer recipe.
- `report.url4` is the complete benchmark, slice, Recipe, grading, and aggregation run.
- evaluation sends that expression in one encoded `GET /v1?q=...` transaction.
- successful bodies are plaintext that the SDK parses and validates.
- benchmark data and scoring remain engine-side and reproducible in URL4.

Continue to the quickstart to evaluate GPQA."""
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
