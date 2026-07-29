"""Subject and stream naming.

This file is what survives `test_subjects_contract.py`, which existed because `subjects.py` was
duplicated across two distributions that could not import each other — every test there compared
the two copies, and the merge left nothing to compare. The invariant below is different in kind:
it constrains the two DERIVATIONS against each other, and would still fail if someone collapsed
them, one copy or two.
"""

from url4_cloud import subjects

TOPIC = "run-01JABCDEF"


def test_subject_and_stream_stay_distinguishable() -> None:
    # The two derivations differ only by separator; collapsing them would make `add_stream` and
    # `publish` disagree in a way neither side can see — the App would subscribe to a stream
    # nothing publishes to, and an attached client would get heartbeats forever, never a
    # terminal frame.
    assert subjects.subject_for(TOPIC) != subjects.stream_for(TOPIC)
