from screamingface.plugins.url4_executor.decoder import (
    ForeachDirectives,
    split_foreach_annotations,
)


def test_extracts_concurrency_and_on_error():
    clean, d = split_foreach_annotations("X;foreach.concurrency=10;foreach.on_error=collect")
    assert clean == "X"
    assert d == ForeachDirectives(concurrency=10, on_error="collect")


def test_absent_annotations_returns_defaults():
    clean, d = split_foreach_annotations("X")
    assert clean == "X"
    assert d == ForeachDirectives(concurrency=None, on_error="abort")


def test_semicolon_inside_parens_is_ignored():
    clean, d = split_foreach_annotations("(/claude(a;b)!x);foreach.concurrency=4")
    assert clean == "(/claude(a;b)!x)"
    assert d.concurrency == 4


def test_unknown_directive_ignored_and_whitespace_trimmed():
    clean, d = split_foreach_annotations("X ;foreach.concurrency=2; foreach.unknown=z")
    assert clean == "X"
    assert d.concurrency == 2
    assert d.on_error == "abort"


def test_non_integer_concurrency_falls_back_to_none():
    _, d = split_foreach_annotations("X;foreach.concurrency=abc")
    assert d.concurrency is None
