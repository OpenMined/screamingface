# Spec — reorganize `src/url4` into intuitive subpackages (OME-499)

## Problem

`packages/url4/src/url4/` ships 24 modules flat in one directory. The
package's actual layering — a pure-Python expression language, an I/O port
with two adapters, a DAG compile/execute engine, two ways to be a network
participant (client / server), and a CLI — exists only in each reader's head.
Nothing on disk marks the boundary between "the language" and "how the
language talks to the network."

## Method

Rather than group files by guessed similarity, the actual intra-package
import graph was extracted with CodeGraph (`codegraph explore`, cross-checked
with `grep -E '^\s*(from url4|import url4)'` over every `src/url4/**/*.py`)
and used to verify each proposed boundary is a real dependency edge, per
`python-expert`'s guidance ("extract subpackages when a boundary is real:
different consumers, different dependencies") and this repo's hexagonal rule
("core defines ports; adapters implement them; core never imports adapters").

## Target layout

```
src/url4/
├── __init__.py       # public re-exports — UNCHANGED surface
├── core/              # the language + shared runtime primitives (leaf layer)
│   ├── errors.py       (was errors.py)         Url4Error hierarchy
│   ├── nodes.py         (was nodes.py)          AST value types
│   ├── _scan.py          (was _scan.py)          tokenizer primitives
│   ├── _annotations.py    (was _annotations.py)   ;key=val directive parsing
│   ├── grammar.py          (was grammar.py)        text -> AST
│   ├── parser.py            (was parser.py)          Parser facade
│   ├── render.py             (was render.py)          AST -> text
│   ├── builders.py            (was builders.py)        programmatic builder API
│   ├── context.py              (was context.py)          scope-frame / $var
│   ├── ensemble.py              (was ensemble.py)          $ref resolution
│   └── subrequest.py             (was subrequest.py)        ?q=... wire codec
├── io/                 # the IOLayer port + its two adapters
│   ├── layer.py          (was io_layer.py)   IOLayer Protocol, FetchRequest/
│   │                                          Result, BoundedIOLayer, capability
│   │                                          protocols (SupportsHoldings, …)
│   ├── http.py             (was io_http.py)    HttpIOLayer (httpx adapter)
│   └── static.py            (was io_static.py)  StaticIOLayer (deterministic)
├── dag/                 # UNCHANGED — node.py, nodes.py, compiler.py, executor.py
├── peer/                 # the two ways to participate in the url4 network
│   ├── client.py           (was client.py)   Client, Url4Result, evaluate_sync
│   └── server.py            (was server.py)   Url4Node, Request
└── cli/                   # the `url4` console script
    ├── app.py               (was cli.py)      argparse entry, main()
    └── _serve.py              (unchanged name)  TOML config + Url4Node/ASGI
                                                   assembly for `url4 serve`
                                                   (CLI-only, underscore kept —
                                                   not part of the public surface)
```

## Why these five boundaries (not others)

- **`core`** is a leaf: none of its 11 modules import from `io`, `dag`,
  `peer`, or `cli` (verified by the import-graph sweep). It has one consumer
  set (every other layer) but zero dependencies outward — the textbook
  "extract when different consumers/dependencies" signal. `context.py` and
  `ensemble.py` were considered for a separate "runtime" split from the pure
  syntax modules (grammar/parser/render/builders/nodes), but nothing outside
  `core` distinguishes the two groups as separate consumers — both `dag` and
  `peer` need both — so splitting further would be boundary-for-its-own-sake
  (`python-expert`: "structure is earned").
- **`io`** groups the `IOLayer` port with its two concrete adapters
  (`HttpIOLayer`, `StaticIOLayer`) in one package — the Go-style convention
  of keeping a port next to its implementations, rather than promoting the
  Protocol into `core` and fragmenting `io` into two one-file packages.
  `dag` and `peer` depend on the *port* (`io.layer`) always, and on
  `io.http` only lazily/optionally (composition-root default), which is the
  adapter discipline the hexagonal rule asks for.
- **`dag`** is untouched: it was already a well-bounded subpackage before
  this reorg (compiler.py lowers AST → DagNode graph, executor.py runs it).
  No file renames — `node.py`/`nodes.py` naming is a pre-existing wart, out
  of scope here (renaming it changes 4-file's worth of edges for a purely
  cosmetic gain and risks confusion mid-reorg).
- **`peer`** groups `client.py` and `server.py`: both are the concrete,
  embeddable façades an integrator constructs to *be* a participant in a
  url4 network — one outbound-only (`Client`), one bidirectional
  (`Url4Node`, since a node serves inbound *and* fetches outbound). Named
  `peer` (not `client`+`server` left flat, not `extend`/`embed`/`api`) to
  match the url4 spec's own vocabulary for a network participant, and to
  avoid colliding with `dag`'s existing `node.py`.
- **`cli`** groups `cli.py` and `_serve.py`: `_serve.py` was initially
  mis-mapped as belonging with `server.py` (both mention "serve"), but
  reading it shows it is CLI-only — TOML config resolution + wrapping
  `Url4Node.asgi()` with admission control specifically for the `url4 serve`
  subcommand. It has one consumer (`cli.py`) and is not re-exported from
  `url4/__init__.py`. Its underscore prefix is preserved in the new location
  to keep signaling "not public API."

## Verified acyclic

`core` (leaf) ← `io` ← `dag` ← `peer` ← `cli`. No sibling imports both ways.
Two intentional runtime-only imports (documented in the source already) stay
intentional: `render.py` lazily imports `parser.py` within `core` to avoid a
literal-time cycle; `client.py`/`server.py`/`dag/executor.py` lazily import
`io.http` as a composition-root default so the base import path stays
httpx-free (this is what `tests/unit/test_import_isolation.py` guards).

## Public API — no change

`import url4` re-exports (`Client`, `Url4Result`, `evaluate_sync`, `Url4Node`,
`Request`, `HttpIOLayer`, `IOLayer`, `StaticIOLayer`, AST node types,
`build`/`walk`, `render`, error classes, builder functions) are unchanged in
name, value, and location (`url4.<name>`) — only where `__init__.py` imports
*from* moves. `pyproject.toml`'s console-script entry point moves:
`url4.cli:main` → `url4.cli.app:main`.

## What breaks (and is accepted)

Deep-module imports (`from url4.grammar import ...`, `from url4.server import
...`, etc.) move. This is a real, sized blast radius — **161 references
across ~24 test files** (`grep`-counted) plus `examples/utils.py` — all
mechanical path rewrites, no semantic changes. Per project memory, this
package has **zero external consumers yet** (clean-room rewrite, not yet
published), so a deep-import path break carries no external compatibility
cost — it is fully contained to this repo's own test suite.

## Non-goals

- No renaming of public classes/functions.
- No change to `dag/`'s internal file names.
- No behavior change of any kind — this is a pure move + import-path rewrite.
