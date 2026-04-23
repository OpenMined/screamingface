"""Syntax-highlight tokenizer for url4 expressions.

Walks the parsed AST and emits a flat list of typed token dicts
that the frontend renders as colored spans.
"""

from __future__ import annotations

from screamingface.plugins.url4_executor.decoder import split_intent
from screamingface.plugins.url4_executor.url4 import Url4List, Url4Text, Url4Url, parse


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
    if isinstance(node, Url4Text):
        return [{"type": "text", "value": node.value, "depth": depth}]
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
