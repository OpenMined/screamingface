"""Syntax-highlight tokenizer for url4 expressions.

Walks the parsed AST and emits a flat list of typed token dicts
that the frontend renders as colored spans.
"""

from __future__ import annotations

from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.url4 import (
    Url4BackendCall,
    Url4Binding,
    Url4ExpandedSource,
    Url4List,
    Url4RelUrl,
    Url4Text,
    Url4Url,
    parse,
)


def tokenize(expr: str) -> list[dict]:
    """Tokenize a url4 expression into highlight spans.

    Returns a list of dicts with keys: type, value, depth.
    """
    source, intent, _broadcast = split_intent(expr)
    ast = parse(source)
    tokens = _walk(ast, depth=0)
    if intent is not None:
        tokens.append({"type": "intent_sep", "value": "!", "depth": 0})
        tokens.append({"type": "intent", "value": intent, "depth": 0})
    return tokens


def _walk(node, depth: int) -> list[dict]:
    if isinstance(node, Url4Url):
        return [{"type": "url", "value": node.value, "depth": depth}]
    if isinstance(node, Url4RelUrl):
        return [{"type": "url", "value": node.value, "depth": depth}]
    if isinstance(node, Url4Text):
        return [{"type": "text", "value": node.value, "depth": depth}]
    if isinstance(node, Url4BackendCall):
        backend_tokens: list[dict] = []
        if node.name:
            backend_tokens.append({"type": "text", "value": f"{node.name}:", "depth": depth})
        if node.weight is not None:
            backend_tokens.append({"type": "text", "value": f"{node.weight:g}:", "depth": depth})
        backend_tokens.append({"type": "url", "value": node.path, "depth": depth})
        backend_tokens.append({"type": "paren", "value": "(", "depth": depth})
        if node.packed_context:
            backend_tokens.append(
                {"type": "text", "value": node.packed_context, "depth": depth + 1}
            )
        backend_tokens.append({"type": "paren", "value": ")", "depth": depth})
        if node.intent is not None:
            backend_tokens.append({"type": "intent_sep", "value": "!", "depth": depth})
            backend_tokens.extend(_walk_intent(node.intent, depth))
        return backend_tokens
    if isinstance(node, Url4ExpandedSource):
        return [{"type": "text", "value": "*", "depth": depth}, *_walk(node.inner, depth)]
    if isinstance(node, Url4Binding):
        return [
            {"type": "text", "value": f"{node.name}{node.kind}", "depth": depth},
            *_walk(node.value, depth),
        ]
    if isinstance(node, Url4List):
        tokens: list[dict] = [{"type": "paren", "value": "(", "depth": depth}]
        for i, item in enumerate(node.items):
            if i > 0:
                tokens.append({"type": "comma", "value": ",", "depth": depth + 1})
                tokens.append({"type": "ws", "value": " ", "depth": depth + 1})
            tokens.extend(_walk(item, depth + 1))
        tokens.append({"type": "paren", "value": ")", "depth": depth})
        return tokens
    raise TypeError(f"Unknown node type: {type(node)}")


def _walk_intent(node, depth: int) -> list[dict]:
    if isinstance(node, Url4Text):
        return [{"type": "intent", "value": node.value, "depth": depth}]
    return _walk(node, depth)
