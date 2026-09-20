from __future__ import annotations

import math
from collections import defaultdict

from lgh.schema.trace import DecisionTrace


def _ece(probs: list[float], labels: list[int], bins: int = 10) -> float:
    if not probs:
        return 0.0
    total = 0.0
    n = len(probs)
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        idx = [j for j, p in enumerate(probs) if (p > lo or i == 0) and p <= hi]
        if i == 0:
            idx = [j for j, p in enumerate(probs) if lo <= p <= hi]
        if not idx:
            continue
        acc = sum(labels[j] for j in idx) / len(idx)
        conf = sum(probs[j] for j in idx) / len(idx)
        total += (len(idx) / n) * abs(acc - conf)
    return total


def _brier(probs: list[float], labels: list[int]) -> float:
    if not probs:
        return 0.0
    return sum((p - y) ** 2 for p, y in zip(probs, labels, strict=False)) / len(probs)


def fit_temperature(probs: list[float], labels: list[int]) -> float:
    best_t = 1.0
    best = float("inf")
    for step in range(1, 51):
        t = step / 10.0
        scaled = [_scale(p, t) for p in probs]
        score = _brier(scaled, labels)
        if score < best:
            best = score
            best_t = t
    return best_t


def _scale(p: float, t: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    logit = math.log(p / (1 - p))
    return 1 / (1 + math.exp(-logit / t))


def calibrate_from_traces(traces: list[DecisionTrace], labels: list[dict]) -> dict:
    by_key: dict[str, tuple[list[float], list[int]]] = defaultdict(lambda: ([], []))
    labeled = {item["trace_id"]: item for item in labels}
    for trace in traces:
        lab = labeled.get(trace.trace_id)
        if not lab or trace.laya is None:
            continue
        a = trace.laya.assessment
        mapping = {
            "noul_destructive": (a.destructive_risk, int(bool(lab.get("destructive_risk")))),
            "noul_sensitive": (a.sensitive_resource, int(bool(lab.get("sensitive_resource")))),
            "noul_external": (a.external_impact, int(bool(lab.get("external_impact")))),
            "noul_verify": (a.verification_needed, int(bool(lab.get("verification_needed")))),
            "choice_4_handling": (
                a.handling.confidence,
                int(a.handling.value == lab.get("handling")),
            ),
        }
        for key, (prob, y) in mapping.items():
            by_key[key][0].append(prob)
            by_key[key][1].append(y)
    report = {}
    temperatures: dict[str, float] = {}
    for key, (probs, ys) in by_key.items():
        report[key] = {
            "ece": _ece(probs, ys),
            "brier": _brier(probs, ys),
            "n": len(probs),
        }
        kind = key.split("_", 1)[0]
        temperatures[kind if kind != "choice" else "choice_4"] = fit_temperature(probs, ys)
    return {"report": report, "temperatures": temperatures}
