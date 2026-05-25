import textwrap
from pathlib import Path

from tools.plugin_dependency_audit import (
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


def test_collect_cross_imports_finds_other_plugin_imports(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "claude_frontend"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text("")
    (plugin_dir / "ctx.py").write_text(
        textwrap.dedent("""
        from screamingface.plugins.url4_executor.interpreter import Url4Interpreter
        from screamingface.plugins.frontend_base import FrontendPluginBase
        from screamingface.plugins.claude_frontend.proxy import create_router  # self - ignored
        from some.unrelated.package import thing
        import screamingface.plugins.llm_base.errors as errs
    """).strip()
    )

    imports = collect_cross_imports(plugin_dir)

    assert imports == {
        "url4_executor": [str(plugin_dir / "ctx.py")],
        "frontend_base": [str(plugin_dir / "ctx.py")],
        "llm_base": [str(plugin_dir / "ctx.py")],
    }


def test_audit_all_flags_missing_and_extraneous(tmp_path: Path) -> None:
    a = tmp_path / "alpha"
    a.mkdir()
    (a / "plugin.py").write_text('class A:\n    name = "alpha"\n    depends = ["beta", "ghost"]\n')
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

    assert by_plugin["alpha"].missing == ["gamma"]
    assert by_plugin["alpha"].extraneous == ["ghost"]
    assert by_plugin["beta"].missing == []
    assert by_plugin["beta"].extraneous == []


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
    assert "## Cycles" in report
    assert "## Per-plugin findings" in report
    assert "Plugins audited: **2**" in report
    # Paths must be relative — no absolute /Users/... or tmp_path prefix.
    assert "/Users/" not in report
    assert str(tmp_path) not in report
    assert "alpha/use.py" in report
