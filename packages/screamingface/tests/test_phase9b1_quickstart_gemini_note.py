"""Contract for the dated Gemini compatibility warning in the quickstart."""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK = Path(__file__).parents[1] / "examples" / "00_quickstart.ipynb"


def test_quickstart_explains_current_gemini_and_huggingface_boundaries() -> None:
    document = json.loads(NOTEBOOK.read_text())
    markdown = "\n".join(
        "".join(cell["source"]) for cell in document["cells"] if cell.get("cell_type") == "markdown"
    )

    # INVARIANT: The warning distinguishes observed access from a universal Google rule.
    assert "Gemini compatibility · July 2026" in markdown
    assert "Some newly created Google API projects" in markdown
    assert "model no longer available" in markdown
    assert "quota dashboard" in markdown
    assert "engine whose AI Gateway" in markdown
    assert "yet register" in markdown
    assert "gemini-3.5-flash" in markdown
    assert "gemini-3.1-pro-preview" in markdown
    assert "Hugging Face does not provide Gemini" in markdown
