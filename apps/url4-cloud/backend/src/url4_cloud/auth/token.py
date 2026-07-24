"""Capability topic ids — a per-run unguessable name (spec §4)."""

import secrets
import string

# WHY: [A-Za-z0-9] only — a topic id is embedded in a NATS subject and a URL path, so it must be
# transport-safe with no escaping; 62^64 keyspace from a CSPRNG makes it unguessable.
_TOPIC_ALPHABET = string.ascii_letters + string.digits
TOPIC_LENGTH = 64


def new_topic() -> str:
    """Return a fresh 64-char ``[A-Za-z0-9]`` topic id from a cryptographic RNG."""
    return "".join(secrets.choice(_TOPIC_ALPHABET) for _ in range(TOPIC_LENGTH))
