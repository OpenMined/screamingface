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

SDK facades — build expressions in Python (:mod:`url4.builders`), print them
canonically (:func:`render`, the certified inverse of :func:`build`), query as
a requestor (:class:`Client`), or stand up a node (:class:`Url4Node`)::

    import asyncio
    from url4 import Client, Url4Node, expr, src

    node = Url4Node("demo")

    @node.endpoint("/claude")
    async def claude(request):          # the intent processor
        return f"[claude] {request.intent}"

    async def main():
        # in-process: the node is its own execution engine (and an IOLayer)
        print(await node.evaluate("(@)!'hello'", env={}))
        # as a requestor, with the expression built in Python
        async with Client(node) as client:
            result = await client.query(src("https://x"), intent="Summarize $1")
            print(result.request)        # the canonical url4 text that ran

    # node.serve(port=4404) exposes the same dispatch over HTTP GET (url4[server])
"""

from __future__ import annotations

from url4.builders import (
    ParamsLike,
    SourceLike,
    broadcast,
    expand,
    expr,
    identity,
    iterate,
    reduce,
    ref,
    self_,
    src,
    struct,
    text,
)
from url4.client import Client, Url4Result
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
    RenderError,
    ResolutionError,
    ScopeError,
    Url4Error,
)
from url4.grammar import parse_value
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
from url4.render import render
from url4.server import Request, Url4Node
from url4.subrequest import decode_subrequest, encode_subrequest, extract_expression_params

__version__ = "0.2.0"

__all__ = [
    "DEFAULT_PROCESSOR",
    "Binding",
    "Client",
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
    "ParamsLike",
    "ParseError",
    "Parser",
    "Payload",
    "RelExpr",
    "RelUrl",
    "RemoteExpr",
    "RenderError",
    "Request",
    "ResolutionError",
    "ScopeError",
    "SelfRef",
    "Source",
    "SourceFailure",
    "SourceLike",
    "StaticIOLayer",
    "StructObject",
    "SupportsFetchEx",
    "SupportsHoldings",
    "Text",
    "Url",
    "Url4Error",
    "Url4Node",
    "Url4Result",
    "VarRef",
    "__version__",
    "broadcast",
    "build",
    "compile_expression",
    "decode_subrequest",
    "encode_subrequest",
    "expand",
    "expr",
    "extract_expression_params",
    "fetch_result",
    "identity",
    "iterate",
    "parse_collection",
    "parse_value",
    "reduce",
    "ref",
    "render",
    "run",
    "self_",
    "src",
    "struct",
    "text",
    "walk",
]
