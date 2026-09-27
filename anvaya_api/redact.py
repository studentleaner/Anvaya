"""Redaction: never let a secret-shaped string leave this process, in either direction (into the AbstractAI
prompt, or into an ingested document). Deliberately crude regexes over a real secrets scanner - false positives
(over-redacting) are the safe failure mode here; false negatives are not.
"""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|pat)\s*[:=]\s*\S+"),  # key: value / key=value
    re.compile(r"sk-[A-Za-z0-9]{16,}"),          # OpenAI/DeepSeek-style keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),   # GitHub tokens
    re.compile(r"\bDragonflies123#"),            # this project's one known standard password, verbatim (no
                                                  # trailing \b: "#" is non-word, so a boundary after it only
                                                  # exists when followed immediately by a word character)
    re.compile(r"\bAWS[A-Za-z0-9/+=]{20,}\b"),
]

REDACTED = "[REDACTED]"


def redact(text: str) -> tuple[str, int]:
    """Return (redacted_text, count of spans redacted). Patterns are applied in order; each pattern's OWN matches
    are counted before substitution (a pattern never sees text an earlier pattern already redacted, since a
    REDACTED span can't match a later pattern here - kept simple and testable, not a general scrubber)."""
    count = 0
    out = text
    for pattern in _PATTERNS:
        matches = pattern.findall(out)
        if matches:
            count += len(matches)
            out = pattern.sub(REDACTED, out)
    return out, count
