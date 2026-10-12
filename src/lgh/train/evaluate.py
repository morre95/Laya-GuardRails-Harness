"""Score Laya predictions against human labels and fit per-bucket temperatures."""

from __future__ import annotations

import math
from typing import Any

from lgh.eval.calibrate import ece
from lgh.train.data import question_target

_EPS = 1e-12
_TEMPERATURE_GRID = [step / 20.0 for step in range(1, 101)]  # 0.05 .. 5.0


def _soft_log_loss(probs: list[float], target: list[float]) -> float:
    return -sum(t * math.log(max(p, _EPS)) for p, t in zip(probs, target, strict=True))


def _predicted_distribution(answer: dict[str, Any], qdef: dict[str, Any]) -> list[float]:
    if qdef["type"] == "choice":
        return [float(answer["probabilities"][option]) for option in qdef["criteria"]]
    p = float(answer["noul"])
    return [1.0 - p, p]


def score_question(answers: list[dict[str, Any]], labels: list[Any], qdef: dict[str, Any]) -> dict[str, Any]:
    """answers: Laya's per-row answer for this question; labels: the human label per row."""
    losses, briers, confidences, correct = [], [], [], []
    options = list(qdef["criteria"]) if qdef["type"] == "choice" else ["false", "true"]
    recall = {option: {"support": 0, "correct": 0} for option in options}
    for answer, label in zip(answers, labels, strict=True):
        probs = _predicted_distribution(answer, qdef)
        target = question_target(qdef, label)
        predicted = max(range(len(probs)), key=probs.__getitem__)
        # noul: a 0.5 label counts as true, matching class_support
        actual = int(target[1] >= 0.5) if qdef["type"] == "noul" else target.index(1.0)
        losses.append(_soft_log_loss(probs, target))
        briers.append(sum((p - t) ** 2 for p, t in zip(probs, target, strict=True)))
        confidences.append(probs[predicted])
        correct.append(int(predicted == actual))
        recall[options[actual]]["support"] += 1
        recall[options[actual]]["correct"] += int(predicted == actual)
    n = len(losses)
    return {
        "n": n,
        "accuracy": sum(correct) / n,
        "log_loss": sum(losses) / n,
        "brier": sum(briers) / n,
        "ece": ece(confidences, correct),
        "recall": recall,
    }


def score_predictions(
    predictions: list[dict[str, Any]], rows: list[dict[str, Any]], questions: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """predictions[i] is Laya's `answers` dict for rows[i]."""
    return {
        key: score_question(
            [prediction[key] for prediction in predictions],
            [row["labels"][key] for row in rows],
            qdef,
        )
        for key, qdef in questions.items()
    }


def _softmax(logits: list[float], temperature: float) -> list[float]:
    scaled = [z / temperature for z in logits]
    top = max(scaled)
    exps = [math.exp(z - top) for z in scaled]
    total = sum(exps)
    return [e / total for e in exps]


def fit_bucket_temperatures(samples: list[tuple[str, list[float], list[float]]]) -> dict[str, float]:
    """samples: (temp_bucket, raw logits, target). Picks the temperature minimizing mean log loss per bucket."""
    by_bucket: dict[str, list[tuple[list[float], list[float]]]] = {}
    for bucket, logits, target in samples:
        by_bucket.setdefault(bucket, []).append((logits, target))
    fitted = {}
    for bucket, pairs in by_bucket.items():
        fitted[bucket] = min(
            _TEMPERATURE_GRID,
            key=lambda t: sum(_soft_log_loss(_softmax(logits, t), target) for logits, target in pairs),
        )
    return fitted
