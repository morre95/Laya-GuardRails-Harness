"""Exported dataset rows → Laya training targets, splits and class support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VAL_FRACTION = 0.2
MIN_TRAIN_SUPPORT = 10
_REQUIRED_FIELDS = ("timestamp", "state", "questions", "labels")


class DatasetError(ValueError):
    """Raised when an exported dataset cannot be trained on."""


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise DatasetError(f"{path} has no rows")
    questions = rows[0].get("questions")
    for row in rows:
        trace_id = row.get("trace_id")
        if row.get("source") == "laya":
            raise DatasetError(f"trace {trace_id} is labeled by Laya itself; never train on its own predictions")
        missing = [field for field in _REQUIRED_FIELDS if field not in row]
        if missing:
            raise DatasetError(f"trace {trace_id} is missing {missing}; re-run `lgh export-dataset`")
        if row["questions"] != questions:
            raise DatasetError(f"trace {trace_id} uses a different question set than the rest of the dataset")
    return rows


def question_target(qdef: dict[str, Any], label: Any) -> list[float]:
    """Target distribution in the option order Laya renders (choice: criteria order; noul: [false, true])."""
    if qdef["type"] == "choice":
        options = list(qdef["criteria"])
        if label not in options:
            raise DatasetError(f"label {label!r} is not one of {options}")
        return [1.0 if option == label else 0.0 for option in options]
    if qdef["type"] == "noul":
        p = float(label)
        return [1.0 - p, p]
    raise DatasetError(f"unsupported question type {qdef['type']!r}")


def chronological_split(
    rows: list[dict[str, Any]], val_fraction: float = VAL_FRACTION
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Newest rows become validation, so near-duplicate commands from one session do not leak across."""
    ordered = sorted(rows, key=lambda row: row["timestamp"])
    n_val = max(1, round(len(ordered) * val_fraction))
    if n_val >= len(ordered):
        raise DatasetError("need at least 2 rows to split into train and validation")
    return ordered[:-n_val], ordered[-n_val:]


def class_support(rows: list[dict[str, Any]], questions: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Examples per class. noul labels count as true when >= 0.5."""
    support: dict[str, dict[str, int]] = {}
    for key, qdef in questions.items():
        if qdef["type"] == "choice":
            counts = {option: 0 for option in qdef["criteria"]}
            for row in rows:
                counts[row["labels"][key]] += 1
        else:
            counts = {"false": 0, "true": 0}
            for row in rows:
                counts["true" if float(row["labels"][key]) >= 0.5 else "false"] += 1
        support[key] = counts
    return support


def support_warnings(train: dict[str, dict[str, int]], val: dict[str, dict[str, int]]) -> list[str]:
    warnings = []
    for key, counts in train.items():
        for cls, n in counts.items():
            if n < MIN_TRAIN_SUPPORT:
                warnings.append(f"{key}={cls}: {n} training examples (< {MIN_TRAIN_SUPPORT}); expect it not to be learned")
            if val[key][cls] == 0:
                warnings.append(f"{key}={cls}: no validation examples; its accuracy cannot be measured")
    return warnings
