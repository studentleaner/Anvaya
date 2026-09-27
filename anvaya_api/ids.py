"""ULID-style ids (48-bit ms timestamp + 80 random bits, Crockford base32, 26 chars) with a type prefix."""

from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str, now_ms: int | None = None) -> str:
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    n = (ms << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[n & 31])
        n >>= 5
    return f"{prefix}_{''.join(reversed(chars))}"
