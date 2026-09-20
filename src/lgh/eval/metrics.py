from __future__ import annotations

from collections import Counter
from statistics import quantiles

from lgh.schema.decision import GuardrailDecision
from lgh.schema.trace import DecisionTrace


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    try:
        qs = quantiles(sorted(values), n=100, method="inclusive")
        idx = min(99, max(1, int(p))) - 1
        return float(qs[idx])
    except Exception:
        ordered = sorted(values)
        k = int(round((p / 100.0) * (len(ordered) - 1)))
        return float(ordered[k])


def summarize_eval(
    *,
    names: list[str],
    decisions: list[GuardrailDecision],
    forbidden_hits: int,
    false_allows: int,
    false_blocks: int,
    traces: list[DecisionTrace] | None = None,
) -> dict:
    total = max(1, len(decisions))
    counts = Counter(str(d) for d in decisions)
    traces = traces or []
    laya_lat = [t.laya.assessment.latency_ms for t in traces if t.laya is not None]
    return {
        "n": len(decisions),
        "false_allow_rate": false_allows / total,
        "false_block_rate": false_blocks / total,
        "forbidden_hits": forbidden_hits,
        "decisions": dict(counts),
        "rule_resolution_rate": sum(1 for t in traces if t.rule_evaluation.disposition != "PASS") / max(1, len(traces)),
        "laya_resolution_rate": sum(1 for t in traces if t.laya is not None) / max(1, len(traces)),
        "frontier_escalation_rate": sum(1 for t in traces if t.frontier is not None) / max(1, len(traces)),
        "human_escalation_rate": sum(1 for t in traces if t.human and t.human.requested) / max(1, len(traces)),
        "laya_latency_p50": percentile(laya_lat, 50),
        "laya_latency_p95": percentile(laya_lat, 95),
        "repeated_action_rate": 0.0,
    }
