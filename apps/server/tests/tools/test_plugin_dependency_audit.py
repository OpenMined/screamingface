import textwrap
from pathlib import Path

from tools.plugin_dependency_audit import collect_cross_imports, extract_manifest


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
