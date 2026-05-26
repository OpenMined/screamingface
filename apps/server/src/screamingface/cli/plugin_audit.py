"""Audit cross-plugin imports vs declared Plugin.depends manifests.

Usage:
    uv run --directory apps/server sf plugin audit-deps \
        --plugins-root src/screamingface/plugins \
        --report ../../docs/superpowers/plans/plugin-dependency-audit.md

`Plugin.depends` is a runtime activation contract enforced by the plugin
registry. Tests are invoked by pytest, not the registry, so test-only
cross-plugin imports do NOT require a `depends` entry. This audit reports
production imports as actionable and test imports as informational only.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PluginManifest:
    module: str  # plugin directory name, e.g. "claude_frontend"
    name: str  # Plugin.name slug, e.g. "claude-frontend"
    depends: list[str]  # Plugin.depends slugs
    plugin_py: Path
    depends_source: str = "self"  # "self" or "<BaseClassName>" if inherited


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


def _extract_class_attrs(cls: ast.ClassDef) -> tuple[str | None, list[str] | None]:
    """Extract (name, depends) from a class body.

    Returns (name_value_or_None, depends_list_or_None). `depends` is None when
    the class does NOT declare its own `depends` (vs an empty list, which is a
    real declaration of no deps).
    """
    name: str | None = None
    depends: list[str] | None = None
    for stmt in cls.body:
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
    return name, depends


def _base_name(base: ast.expr) -> str | None:
    """Extract the simple class identifier from a base expression."""
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _parsed_module(path: Path, cache: dict[Path, ast.Module]) -> ast.Module | None:
    if path in cache:
        return cache[path]
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except (SyntaxError, OSError, UnicodeDecodeError):
        return None
    cache[path] = tree
    return tree


def _find_class_def(
    name: str,
    plugins_root: Path,
    cache: dict[Path, ast.Module],
) -> ast.ClassDef | None:
    """Find the first `class <name>(...)` definition under plugins_root."""
    for py in plugins_root.rglob("*.py"):
        tree = _parsed_module(py, cache)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == name:
                return node
    return None


def _resolve_inherited_depends(
    bases: list[ast.expr],
    plugins_root: Path,
    cache: dict[Path, ast.Module],
    depth: int = 0,
) -> tuple[list[str], str] | None:
    """Walk bases to find the first ancestor that declares its own `depends`."""
    if depth >= 5:
        return None
    for base in bases:
        base_name = _base_name(base)
        if base_name is None:
            continue
        cls = _find_class_def(base_name, plugins_root, cache)
        if cls is None:
            continue
        _, depends = _extract_class_attrs(cls)
        if depends is not None:
            return depends, base_name
        # Recurse into this base's bases
        deeper = _resolve_inherited_depends(cls.bases, plugins_root, cache, depth + 1)
        if deeper is not None:
            return deeper
    return None


def extract_manifest(
    plugin_py: Path,
    plugins_root: Path | None = None,
) -> PluginManifest:
    tree = ast.parse(plugin_py.read_text(), filename=str(plugin_py))
    name: str | None = None
    depends: list[str] | None = None
    depends_source = "self"
    # Prefer the class that declares either `name` or `depends`. Track the
    # first matching class's bases for inheritance walk.
    chosen_bases: list[ast.expr] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        cls_name, cls_depends = _extract_class_attrs(node)
        if cls_name is not None and name is None:
            name = cls_name
            chosen_bases = node.bases
        if cls_depends is not None and depends is None:
            depends = cls_depends
            if name is None:
                # No name yet — still capture bases in case this class is the
                # one we end up using
                chosen_bases = node.bases

    if depends is None and plugins_root is not None and chosen_bases:
        resolved = _resolve_inherited_depends(chosen_bases, plugins_root, {})
        if resolved is not None:
            depends, depends_source = resolved

    if name is None:
        name = plugin_py.parent.name
    return PluginManifest(
        module=plugin_py.parent.name,
        name=name,
        depends=depends if depends is not None else [],
        plugin_py=plugin_py,
        depends_source=depends_source,
    )


PLUGIN_PKG = "screamingface.plugins"


def _imported_plugin_module(dotted: str) -> str | None:
    """Return the plugin-directory segment from a dotted module path, or None."""
    if not dotted.startswith(PLUGIN_PKG + "."):
        return None
    tail = dotted[len(PLUGIN_PKG) + 1 :]
    head = tail.split(".", 1)[0]
    return head or None


def _is_test_file(py: Path, plugin_dir: Path) -> bool:
    """A file is a test file iff it sits under a `tests/` segment, OR its
    filename starts with `test_`, OR its filename is `conftest.py`.
    """
    try:
        rel = py.relative_to(plugin_dir)
    except ValueError:
        rel = py
    parts = rel.parts
    if "tests" in parts:
        return True
    name = py.name
    if name == "conftest.py":
        return True
    if name.startswith("test_"):
        return True
    return False


@dataclass(frozen=True)
class CrossImports:
    """Cross-plugin imports observed within a single plugin directory.

    Both maps are: imported-plugin-module -> sorted unique list of file paths
    importing it. `prod` covers production files; `tests` covers files
    classified as test code (see `_is_test_file`).
    """

    prod: dict[str, list[str]] = field(default_factory=dict)
    tests: dict[str, list[str]] = field(default_factory=dict)


def collect_cross_imports(plugin_dir: Path) -> CrossImports:
    """Walk `plugin_dir` and bucket cross-plugin imports into prod vs tests.

    Self-imports (the plugin importing its own submodules) are excluded.
    """
    self_module = plugin_dir.name
    prod_found: dict[str, set[str]] = {}
    test_found: dict[str, set[str]] = {}
    for py in plugin_dir.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError:
            continue
        bucket = test_found if _is_test_file(py, plugin_dir) else prod_found
        for node in ast.walk(tree):
            dotted: str | None = None
            if isinstance(node, ast.ImportFrom) and node.module:
                dotted = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    mod = _imported_plugin_module(alias.name)
                    if mod and mod != self_module:
                        bucket.setdefault(mod, set()).add(str(py))
                continue
            if dotted is None:
                continue
            mod = _imported_plugin_module(dotted)
            if mod and mod != self_module:
                bucket.setdefault(mod, set()).add(str(py))
    return CrossImports(
        prod={k: sorted(v) for k, v in sorted(prod_found.items())},
        tests={k: sorted(v) for k, v in sorted(test_found.items())},
    )


@dataclass(frozen=True)
class AuditFinding:
    plugin_name: str  # slug
    plugin_module: str  # dir name
    declared: list[str]  # depends, as declared (slugs)
    prod_imports: dict[str, list[str]]  # module -> files (prod only)
    test_imports: dict[str, list[str]]  # module -> files (tests only)
    prod_missing: list[str]  # imported by prod, not declared (slugs)
    test_only_missing: list[str]  # imported only by tests and not declared (slugs)
    extraneous: list[str]  # declared but unused by either prod or tests (slugs)


def _slug_for_module(module: str, by_module: dict[str, PluginManifest]) -> str:
    mf = by_module.get(module)
    return mf.name if mf else module  # fall back to directory name


def audit_all(plugins_root: Path) -> list[AuditFinding]:
    plugin_dirs = sorted(
        p
        for p in plugins_root.iterdir()
        if p.is_dir() and (p / "plugin.py").exists() and not p.name.startswith("_")
    )
    manifests = [extract_manifest(p / "plugin.py", plugins_root=plugins_root) for p in plugin_dirs]
    by_module = {m.module: m for m in manifests}

    findings: list[AuditFinding] = []
    for mf in manifests:
        imports = collect_cross_imports(mf.plugin_py.parent)
        prod_slugs = {_slug_for_module(m, by_module) for m in imports.prod}
        test_slugs = {_slug_for_module(m, by_module) for m in imports.tests}
        declared = list(mf.depends)
        declared_set = set(declared)
        prod_missing = sorted(prod_slugs - declared_set)
        # test-only-missing: imported by tests, not by prod, and not declared
        test_only_missing = sorted((test_slugs - prod_slugs) - declared_set)
        extraneous = sorted(declared_set - prod_slugs - test_slugs)
        findings.append(
            AuditFinding(
                plugin_name=mf.name,
                plugin_module=mf.module,
                declared=declared,
                prod_imports=imports.prod,
                test_imports=imports.tests,
                prod_missing=prod_missing,
                test_only_missing=test_only_missing,
                extraneous=extraneous,
            )
        )
    return findings


def find_cycles(findings: list[AuditFinding]) -> list[list[str]]:
    """Return cycles in the *production* import graph, keyed by slug.

    Test-only edges are ignored: a cycle through a test file is not a real
    runtime activation cycle.
    """
    name_by_module = {f.plugin_module: f.plugin_name for f in findings}
    graph: dict[str, set[str]] = {f.plugin_name: set() for f in findings}
    for f in findings:
        for mod in f.prod_imports:
            tgt = name_by_module.get(mod, mod)
            if tgt in graph:
                graph[f.plugin_name].add(tgt)

    cycles: list[list[str]] = []
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in graph}
    stack: list[str] = []

    def dfs(n: str) -> None:
        color[n] = GREY
        stack.append(n)
        for m in sorted(graph[n]):
            if color[m] == GREY:
                cycle = stack[stack.index(m) :] + [m]
                cycles.append(cycle)
            elif color[m] == WHITE:
                dfs(m)
        stack.pop()
        color[n] = BLACK

    for n in sorted(graph):
        if color[n] == WHITE:
            dfs(n)
    # Deduplicate by frozenset of nodes
    seen: set[frozenset[str]] = set()
    unique: list[list[str]] = []
    for c in cycles:
        key = frozenset(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _display_path(path: str, repo_root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _render_import_section(
    label: str,
    imports: dict[str, list[str]],
    repo_root: Path,
    *,
    collapsed: bool,
) -> list[str]:
    """Render an imports subsection, optionally wrapped in a <details> block."""
    lines: list[str] = []
    if not imports:
        lines.append(f"- **{label}:** _(none)_")
        return lines
    if collapsed:
        lines.append("- <details><summary><b>" + label + "</b></summary>")
        lines.append("")
        for mod, files in imports.items():
            lines.append(f"  - `{mod}` - {len(files)} file(s)")
            for path in files:
                lines.append(f"    - `{_display_path(path, repo_root)}`")
        lines.append("")
        lines.append("  </details>")
    else:
        lines.append(f"- **{label}:**")
        for mod, files in imports.items():
            lines.append(f"  - `{mod}` - {len(files)} file(s)")
            for path in files:
                lines.append(f"    - `{_display_path(path, repo_root)}`")
    return lines


def render_report(
    findings: list[AuditFinding],
    cycles: list[list[str]],
    plugins_root: Path,
    repo_root: Path | None = None,
) -> str:
    if repo_root is None:
        # Heuristic: plugins live at <repo_root>/apps/server/src/screamingface/plugins
        try:
            repo_root = plugins_root.resolve().parents[4]
        except IndexError:
            repo_root = plugins_root.resolve()
    plugins_root_display = (
        plugins_root.resolve().relative_to(repo_root).as_posix()
        if _is_relative_to(plugins_root.resolve(), repo_root)
        else plugins_root.as_posix()
    )

    lines: list[str] = []
    lines.append("# Plugin Dependency Audit\n")
    lines.append(
        "Audit of cross-plugin imports under "
        f"`{plugins_root_display}` against each plugin's `Plugin.depends` manifest. "
        "Generated by `sf plugin audit-deps`.\n"
    )
    lines.append(
        "`Plugin.depends` is a runtime activation contract — only production "
        "imports require a declared dependency. Test-only cross-plugin imports "
        "(under `tests/`, `test_*.py`, or `conftest.py`) are reported separately "
        "as informational.\n"
    )
    lines.append("## Summary\n")
    total = len(findings)
    with_prod_missing = sum(1 for f in findings if f.prod_missing)
    with_test_only_missing = sum(1 for f in findings if f.test_only_missing)
    with_extra = sum(1 for f in findings if f.extraneous)
    lines.append(
        f"- Plugins audited: **{total}**\n"
        f"- Plugins with **missing** prod deps (imported by production code, not declared): "
        f"**{with_prod_missing}**\n"
        f"- Plugins with test-only imports of undeclared plugins: "
        f"**{with_test_only_missing}** (informational)\n"
        f"- Plugins with **extraneous** deps (declared but never imported): **{with_extra}**\n"
        f"- Cycles detected (production edges only): **{len(cycles)}**\n"
    )

    lines.append("## Cycles (production edges only)\n")
    if cycles:
        for c in cycles:
            lines.append("- " + " -> ".join(c))
        lines.append("")
    else:
        lines.append("None detected.\n")

    lines.append("## Per-plugin findings\n")
    for f in findings:
        lines.append(f"### `{f.plugin_name}` (`{f.plugin_module}/`)\n")
        lines.append(f"- **Declared `depends`:** {f.declared or '_(none)_'}")
        lines.append(
            "- **Missing in prod (imported by production code, not declared):** "
            f"{f.prod_missing or '_(none)_'}"
        )
        lines.append(f"- **Extraneous (declared, not imported):** {f.extraneous or '_(none)_'}")
        lines.append(
            "- **Test-only imports of undeclared plugins (informational):** "
            f"{f.test_only_missing or '_(none)_'}"
        )
        prod_collapsed = not (f.prod_missing or f.extraneous)
        lines.extend(
            _render_import_section(
                "Prod imports observed",
                f.prod_imports,
                repo_root,
                collapsed=prod_collapsed,
            )
        )
        test_collapsed = not f.test_only_missing
        lines.extend(
            _render_import_section(
                "Test imports observed",
                f.test_imports,
                repo_root,
                collapsed=test_collapsed,
            )
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
