import textwrap
from pathlib import Path

from typer.testing import CliRunner

from screamingface.cli.main import app
from screamingface.cli.plugin_audit import (
    audit_all,
    collect_cross_imports,
    extract_manifest,
    find_cycles,
    render_report,
)


def test_extract_manifest_reads_name_and_depends(tmp_path: Path) -> None:
    plugin_py = tmp_path / "plugin.py"
    plugin_py.write_text(
        textwrap.dedent("""
        from screamingface.plugins.frontend_base import FrontendPluginBase

        class ClaudeFrontendPlugin(FrontendPluginBase):
            name = "claude-frontend"
            depends: list[str] = ["url4-specs", "url4-executor", "frontend-base"]
    """).strip()
    )

    manifest = extract_manifest(plugin_py)

    assert manifest.name == "claude-frontend"
    assert manifest.depends == ["url4-specs", "url4-executor", "frontend-base"]


def test_extract_manifest_handles_missing_depends(tmp_path: Path) -> None:
    plugin_py = tmp_path / "plugin.py"
    plugin_py.write_text(
        textwrap.dedent("""
        class FooPlugin:
            name = "foo"
    """).strip()
    )

    manifest = extract_manifest(plugin_py)

    assert manifest.name == "foo"
    assert manifest.depends == []


def test_collect_cross_imports_splits_prod_and_test(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "claude_frontend"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text("")
    # Prod file imports url4_executor and frontend_base
    (plugin_dir / "ctx.py").write_text(
        textwrap.dedent("""
        from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
        from screamingface.plugins.frontend_base import FrontendPluginBase
        from screamingface.plugins.claude_frontend.proxy import create_router  # self - ignored
        from some.unrelated.package import thing
        import screamingface.plugins.llm_base.errors as errs
    """).strip()
    )
    # Test file under tests/ imports a different sibling: aigw_base
    tests_dir = plugin_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_ctx.py").write_text("from screamingface.plugins.aigw_base import x\n")

    imports = collect_cross_imports(plugin_dir)

    assert imports.prod == {
        "url4_executor": [str(plugin_dir / "ctx.py")],
        "frontend_base": [str(plugin_dir / "ctx.py")],
        "llm_base": [str(plugin_dir / "ctx.py")],
    }
    assert imports.tests == {
        "aigw_base": [str(tests_dir / "test_ctx.py")],
    }


def test_collect_cross_imports_classifies_top_level_test_file_as_test(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "alpha"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text("")
    # No tests/ directory — but the filename starts with test_
    (plugin_dir / "test_foo.py").write_text("from screamingface.plugins.beta import x\n")

    imports = collect_cross_imports(plugin_dir)

    assert imports.prod == {}
    assert imports.tests == {"beta": [str(plugin_dir / "test_foo.py")]}


def test_collect_cross_imports_classifies_conftest_as_test(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "alpha"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text("")
    (plugin_dir / "conftest.py").write_text("from screamingface.plugins.beta import x\n")

    imports = collect_cross_imports(plugin_dir)

    assert imports.prod == {}
    assert imports.tests == {"beta": [str(plugin_dir / "conftest.py")]}


def test_audit_all_flags_prod_missing_and_extraneous(tmp_path: Path) -> None:
    a = tmp_path / "alpha"
    a.mkdir()
    (a / "plugin.py").write_text('class A:\n    name = "alpha"\n    depends = ["beta", "ghost"]\n')
    # Prod file imports beta and gamma
    (a / "use.py").write_text(
        "from screamingface.plugins.beta.x import y\nfrom screamingface.plugins.gamma import z\n"
    )
    b = tmp_path / "beta"
    b.mkdir()
    (b / "plugin.py").write_text('class B:\n    name = "beta"\n    depends = []\n')
    g = tmp_path / "gamma"
    g.mkdir()
    (g / "plugin.py").write_text('class G:\n    name = "gamma"\n    depends = []\n')

    findings = audit_all(tmp_path)
    by_plugin = {f.plugin_name: f for f in findings}

    assert by_plugin["alpha"].prod_missing == ["gamma"]
    assert by_plugin["alpha"].test_only_missing == []
    assert by_plugin["alpha"].extraneous == ["ghost"]
    assert by_plugin["beta"].prod_missing == []
    assert by_plugin["beta"].extraneous == []


def test_audit_all_test_only_imports_are_informational(tmp_path: Path) -> None:
    a = tmp_path / "alpha"
    a.mkdir()
    (a / "plugin.py").write_text('class A:\n    name = "alpha"\n    depends = []\n')
    tests_dir = a / "tests"
    tests_dir.mkdir()
    # Test-only import of beta — must NOT show up in prod_missing
    (tests_dir / "test_alpha.py").write_text("from screamingface.plugins.beta import x\n")
    b = tmp_path / "beta"
    b.mkdir()
    (b / "plugin.py").write_text('class B:\n    name = "beta"\n    depends = []\n')

    findings = audit_all(tmp_path)
    by_plugin = {f.plugin_name: f for f in findings}

    assert by_plugin["alpha"].prod_missing == []
    assert by_plugin["alpha"].test_only_missing == ["beta"]
    assert by_plugin["alpha"].extraneous == []
    # The test_imports map exposes the underlying file
    assert "beta" in by_plugin["alpha"].test_imports


def test_find_cycles_detects_two_cycle(tmp_path: Path) -> None:
    a = tmp_path / "alpha"
    a.mkdir()
    (a / "plugin.py").write_text('class A:\n    name = "alpha"\n    depends = ["beta"]\n')
    (a / "u.py").write_text("from screamingface.plugins.beta import x\n")
    b = tmp_path / "beta"
    b.mkdir()
    (b / "plugin.py").write_text('class B:\n    name = "beta"\n    depends = ["alpha"]\n')
    (b / "u.py").write_text("from screamingface.plugins.alpha import y\n")

    findings = audit_all(tmp_path)
    cycles = find_cycles(findings)

    assert any(set(c) == {"alpha", "beta"} for c in cycles)


def test_find_cycles_ignores_test_only_back_edge(tmp_path: Path) -> None:
    """A cycle whose back-edge is only via a test file is NOT a real cycle."""
    a = tmp_path / "alpha"
    a.mkdir()
    (a / "plugin.py").write_text('class A:\n    name = "alpha"\n    depends = ["beta"]\n')
    # Back-edge alpha -> beta via test only
    a_tests = a / "tests"
    a_tests.mkdir()
    (a_tests / "test_alpha.py").write_text("from screamingface.plugins.beta import x\n")
    b = tmp_path / "beta"
    b.mkdir()
    (b / "plugin.py").write_text('class B:\n    name = "beta"\n    depends = []\n')
    # Forward edge beta -> alpha via prod
    (b / "u.py").write_text("from screamingface.plugins.alpha import y\n")

    findings = audit_all(tmp_path)
    cycles = find_cycles(findings)

    assert not any(set(c) == {"alpha", "beta"} for c in cycles)


def test_extract_manifest_inherits_depends_from_base_in_other_file(tmp_path: Path) -> None:
    base = tmp_path / "base_plugin"
    base.mkdir()
    (base / "plugin.py").write_text(
        textwrap.dedent("""
        from typing import ClassVar

        class BasePlugin(Plugin):
            depends: ClassVar[list[str]] = ["other"]
    """).strip()
    )
    child = tmp_path / "child_plugin"
    child.mkdir()
    (child / "plugin.py").write_text(
        textwrap.dedent("""
        from base_plugin.plugin import BasePlugin

        class ChildPlugin(BasePlugin):
            name = "child"
    """).strip()
    )

    manifest = extract_manifest(child / "plugin.py", plugins_root=tmp_path)

    assert manifest.depends == ["other"]
    assert manifest.depends_source == "BasePlugin"


def test_extract_manifest_self_depends_takes_precedence_over_base(tmp_path: Path) -> None:
    base = tmp_path / "base_plugin"
    base.mkdir()
    (base / "plugin.py").write_text(
        textwrap.dedent("""
        class BasePlugin:
            depends = ["y"]
    """).strip()
    )
    child = tmp_path / "child_plugin"
    child.mkdir()
    (child / "plugin.py").write_text(
        textwrap.dedent("""
        from base_plugin.plugin import BasePlugin

        class ChildPlugin(BasePlugin):
            name = "child"
            depends = ["x"]
    """).strip()
    )

    manifest = extract_manifest(child / "plugin.py", plugins_root=tmp_path)

    assert manifest.depends == ["x"]
    assert manifest.depends_source == "self"


def test_extract_manifest_unfound_base_is_skipped(tmp_path: Path) -> None:
    child = tmp_path / "child_plugin"
    child.mkdir()
    (child / "plugin.py").write_text(
        textwrap.dedent("""
        class ChildPlugin(SomeExternalThing):
            name = "child"
    """).strip()
    )

    manifest = extract_manifest(child / "plugin.py", plugins_root=tmp_path)

    assert manifest.depends == []
    assert manifest.depends_source == "self"


def test_render_report_uses_relative_paths_and_sections(tmp_path: Path) -> None:
    a = tmp_path / "alpha"
    a.mkdir()
    (a / "plugin.py").write_text('class A:\n    name = "alpha"\n    depends = ["beta"]\n')
    (a / "use.py").write_text("from screamingface.plugins.beta.x import y\n")
    b = tmp_path / "beta"
    b.mkdir()
    (b / "plugin.py").write_text('class B:\n    name = "beta"\n    depends = []\n')

    findings = audit_all(tmp_path)
    cycles = find_cycles(findings)
    report = render_report(findings, cycles, tmp_path, repo_root=tmp_path)

    assert "# Plugin Dependency Audit" in report
    assert "## Summary" in report
    assert "## Cycles (production edges only)" in report
    assert "## Per-plugin findings" in report
    assert "Plugins audited: **2**" in report
    assert "Test-only imports of undeclared plugins" in report
    assert "Prod imports observed" in report
    # Paths must be relative — no absolute /Users/... or tmp_path prefix.
    assert "/Users/" not in report
    assert str(tmp_path) not in report
    assert "alpha/use.py" in report


def test_sf_plugin_audit_deps_writes_report(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "p").mkdir()
    (plugins / "p" / "plugin.py").write_text('class P:\n    name = "p"\n    depends = []\n')

    report = tmp_path / "audit.md"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["plugin", "audit-deps", "--plugins-root", str(plugins), "--report", str(report)],
    )

    assert result.exit_code == 0, result.output
    assert report.exists()
    content = report.read_text()
    assert "# Plugin Dependency Audit" in content
    assert "`p`" in content
