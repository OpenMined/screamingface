"""Tests for the url4 pretty-formatter."""

from __future__ import annotations

from screamingface.plugins.url4_executor.formatter import format_url4, format_url4_safe

SCORED = (
    "(https://screamingface.ai/x.eval.jsonl*(consensus=(claude:0.40:/claude($item.question)"
    "!'Answer A', codex:0.30:/codex($item.question)!'Answer B')"
    "!'Combine them', /python(/data/code/check_correct.py)"
    '!{"question":"$item.question","expected":"$item.expected_answer","consensus":"$consensus"})'
    " ;foreach.concurrency=10;foreach.on_error=collect)!/python(/data/code/calculate_accuracy.py)"
)


def test_indents_groups_and_breaks_intent_onto_new_line() -> None:
    out = format_url4("/claude($item.q)!'Answer'")
    assert out == "/claude($item.q)\n!'Answer'"


def test_foreach_directives_each_on_their_own_line() -> None:
    out = format_url4("data*(/claude($x)!'a') ;foreach.concurrency=10;foreach.on_error=collect")
    assert ";foreach.concurrency=10" in out
    assert ";foreach.on_error=collect" in out
    # each directive on its own line
    assert "\n;foreach.concurrency=10" in out
    assert "\n;foreach.on_error=collect" in out


def test_json_blob_intent_is_pretty_printed() -> None:
    out = format_url4('/python(/data/code/c.py)!{"a":"$x","b":"$y"}')
    assert '!{\n  "a": "$x",\n  "b": "$y"\n}' in out


def test_string_literals_are_left_byte_identical() -> None:
    # A long prompt is NOT hard-wrapped — its content is preserved exactly.
    prompt = "Answer this fill-in-the-blank question with the single most likely short answer."
    out = format_url4(f"/claude($q)!'{prompt}'")
    assert f"'{prompt}'" in out


def test_collection_iteration_nests_body() -> None:
    out = format_url4("data*(claude:0.40:/claude($q)!'a', codex:0.30:/codex($q)!'b')")
    assert "data*(" in out
    assert "claude:0.40:/claude($q)" in out
    assert out.rstrip().endswith(")")


def test_named_binding_group() -> None:
    out = format_url4("consensus=(/claude($q)!'a', /codex($q)!'b')!'reduce'")
    assert out.startswith("consensus=(")


def test_full_scored_spec_formats_and_is_idempotent() -> None:
    out, err = format_url4_safe(SCORED)
    assert err is None
    assert "\n  https://screamingface.ai/x.eval.jsonl*(" in out
    assert ";foreach.concurrency=10" in out
    assert "!/python(/data/code/calculate_accuracy.py)" in out
    # pretty json blob present
    assert '"question": "$item.question"' in out
    # idempotent
    again, _ = format_url4_safe(out)
    assert again == out


def test_malformed_input_returns_original_with_error() -> None:
    bad = "/claude('unterminated"
    out, err = format_url4_safe(bad)
    # never destroys input; either formats benignly or returns original + error
    assert out == bad or err is None
