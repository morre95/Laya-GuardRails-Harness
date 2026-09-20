from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lgh.schema.envelope import ActionEnvelope


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def envelope_hash(envelope: ActionEnvelope) -> str:
    payload = envelope.model_dump(mode="json", by_alias=True)
    return sha256_text(canonical_json(payload))


def record_hash(payload: dict) -> str:
    return sha256_text(canonical_json(payload))


def daily_trace_path(directory: Path, timestamp: str) -> Path:
    day = timestamp[:10]
    return directory / f"{day}.jsonl"
