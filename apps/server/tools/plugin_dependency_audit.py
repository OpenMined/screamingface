"""Audit cross-plugin imports vs declared Plugin.depends manifests.

Usage:
    uv run python -m tools.plugin_dependency_audit \
        --plugins-root apps/server/src/screamingface/plugins \
        --report docs/superpowers/plans/plugin-dependency-audit.md
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginManifest:
    module: str  # plugin directory name, e.g. "claude_frontend"
    name: str  # Plugin.name slug, e.g. "claude-frontend"
    depends: list[str]  # Plugin.depends slugs
    plugin_py: Path


def _literal_str_list(node: ast.AST) -> list[str] | None:
    if not isinstance(node, ast.List):
        return None
    values: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            values.append(elt.value)
        else:
            return None
    return values


def extract_manifest(plugin_py: Path) -> PluginManifest:
    tree = ast.parse(plugin_py.read_text(), filename=str(plugin_py))
    name: str | None = None
    depends: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            # name = "..."
            if isinstance(stmt, ast.Assign):
                targets = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
                if (
                    "name" in targets
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    name = stmt.value.value
                if "depends" in targets:
                    parsed = _literal_str_list(stmt.value)
                    if parsed is not None:
                        depends = parsed
            # depends: list[str] = [...]
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                if (
                    stmt.target.id == "name"
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    name = stmt.value.value
                if stmt.target.id == "depends" and stmt.value is not None:
                    parsed = _literal_str_list(stmt.value)
                    if parsed is not None:
                        depends = parsed
    if name is None:
        # Plugin without a name attribute — use the directory name as a fallback identifier
        name = plugin_py.parent.name
    return PluginManifest(
        module=plugin_py.parent.name,
        name=name,
        depends=depends,
        plugin_py=plugin_py,
    )
