from __future__ import annotations

from typing import Any

import yaml

from lgh.resources import read_package_text

QUESTION_KEYS = (
    "task_alignment",
    "destructive_risk",
    "sensitive_resource",
    "external_impact",
    "reversibility",
    "verification_needed",
    "handling",
)


def load_questions() -> dict[str, Any]:
    data = yaml.safe_load(read_package_text("laya", "questions_v0_1.yaml")) or {}
    missing = [key for key in QUESTION_KEYS if key not in data]
    if missing:
        raise RuntimeError(f"Laya question set missing keys: {missing}")
    return data
