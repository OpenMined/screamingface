# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
from screamingface.plugins.url4_executor.url4_ast import Url4BackendCall, Url4List, Url4Text
from screamingface.plugins.url4_executor.url4_grammar import parse


def test_quoted_intent_with_comma_parses_whole():
    node = parse("/claude(q)!'Answer this. Return only the answer, no other text.'")
    assert isinstance(node, Url4BackendCall)
    assert isinstance(node.intent, Url4Text)
    assert node.intent.value == "'Answer this. Return only the answer, no other text.'"


def test_quoted_intent_in_fanout_list_does_not_split_on_inner_commas():
    # MainOne-shaped: two backend calls with comma-laden quoted intents.
    node = parse("(/claude(q)!'Pick A, B, or C.', /codex(q)!'Pick A, B, or C.')")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2  # NOT split on the commas inside the quotes
    assert all(isinstance(i, Url4BackendCall) for i in node.items)
    assert node.items[0].intent.value == "'Pick A, B, or C.'"


def test_double_quoted_intent_with_comma():
    node = parse('/claude(q)!"one, two, three"')
    assert node.intent.value == '"one, two, three"'


def test_comma_free_quoted_intent_unchanged():
    # behavior parity: a comma-free quoted intent still parses as before
    node = parse("/claude(q)!'hello world'")
    assert node.intent.value == "'hello world'"


def test_bare_text_intent_still_works():
    node = parse("/claude(q)!plain text")
    assert node.intent.value == "plain text"
