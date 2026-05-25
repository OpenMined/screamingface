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


PLUGIN_PKG = "screamingface.plugins"


def _imported_plugin_module(dotted: str) -> str | None:
    """Return the plugin-directory segment from a dotted module path, or None."""
    if not dotted.startswith(PLUGIN_PKG + "."):
        return None
    tail = dotted[len(PLUGIN_PKG) + 1 :]
    head = tail.split(".", 1)[0]
    return head or None


def collect_cross_imports(plugin_dir: Path) -> dict[str, list[str]]:
    """Map imported-plugin-module -> sorted unique list of file paths importing it.

    Self-imports (the plugin importing its own submodules) are excluded.
    """
    self_module = plugin_dir.name
    found: dict[str, set[str]] = {}
    for py in plugin_dir.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            dotted: str | None = None
            if isinstance(node, ast.ImportFrom) and node.module:
                dotted = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    mod = _imported_plugin_module(alias.name)
                    if mod and mod != self_module:
                        found.setdefault(mod, set()).add(str(py))
                continue
            if dotted is None:
                continue
            mod = _imported_plugin_module(dotted)
            if mod and mod != self_module:
                found.setdefault(mod, set()).add(str(py))
    return {k: sorted(v) for k, v in sorted(found.items())}
