"""Generation of the random "topic" identifier bound into a capability token's
``sub`` claim. The topic is the routing key clients use to attach to a run's
WS/stream, so it must be unguessable.
"""

import secrets
import string

_TOPIC_ALPHABET = string.ascii_letters + string.digits
TOPIC_LENGTH = 64


def new_topic() -> str:
    """Generate a fresh, cryptographically random topic identifier."""
    return "".join(secrets.choice(_TOPIC_ALPHABET) for _ in range(TOPIC_LENGTH))
