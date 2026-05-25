import textwrap
from pathlib import Path

from tools.plugin_dependency_audit import extract_manifest


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
