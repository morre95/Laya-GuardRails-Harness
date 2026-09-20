from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from lgh.paths import traces_dir
from lgh.schema.trace import DecisionTrace
from lgh.trace.hashing import record_hash


def iter_trace_files(directory: Path | None = None) -> list[Path]:
    root = directory or traces_dir()
    if not root.is_dir():
        return []
    return sorted(root.glob("*.jsonl"))


def iter_traces(directory: Path | None = None) -> Iterator[DecisionTrace]:
    for path in iter_trace_files(directory):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            yield DecisionTrace.model_validate(json.loads(line))


def last_record_hash(directory: Path | None = None) -> str | None:
    files = iter_trace_files(directory)
    if not files:
        return None
    last_line = None
    for line in files[-1].read_text(encoding="utf-8").splitlines():
        if line.strip():
            last_line = line
    if not last_line:
        return None
    return record_hash(json.loads(last_line))


def tail_traces(n: int = 20, directory: Path | None = None) -> list[DecisionTrace]:
    items = list(iter_traces(directory))
    return items[-n:]


def get_trace(trace_id: str, directory: Path | None = None) -> DecisionTrace | None:
    for trace in iter_traces(directory):
        if trace.trace_id == trace_id:
            return trace
    return None
