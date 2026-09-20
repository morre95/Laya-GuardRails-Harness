from __future__ import annotations

import json
from pathlib import Path

from lgh.paths import user_data_dir


def labels_path() -> Path:
    path = user_data_dir() / "labels.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_label(record: dict) -> None:
    path = labels_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def load_labels() -> list[dict]:
    path = labels_path()
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
