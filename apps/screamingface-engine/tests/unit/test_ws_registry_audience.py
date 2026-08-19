"""The registry's audience-transition edges — the arm/disarm signal the reaper listens to.

FEATURE: tie a run's lifetime to its audience (OME-890).
"""

from screamingface_engine.ws.registry import ConnectionRegistry


class _Recorder:
    """Records transitions in order, as ("arrived"|"left", topic) pairs."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def audience_arrived(self, topic: str) -> None:
        self.events.append(("arrived", topic))

    def audience_left(self, topic: str) -> None:
        self.events.append(("left", topic))


def test_first_subscriber_arrives_and_last_one_leaves() -> None:
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("t")
    registry.remove("t")

    assert recorder.events == [("arrived", "t"), ("left", "t")]


def test_second_watcher_is_not_an_arrival_and_first_leaver_is_not_a_departure() -> None:
    # INVARIANT: two sockets may legitimately observe one run. The reaper must arm only when
    # the LAST of them goes, never when one of two goes.
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("t")
    registry.add("t")
    registry.remove("t")

    assert recorder.events == [("arrived", "t")]

    registry.remove("t")

    assert recorder.events == [("arrived", "t"), ("left", "t")]


def test_notifier_created_session_still_reads_the_first_add_as_an_arrival() -> None:
    # WHY: `add_notifier` creates a session at ZERO subscribers, so a naive "session already
    # existed" check would swallow the arrival and leave the reaper armed on a watched run.
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add_notifier("t", lambda _frame: None)
    registry.add("t")

    assert recorder.events == [("arrived", "t")]


def test_remove_without_add_fires_nothing() -> None:
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.remove("never-attached")

    assert recorder.events == []


def test_repeated_remove_does_not_fire_left_twice() -> None:
    # INVARIANT: `audience_left` is edge-triggered. A double fire would re-arm a topic whose
    # window the reaper may have already closed.
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("t")
    registry.remove("t")
    registry.remove("t")

    assert recorder.events == [("arrived", "t"), ("left", "t")]


def test_transitions_are_per_topic() -> None:
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("a")
    registry.add("b")
    registry.remove("a")

    assert recorder.events == [("arrived", "a"), ("arrived", "b"), ("left", "a")]


def test_re_attaching_after_the_last_leave_arrives_again() -> None:
    # WHY this matters to the reaper: `remove` discards the whole session at zero, so the
    # re-attach starts from a fresh one. The arrival edge must still fire, or the topic would
    # stay armed while somebody is watching it.
    registry = ConnectionRegistry()
    recorder = _Recorder()
    registry.listen(recorder)

    registry.add("t")
    registry.remove("t")
    registry.add("t")

    assert recorder.events == [("arrived", "t"), ("left", "t"), ("arrived", "t")]


def test_registry_without_a_listener_behaves_exactly_as_before() -> None:
    # INVARIANT: the listener is optional. Every existing test builds a bare registry.
    registry = ConnectionRegistry()

    registry.add("t")
    registry.remove("t")  # must not raise
