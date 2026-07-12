"""url4 — a standalone core library for the url4 expression protocol.

url4 expresses multi-source computation as ``(sources)!intent`` — "given this
data, do this" — recursively, with ``$name`` / ``$N`` references (and their
``.field`` / ``[N]`` paths) resolved through a lexical scope. An expression
compiles into an executable **DAG** of typed nodes (:mod:`url4.dag`): each node
owns its own piece of logic behind the :class:`DagNode` protocol, independent
nodes run in parallel, and nested fragments parse lazily inside the node that
owns them. All I/O is inverted behind the :class:`IOLayer` port, so the core is
deterministic and framework-free.

Quickstart::

    import asyncio
    from url4 import StaticIOLayer, compile_expression, run

    io = StaticIOLayer(fetch_map={"https://x": "some article text"})
    text = "(a=https://x, tone='formal')!'Summarize $a in a $tone tone'"

    # One-shot: compile + execute
    print(asyncio.run(run(text, io)))

    # Or inspect the graph first
    graph = compile_expression(text)
    for node in graph.walk():
        print(type(node).__name__)

Iteration (``src*(body)!intent``) resolves to a JSON array of per-row results
(spec §5.3.8); broadcast (``!*``) to a JSON array of per-source result objects
(spec §6.1.4).
"""

from __future__ import annotations

from url4.context import Context
from url4.dag import (
    DEFAULT_PROCESSOR,
    DagNode,
    ExecutionContext,
    Executor,
    Graph,
    LoweringRegistry,
    Payload,
    SourceFailure,
    compile_expression,
    run,
)
from url4.errors import (
    CollectionError,
    CycleError,
    ParseError,
    ResolutionError,
    ScopeError,
    Url4Error,
)
from url4.io_http import HttpIOLayer
from url4.io_layer import (
    FetchRequest,
    FetchResult,
    IOLayer,
    SupportsFetchEx,
    SupportsHoldings,
    fetch_result,
    parse_collection,
)
from url4.io_static import StaticIOLayer
from url4.nodes import (
    Binding,
    Expression,
    ForeachDirectives,
    IdentityRef,
    Iteration,
    IterationDirectives,
    Node,
    RelExpr,
    RelUrl,
    RemoteExpr,
    SelfRef,
    Source,
    StructObject,
    Text,
    Url,
    VarRef,
)
from url4.parser import Parser, build, walk
from url4.subrequest import decode_subrequest, encode_subrequest, extract_expression_params

__version__ = "0.2.0"

__all__ = [
    "DEFAULT_PROCESSOR",
    "Binding",
    "CollectionError",
    "Context",
    "CycleError",
    "DagNode",
    "ExecutionContext",
    "Executor",
    "Expression",
    "FetchRequest",
    "FetchResult",
    "ForeachDirectives",
    "Graph",
    "HttpIOLayer",
    "IOLayer",
    "IdentityRef",
    "Iteration",
    "IterationDirectives",
    "LoweringRegistry",
    "Node",
    "ParseError",
    "Parser",
    "Payload",
    "RelExpr",
    "RelUrl",
    "RemoteExpr",
    "ResolutionError",
    "ScopeError",
    "SelfRef",
    "Source",
    "SourceFailure",
    "StaticIOLayer",
    "StructObject",
    "SupportsFetchEx",
    "SupportsHoldings",
    "Text",
    "Url",
    "Url4Error",
    "VarRef",
    "__version__",
    "build",
    "compile_expression",
    "decode_subrequest",
    "encode_subrequest",
    "extract_expression_params",
    "fetch_result",
    "parse_collection",
    "run",
    "walk",
]
