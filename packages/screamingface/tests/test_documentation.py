from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from runpy import run_path

import pytest

import screamingface as sf

PACKAGE_ROOT = Path(__file__).parents[1]
DOCS_PAGE = PACKAGE_ROOT / "docs" / "index.html"


def _builder(name: str):
    return run_path(str(PACKAGE_ROOT / "scripts" / name))["notebook"]


quickstart_notebook = _builder("build_quickstart.py")
engine_notebook = _builder("build_sf_url4_engine.py")
draco_notebook = _builder("build_draco.py")


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.api_names: set[str] = set()
        self.local_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if api_name := values.get("data-api"):
            self.api_names.add(api_name)
        if tag == "a" and (href := values.get("href")):
            if not href.startswith(("#", "http://", "https://", "mailto:")):
                self.local_links.append(href)


def _notebook_text(document) -> str:
    return "\n".join("".join(cell.get("source", "")) for cell in document.cells)


def test_static_docs_cover_the_complete_public_api_and_local_links() -> None:
    parser = _DocumentParser()
    parser.feed(DOCS_PAGE.read_text(encoding="utf-8"))

    assert parser.api_names == set(sf.__all__)
    assert parser.local_links
    for relative in parser.local_links:
        path = (DOCS_PAGE.parent / relative.split("#", 1)[0]).resolve()
        assert path.exists(), f"broken documentation link: {relative}"


def test_static_docs_pin_the_current_execution_boundary_and_wire_contract() -> None:
    page = DOCS_PAGE.read_text(encoding="utf-8")

    assert "ScreamingFace never calls AI Gateway directly" in page
    assert "real in-process <code>Url4Node</code>" in page
    assert "deterministic model-route handlers" in page
    assert "GET /v1?q=" in page
    assert "screamingface.panel-result.v2" in page
    assert "screamingface.fusion-result.v2" in page
    assert "No silent fallback" in page


def test_static_docs_follow_the_brand_surface_rules() -> None:
    page = DOCS_PAGE.read_text(encoding="utf-8").lower()

    assert "linear-gradient" not in page
    assert "radial-gradient" not in page
    assert "box-shadow" not in page
    assert "border-radius" not in page
    assert "purple" not in page
    assert "prefers-color-scheme" in page


@pytest.mark.parametrize(
    ("document", "level", "required"),
    [
        (quickstart_notebook(), "Path: bare quickstart", "No architecture knowledge required"),
        (engine_notebook(), "Path: architecture walkthrough", "What URL4 returns"),
        (draco_notebook(), "Path: benchmark adapter", "Judge request and response"),
    ],
)
def test_notebooks_declare_their_teaching_level(document, level: str, required: str) -> None:
    text = _notebook_text(document)

    assert level in text
    assert required in text


def test_bare_quickstart_stays_small_and_defers_wire_internals() -> None:
    document = quickstart_notebook()
    text = _notebook_text(document)

    assert len(document.cells) <= 12
    assert "GatherNode" not in text
    assert "screamingface.panel-result.v2" not in text
    assert "sf_url4_engine.ipynb" in text


@pytest.mark.parametrize(
    ("generated", "filename"),
    [
        (quickstart_notebook(), "00_quickstart.ipynb"),
        (engine_notebook(), "sf_url4_engine.ipynb"),
        (draco_notebook(), "draco.ipynb"),
    ],
)
def test_committed_notebook_sources_match_their_builders(generated, filename: str) -> None:
    import nbformat

    committed = nbformat.read(PACKAGE_ROOT / "examples" / filename, as_version=4)
    generated_cells = [(cell.cell_type, cell.id, cell.source) for cell in generated.cells]
    committed_cells = [(cell.cell_type, cell.id, cell.source) for cell in committed.cells]

    assert committed_cells == generated_cells
