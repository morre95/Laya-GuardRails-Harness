from __future__ import annotations

import math
from typing import Any

from lgh.schema.laya import (
    HandlingAssessment,
    LayaAssessment,
    ReversibilityAssessment,
    TaskAlignmentAssessment,
)

TASK_VALUES = {"aligned", "supporting", "unclear", "outside_scope"}
REVERSIBILITY_VALUES = {"trivial", "recoverable", "difficult", "irreversible"}
HANDLING_VALUES = {"allow", "verify", "replan", "escalate"}


class LayaUnavailable(Exception):
    """Raised when Laya cannot produce a complete assessment."""


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def apply_temperature(probability: float, temperature: float) -> float:
    if temperature <= 0:
        return _clip(probability)
    if abs(temperature - 1.0) < 1e-9:
        return _clip(probability)
    p = min(1 - 1e-6, max(1e-6, float(probability)))
    logit = math.log(p / (1.0 - p))
    scaled = logit / temperature
    return _clip(1.0 / (1.0 + math.exp(-scaled)))


def _choice(answers: dict[str, Any], key: str) -> tuple[str, float]:
    """Return (label, confidence) where confidence is the top-class probability.

    Laya's own ``confidence`` on ``choice`` questions is a normalized-entropy
    score (1 - H(p)/log k), which is not what the reducer thresholds and the
    ECE/Brier calibration in the spec assume. When per-option ``probabilities``
    are present we take the probability of the chosen label; the entropy score
    is only used as a fallback when the distribution is missing.
    """
    payload = answers.get(key) or {}
    value = payload.get("choice") or payload.get("value")
    if value is None:
        raise LayaUnavailable(f"missing choice for {key}")
    probs = payload.get("probabilities")
    if isinstance(probs, dict) and probs:
        top = probs.get(str(value))
        if top is None:
            top = max(float(v) for v in probs.values())
        return str(value), _clip(float(top))
    return str(value), _clip(float(payload.get("confidence", 0.0)))


def _noul(answers: dict[str, Any], key: str) -> float:
    payload = answers.get(key) or {}
    if "noul" in payload:
        return _clip(float(payload["noul"]))
    if "score" in payload:
        return _clip(float(payload["score"]))
    raise LayaUnavailable(f"missing noul for {key}")


def normalize_assessment(
    result: dict[str, Any],
    *,
    model: str,
    latency_ms: float,
    temperatures: dict[str, float] | None = None,
) -> LayaAssessment:
    answers = result.get("answers") or result
    temps = temperatures or {}
    task_value, task_conf = _choice(answers, "task_alignment")
    if task_value not in TASK_VALUES:
        raise LayaUnavailable(f"invalid task_alignment {task_value}")
    rev_value, rev_conf = _choice(answers, "reversibility")
    if rev_value not in REVERSIBILITY_VALUES:
        raise LayaUnavailable(f"invalid reversibility {rev_value}")
    handling_value, handling_conf = _choice(answers, "handling")
    if handling_value not in HANDLING_VALUES:
        raise LayaUnavailable(f"invalid handling {handling_value}")

    t_noul = temps.get("noul", 1.0)
    t_choice4 = temps.get("choice_4", temps.get("choice", 1.0))
    return LayaAssessment(
        model=model,
        latencyMs=latency_ms,
        taskAlignment=TaskAlignmentAssessment(
            value=task_value,  # type: ignore[arg-type]
            confidence=apply_temperature(task_conf, t_choice4),
        ),
        destructiveRisk=apply_temperature(_noul(answers, "destructive_risk"), t_noul),
        sensitiveResource=apply_temperature(_noul(answers, "sensitive_resource"), t_noul),
        externalImpact=apply_temperature(_noul(answers, "external_impact"), t_noul),
        reversibility=ReversibilityAssessment(
            value=rev_value,  # type: ignore[arg-type]
            confidence=apply_temperature(rev_conf, t_choice4),
        ),
        verificationNeeded=apply_temperature(_noul(answers, "verification_needed"), t_noul),
        handling=HandlingAssessment(
            value=handling_value,  # type: ignore[arg-type]
            confidence=apply_temperature(handling_conf, t_choice4),
        ),
    )
