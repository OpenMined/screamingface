"""Stable names shared by Benchmark builders and the Runner adapter."""

CANDIDATE_ROUTE = "/candidate"
CANDIDATE_INPUT_SCHEMA = "screamingface.candidate-input.v1"
CANDIDATE_MESSAGE_ROLES = frozenset({"system", "developer", "user", "assistant"})

__all__ = ["CANDIDATE_INPUT_SCHEMA", "CANDIDATE_MESSAGE_ROLES", "CANDIDATE_ROUTE"]
