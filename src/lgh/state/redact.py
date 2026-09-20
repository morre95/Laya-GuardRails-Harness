from __future__ import annotations

import re

_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|authorization)\s*[:=]\s*['\"]?([^\s'\"]+)"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-+=/]+"),
    re.compile(r"(?i)(sk-[a-z0-9]{10,})"),
    re.compile(r"(?i)(gh[pousr]_[A-Za-z0-9]{20,})"),
    re.compile(r"(?i)(xox[baprs]-[A-Za-z0-9-]{10,})"),
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    re.compile(r"(?i)(eyJ[a-z0-9_-]{20,}\.[a-z0-9_-]{10,})"),
]


def redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = _PEM.sub("[REDACTED_PRIVATE_KEY]", value)
    for pattern in _PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def is_sensitive_target(target: str | None) -> bool:
    if not target:
        return False
    lowered = target.replace("\\", "/").lower()
    name = lowered.rsplit("/", 1)[-1]
    return (
        name.startswith(".env")
        or name.endswith(".pem")
        or name.endswith(".key")
        or "/.ssh/" in lowered
        or name in {"id_rsa", "id_ed25519", "credentials.json", "secrets.yaml", "secrets.yml"}
    )
