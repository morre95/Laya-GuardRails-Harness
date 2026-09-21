from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lgh.paths import user_data_dir

SOURCES = ("human", "frontier", "deterministic")
HANDLING_VALUES = ("allow", "verify", "replan", "escalate")
ALIGNMENT_VALUES = ("aligned", "supporting", "unclear", "outside_scope")
REVERSIBILITY_VALUES = ("trivial", "recoverable", "difficult", "irreversible")


class LabelError(ValueError):
    """Raised when a human label is incomplete or invalid."""


def labels_path(directory: Path | None = None) -> Path:
    path = (directory or user_data_dir()) / "labels.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def skips_path(directory: Path | None = None) -> Path:
    path = (directory or user_data_dir()) / "review-skips.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _noul(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LabelError(f"noul value must be a number, got {value!r}") from exc
    if number < 0.0 or number > 1.0:
        raise LabelError(f"noul value must be in [0, 1], got {number}")
    return number


def normalize_label(record: dict[str, Any]) -> dict[str, Any]:
    trace_id = str(record.get("trace_id") or "").strip()
    if not trace_id:
        raise LabelError("trace_id is required")
    source = record.get("source")
    if source not in SOURCES:
        raise LabelError(f"source must be one of {SOURCES}")
    handling = record.get("handling")
    if handling not in HANDLING_VALUES:
        raise LabelError(f"handling must be one of {HANDLING_VALUES}")
    alignment = record.get("task_alignment")
    if alignment not in ALIGNMENT_VALUES:
        raise LabelError(f"task_alignment must be one of {ALIGNMENT_VALUES}")
    reversibility = record.get("reversibility")
    if reversibility not in REVERSIBILITY_VALUES:
        raise LabelError(f"reversibility must be one of {REVERSIBILITY_VALUES}")
    destructive = _noul(record.get("destructive_risk"))
    sensitive = _noul(record.get("sensitive_resource"))
    external = _noul(record.get("external_impact"))
    verification = _noul(record.get("verification_needed"))
    missing = [
        name
        for name, value in (
            ("destructive_risk", destructive),
            ("sensitive_resource", sensitive),
            ("external_impact", external),
            ("verification_needed", verification),
        )
        if value is None
    ]
    if missing:
        raise LabelError("missing noul labels: " + ", ".join(missing))
    return {
        "trace_id": trace_id,
        "source": source,
        "task_alignment": alignment,
        "destructive_risk": destructive,
        "sensitive_resource": sensitive,
        "external_impact": external,
        "reversibility": reversibility,
        "verification_needed": verification,
        "handling": handling,
        "outcome": record.get("outcome") or {"successful": None},
    }


def append_label(record: dict, directory: Path | None = None) -> dict[str, Any]:
    normalized = normalize_label(record)
    path = labels_path(directory)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized) + "\n")
    return normalized


def load_labels(directory: Path | None = None) -> list[dict]:
    path = labels_path(directory)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def latest_labels(directory: Path | None = None) -> dict[str, dict]:
    """Last label per trace_id wins (the JSONL is append-only)."""
    by_id: dict[str, dict] = {}
    for row in load_labels(directory):
        trace_id = row.get("trace_id")
        if trace_id and row.get("source") != "laya":
            by_id[str(trace_id)] = row
    return by_id


def load_skips(directory: Path | None = None) -> set[str]:
    path = skips_path(directory)
    if not path.is_file():
        return set()
    raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    if not isinstance(raw, list):
        return set()
    return {str(item) for item in raw}


def save_skips(skipped: set[str], directory: Path | None = None) -> None:
    path = skips_path(directory)
    path.write_text(json.dumps(sorted(skipped)), encoding="utf-8")
