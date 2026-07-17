# url4

**A standalone, framework-free core library for the url4 expression protocol.**

url4 expresses multi-source computation as `(sources)!intent` — *"given this data, do
this"* — recursively, with `$name` / `$N` references resolved through a lexical scope. An
expression compiles into an executable **DAG** of typed nodes: each node owns its own logic
behind a small protocol, independent nodes run in parallel, and nested fragments parse
lazily inside the node that owns them. All I/O is inverted behind an `IOLayer` port, so the
core is deterministic and testable.

Part of [ScreamingFace](https://screamingface.ai) by [OpenMined](https://openmined.org).

## Install

```bash
pip install url4
```

url4 requires Python 3.12+ and ships type information (PEP 561).

## Quickstart

```python
from url4 import Client, StaticIOLayer, evaluate_sync

io = StaticIOLayer(fetch_map={"https://x": "some article text"})
text = "(a=https://x, tone='formal')!'Summarize $a in a $tone tone'"

# scripts and REPLs: one call, no event loop to manage
print(evaluate_sync(text, io).text)

# async code owns a Client (Client() with no io speaks real HTTP)
async with Client(io) as client:
    res = await client.evaluate(text)
    print(res.request)               # the canonical url4 text that ran
```

The execution engine — DAG compilation, executor, lowering — lives one level down:
`from url4.dag import compile_expression, run`.

## Features

- **Expression-as-computation** — `(sources)!intent` with recursive fan-out and `$name`/`$N`
  lexical references.
- **Typed DAG** — expressions compile to a graph of typed nodes; independent nodes execute
  concurrently.
- **Inverted I/O** — all side effects go through the `IOLayer` port (`StaticIOLayer` for
  tests/offline, HTTP for real fetches), keeping the core pure and deterministic.
- **Fully typed** — passes `pyright`; type hints ship to consumers.

## License

Apache-2.0 — see [LICENSE](LICENSE).
