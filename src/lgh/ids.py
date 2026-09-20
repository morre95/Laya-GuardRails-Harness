from __future__ import annotations

import uuid
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id() -> str:
    fn = getattr(uuid, "uuid7", None)
    if callable(fn):
        return str(fn())
    return str(uuid.uuid4())
