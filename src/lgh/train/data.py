"""Exported dataset rows → Laya training targets, splits and class support."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from lgh.schema.envelope import LayaState

VAL_FRACTION = 0.2
MIN_TRAIN_SUPPORT = 10
_REQUIRED_FIELDS = ("timestamp", "state", "questions", "labels")


class DatasetError(ValueError):
    """Raised when an exported dataset cannot be trained on."""


def load_rows(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise DatasetError(f'{path}: invalid JSON') from exc
    if not rows:
        raise DatasetError(f"{path} has no rows")
    if any(not isinstance(row, dict) for row in rows):
        raise DatasetError('each dataset row must be an object')
    questions = rows[0].get("questions")
    if not isinstance(questions, dict) or not questions:
        raise DatasetError('questions must be a nonempty mapping')
    seen = set()
    for row in rows:
        trace_id = row.get("trace_id")
        if row.get("source") == "laya":
            raise DatasetError(f"trace {trace_id} is labeled by Laya itself; never train on its own predictions")
        missing = [field for field in _REQUIRED_FIELDS if field not in row]
        if missing:
            raise DatasetError(f"trace {trace_id} is missing {missing}; re-run `lgh export-dataset`")
        if not isinstance(trace_id, str) or not trace_id or trace_id in seen:
            raise DatasetError(f'missing or duplicate trace_id: {trace_id}')
        seen.add(trace_id)
        if row.get('source') not in ('human', 'frontier', 'deterministic'):
            raise DatasetError(f'trace {trace_id}: independent label source required')
        if row.get('review_status') == 'insufficient_context':
            raise DatasetError(f'trace {trace_id}: insufficient context')
        if not isinstance(row['state'], dict) or not row['state'] or not isinstance(row['timestamp'], str) or not row['timestamp'].strip():
            raise DatasetError(f'trace {trace_id}: state and timestamp are required')
        for key in ('group_id', 'session_id'):
            if key in row and (not isinstance(row[key], str) or not row[key].strip()):
                raise DatasetError(f'trace {trace_id}: {key} must be a nonempty string')
        try:
            LayaState.model_validate(row['state'])
        except ValidationError as exc:
            raise DatasetError(f'trace {trace_id}: invalid LayaState') from exc
        if row["questions"] != questions:
            raise DatasetError(f"trace {trace_id} uses a different question set than the rest of the dataset")
        if not isinstance(row['labels'], dict) or set(row['labels']) != set(questions):
            raise DatasetError(f'trace {trace_id}: labels must cover exactly the questions')
        for key, qdef in questions.items():
            if not isinstance(qdef, dict) or not isinstance(qdef.get('instructions'), str) or not qdef['instructions'].strip():
                raise DatasetError(f'trace {trace_id}: invalid instructions for {key}')
            question_target(qdef, row['labels'][key])
    return rows


def question_target(qdef: dict[str, Any], label: Any) -> list[float]:
    """Target distribution in the option order Laya renders (choice: criteria order; noul: [false, true])."""
    if not isinstance(qdef, dict) or qdef.get('type') not in ('choice', 'noul'):
        raise DatasetError('unsupported or malformed question definition')
    if qdef["type"] == "choice":
        if not isinstance(qdef.get('criteria'), dict) or len(qdef['criteria']) < 2:
            raise DatasetError('choice criteria must contain at least two options')
        options = list(qdef["criteria"])
        if label not in options:
            raise DatasetError(f"label {label!r} is not one of {options}")
        return [1.0 if option == label else 0.0 for option in options]
    if qdef["type"] == "noul":
        try:
            p = float(label)
        except (TypeError, ValueError) as exc:
            raise DatasetError(f'invalid label probability: {label!r}') from exc
        if not math.isfinite(p) or not 0 <= p <= 1:
            raise DatasetError(f'invalid label probability: {label!r}')
        return [1.0 - p, p]
    raise DatasetError(f"unsupported question type {qdef['type']!r}")


def chronological_split(
    rows: list[dict[str, Any]], val_fraction: float = VAL_FRACTION
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Newest rows become validation. This alone does not prevent session leakage."""
    if not 0 < val_fraction < 1:
        raise DatasetError('validation fraction must be between zero and one')
    ordered = sorted(rows, key=lambda row: row["timestamp"])
    n_val = max(1, round(len(ordered) * val_fraction))
    if n_val >= len(ordered):
        raise DatasetError("need at least 2 rows to split into train and validation")
    return ordered[:-n_val], ordered[-n_val:]


def assert_disjoint(partitions: dict[str, list[dict[str, Any]]]) -> None:
    """Reject known leakage; near-duplicates without group/session IDs remain unknown."""
    owners: dict[tuple[str, str], str] = {}
    questions = None
    for name, rows in partitions.items():
        if not rows:
            raise DatasetError(f'{name} is empty')
        for row in rows:
            if questions is None:
                questions = row['questions']
            if row['questions'] != questions:
                raise DatasetError(f'{name}: inconsistent question set')
            identities = {'state': json.dumps(row['state'], sort_keys=True)}
            identities.update({key: str(row[key]) for key in ('trace_id', 'group_id', 'session_id') if row.get(key)})
            for kind, value in identities.items():
                previous = owners.setdefault((kind, value), name)
                if previous != name:
                    raise DatasetError(f'{kind} overlap between {previous} and {name}: {row.get("trace_id")}')


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
