"""Errors raised by DRACO's deterministic grading pipeline."""


class AggregateError(ValueError):
    """The reducer's input is unusable and cannot be scored."""
