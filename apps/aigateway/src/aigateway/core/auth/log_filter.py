from __future__ import annotations

import logging
import re
from typing import Any, cast


class RedactProvisioningTokenFilter(logging.Filter):
    _HEADER_NAME = "x-aigw-provisioning-token"
    _PATTERN = re.compile(
        r"(X-Aigw-Provisioning-Token[:=\s\"']*)([^\s\"',}]+)",
        re.IGNORECASE,
    )
    _RAW_HEADER_PATTERN = re.compile(
        r"(b?[\"']x-aigw-provisioning-token[\"']\s*,\s*b?[\"'])([^\"']+)",
        re.IGNORECASE,
    )

    @classmethod
    def _redact(cls, value: str) -> str:
        redacted = cls._PATTERN.sub(r"\1[REDACTED]", value)
        return cls._RAW_HEADER_PATTERN.sub(r"\1[REDACTED]", redacted)

    @classmethod
    def _is_header_key(cls, value: object) -> bool:
        if isinstance(value, bytes):
            value = value.decode("latin-1")
        if not isinstance(value, str):
            return False
        return value.lower() == cls._HEADER_NAME

    @staticmethod
    def _redacted_like(value: object) -> object:
        return b"[REDACTED]" if isinstance(value, bytes) else "[REDACTED]"

    @classmethod
    def _redact_obj(cls, value: object) -> object:
        if isinstance(value, str):
            return cls._redact(value)
        if isinstance(value, bytes):
            redacted = cls._redact(value.decode("latin-1"))
            return redacted.encode("latin-1")
        if isinstance(value, tuple):
            if len(value) == 2 and cls._is_header_key(value[0]):
                return (value[0], cls._redacted_like(value[1]))
            return tuple(cls._redact_obj(item) for item in value)
        if isinstance(value, list):
            if len(value) == 2 and cls._is_header_key(value[0]):
                return [value[0], cls._redacted_like(value[1])]
            return [cls._redact_obj(item) for item in value]
        if isinstance(value, dict):
            return {
                key: cls._redacted_like(item) if cls._is_header_key(key) else cls._redact_obj(item)
                for key, item in value.items()
            }
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        redacted_rendered = self._redact(rendered)
        if redacted_rendered != rendered and record.name != "uvicorn.access":
            record.msg = redacted_rendered
            record.args = ()
            return True

        record.msg = self._redact_obj(record.msg)
        record.args = cast(Any, self._redact_obj(record.args))
        return True


def install_provisioning_token_redaction() -> None:
    """Install process-wide redaction for records from any logger/handler path."""
    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, "_aigw_provisioning_token_redaction", False):
        return

    redactor = RedactProvisioningTokenFilter()

    def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current_factory(*args, **kwargs)
        redactor.filter(record)
        return record

    setattr(redacting_factory, "_aigw_provisioning_token_redaction", True)
    logging.setLogRecordFactory(redacting_factory)
