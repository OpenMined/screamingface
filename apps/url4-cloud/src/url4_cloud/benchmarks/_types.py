"""Small internal values shared by benchmark discovery and execution."""

from __future__ import annotations

import ast
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

type BenchmarkAction = Callable[[str, str], str]


def decode_wire(value: str, label: str) -> object:
    """Decode either JSON or URL4's current Python-literal structured text."""
    value = _structured_payload(value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"{label} must be structured data: {exc}") from exc


def _structured_payload(value: str) -> str:
    """Remove URL4's one-name context packing around a structured binding."""
    selected = value.strip()
    if selected.startswith(("{", "[")):
        return selected
    name, separator, payload = selected.partition(": ")
    if separator and name.replace("_", "").isalnum() and payload.startswith(("{", "[")):
        return payload
    return selected


@dataclass(frozen=True, slots=True)
class Benchmark:
    """One installed benchmark descriptor and deterministic action dispatcher."""

    id: str
    title: str
    manifest: bytes
    actions: Mapping[str, BenchmarkAction]
    # WHY: the exam version behind the manifest's `id: <name>-v<version>` — the registry
    # resolves that versioned identity so a plan compiled against one exam version can
    # never silently execute another. Separator is `-v`, NOT `@`: the id travels inside
    # url4 contexts, where `@` is the reserved holdings-reference token.
    version: int = 1

    @property
    def versioned_id(self) -> str:
        return f"{self.id}-v{self.version}"

    def execute(self, action: str, context: str, intent: str) -> str:
        try:
            handler = self.actions[action]
        except KeyError:
            raise ValueError(
                f"benchmark {self.id!r} does not support action {action!r}; "
                f"expected one of {sorted(self.actions)}"
            ) from None
        return handler(context, intent)


__all__ = ["Benchmark", "BenchmarkAction", "decode_wire"]
