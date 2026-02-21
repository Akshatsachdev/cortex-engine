from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)secret\s*[:=]\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)token\s*[:=]\s*['\"][^'\"]+['\"]"),
]


def contains_secrets(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)