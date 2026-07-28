"""JobRunner port: the deterministic, stateless job name (spec §3/§5)."""

import re

from url4_cloud.jobs import JobAlreadyExists, JobRunner, JobStatus, job_name

_DNS_1123_LABEL = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?")


def test_job_name_is_deterministic() -> None:
    assert job_name("cap-topic") == job_name("cap-topic")


def test_job_name_is_dns_1123_label_and_prefixed() -> None:
    name = job_name("A" * 64)  # a real 64-char capability topic
    assert name.startswith("url4-")
    assert len(name) <= 63
    assert _DNS_1123_LABEL.fullmatch(name)


def test_job_name_is_topic_sensitive() -> None:
    assert job_name("topic-a") != job_name("topic-b")


def test_port_symbols_are_exported() -> None:
    assert issubclass(JobAlreadyExists, Exception)
    # JobStatus is a Literal alias usable as an annotation; JobRunner is the port Protocol.
    assert JobStatus is not None
    assert hasattr(JobRunner, "schedule")
