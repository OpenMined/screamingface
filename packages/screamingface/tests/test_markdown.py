"""The safe markdown-subset renderer for untrusted answer text.

INVARIANT under test: the input is UNTRUSTED model output. Nothing it contains may reach the
page as live HTML — the renderer escapes every character first and only ever emits its own
fixed tag set. `<script>`, `<img onerror>`, and `javascript:` links must all come out inert.
"""

from __future__ import annotations

from screamingface._ui.markdown import render_markdown


def test_empty_text_renders_nothing() -> None:
    assert render_markdown("") == ""


def test_plain_text_becomes_a_paragraph() -> None:
    assert render_markdown("just prose") == "<p>just prose</p>"


def test_soft_line_breaks_are_preserved_within_a_paragraph() -> None:
    assert render_markdown("line one\nline two") == "<p>line one<br>line two</p>"


def test_headings_are_tamed_to_h4_through_h6() -> None:
    assert "<h4>Title</h4>" in render_markdown("# Title")
    assert "<h5>Sub</h5>" in render_markdown("## Sub")
    assert "<h6>Deep</h6>" in render_markdown("### Deep")
    # a lone '#' must never render a page-dominating hero — level caps at h6.
    assert "<h6>Deeper</h6>" in render_markdown("##### Deeper")


def test_bold_and_italic_via_asterisks() -> None:
    assert render_markdown("**DiD**") == "<p><strong>DiD</strong></p>"
    assert render_markdown("*parallel trends*") == "<p><em>parallel trends</em></p>"


def test_underscores_are_left_alone_so_snake_case_survives() -> None:
    # WHY: answers are technical; underscore-emphasis would mangle estimator_test / __init__.
    assert render_markdown("call estimator_test now") == "<p>call estimator_test now</p>"


def test_inline_code_is_wrapped_and_not_reformatted() -> None:
    assert render_markdown("see `estimator.py`") == "<p>see <code>estimator.py</code></p>"
    # markdown inside a code span stays literal.
    assert render_markdown("`**x**`") == "<p><code>**x**</code></p>"


def test_fenced_code_block_renders_as_pre_code() -> None:
    out = render_markdown("```\nfit(x)\n```")
    assert "<pre class='sf-md__pre'><code>" in out
    assert "fit(x)" in out
    # no inline processing inside a fence.
    assert "<strong>" not in render_markdown("```\n**x**\n```")


def test_unclosed_fence_runs_to_end_of_text() -> None:
    out = render_markdown("```\nabc\ndef")
    assert "<pre class='sf-md__pre'><code>abc\ndef</code></pre>" == out


def test_unordered_and_ordered_lists() -> None:
    assert render_markdown("- a\n- b") == "<ul><li>a</li><li>b</li></ul>"
    assert render_markdown("1. a\n2. b") == "<ol><li>a</li><li>b</li></ol>"


def test_blockquote() -> None:
    assert render_markdown("> a note") == "<blockquote>a note</blockquote>"


def test_inline_formatting_applies_inside_blocks() -> None:
    assert render_markdown("## **Hi**") == "<h5><strong>Hi</strong></h5>"
    assert render_markdown("- **bold** item") == "<ul><li><strong>bold</strong> item</li></ul>"


def test_multiple_blocks_render_in_order() -> None:
    out = render_markdown("# Findings\n\n- one\n- two\n\ntrailing prose")
    assert out == ("<h4>Findings</h4><ul><li>one</li><li>two</li></ul><p>trailing prose</p>")


def test_safe_links_render_as_anchors() -> None:
    out = render_markdown("[docs](https://x.com/a)")
    assert '<a href="https://x.com/a"' in out
    assert 'target="_blank"' in out
    assert 'rel="noopener noreferrer"' in out
    assert ">docs</a>" in out


def test_unsafe_link_scheme_is_never_an_anchor() -> None:
    out = render_markdown("[x](javascript:alert(1))")
    assert "<a " not in out
    assert "href" not in out


def test_script_in_source_is_escaped_not_executed() -> None:
    out = render_markdown("<script>alert('x')</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_html_in_a_code_span_is_escaped() -> None:
    out = render_markdown("`<script>`")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_image_onerror_payload_is_escaped() -> None:
    out = render_markdown("<img src=x onerror=alert(1)>")
    assert "<img" not in out
    assert "&lt;img" in out
