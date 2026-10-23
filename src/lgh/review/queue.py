from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from lgh.eval.labels import latest_labels, load_review_exclusions, load_skips
from lgh.laya.client import state_payload
from lgh.laya.questions import load_questions
from lgh.review.triage import RiskScore, score_trace
from lgh.schema.trace import DecisionTrace
from lgh.trace.reader import iter_traces

Status = Literal["unlabeled", "labeled", "skipped", "no_state", "insufficient_context"]


def unique_traces(traces: list[DecisionTrace]) -> list[DecisionTrace]:
    """Keep the last record per trace_id (post-hook re-appends the same id)."""
    by_id: dict[str, DecisionTrace] = {}
    order: list[str] = []
    for trace in traces:
        if trace.trace_id not in by_id:
            order.append(trace.trace_id)
        by_id[trace.trace_id] = trace
    return [by_id[trace_id] for trace_id in order]


def _summary(trace: DecisionTrace) -> str:
    if trace.state is None:
        return "(no state — collected before review UI)"
    action = trace.state.action
    return action.command or action.target or f"{action.tool} {action.operation}"


def _status(trace: DecisionTrace, labels: dict[str, dict], skipped: set[str], excluded: dict[str, dict]) -> Status:
    if trace.trace_id in excluded:
        return "insufficient_context"
    if trace.trace_id in labels:
        return "labeled"
    if trace.trace_id in skipped:
        return "skipped"
    if trace.state is None:
        return "no_state"
    return "unlabeled"


@dataclass
class ReviewStore:
    traces_dir: Path | None = None
    data_dir: Path | None = None

    def items(self) -> list[dict[str, Any]]:
        labels = latest_labels(self.data_dir)
        skipped = load_skips(self.data_dir)
        excluded = load_review_exclusions(self.data_dir)
        rows = []
        for trace in unique_traces(list(iter_traces(self.traces_dir))):
            status = _status(trace, labels, skipped, excluded)
            risk = score_trace(trace) if trace.state is not None else RiskScore()
            rows.append(
                {
                    "traceId": trace.trace_id,
                    "timestamp": trace.timestamp,
                    "status": status,
                    "decision": str(trace.final_decision),
                    "policyDecision": str(trace.policy_decision),
                    "summary": _summary(trace),
                    "hasState": trace.state is not None,
                    "risk": risk.score,
                    "riskReasons": risk.reasons,
                }
            )
        return rows

    def risk_candidates(self, min_score: int = 1) -> list[dict[str, Any]]:
        """Skipped/unlabeled rows at or above min_score, riskiest first."""
        rows = [
            row
            for row in self.items()
            if row["status"] in ("skipped", "unlabeled") and row["risk"] >= min_score
        ]
        rows.sort(key=lambda row: (-row["risk"], row["timestamp"]))
        return rows

    def counts(self, rows: list[dict[str, Any]] | None = None) -> dict[str, int]:
        rows = rows if rows is not None else self.items()
        tally = {"unlabeled": 0, "labeled": 0, "skipped": 0, "no_state": 0,
                 "insufficient_context": 0, "total": len(rows)}
        for row in rows:
            tally[str(row["status"])] = tally.get(str(row["status"]), 0) + 1
        return tally

    def payload(self, trace_id: str) -> dict[str, Any] | None:
        traces = unique_traces(list(iter_traces(self.traces_dir)))
        trace = next((item for item in traces if item.trace_id == trace_id), None)
        if trace is None:
            return None
        labels = latest_labels(self.data_dir)
        skipped = load_skips(self.data_dir)
        excluded = load_review_exclusions(self.data_dir)
        laya = None
        if trace.laya is not None and trace.laya.assessment is not None:
            laya = trace.laya.assessment.model_dump(mode="json", by_alias=True)
        outcome = trace.outcome.model_dump(mode="json", by_alias=True) if trace.outcome else None
        return {
            "traceId": trace.trace_id,
            "timestamp": trace.timestamp,
            "status": _status(trace, labels, skipped, excluded),
            "quality": excluded.get(trace.trace_id),
            "decision": str(trace.final_decision),
            "policyDecision": str(trace.policy_decision),
            "rules": trace.rule_evaluation.matched,
            "mode": trace.mode,
            "state": state_payload(trace.state) if trace.state else None,
            "reviewContext": trace.review_context.model_dump(mode="json") if trace.review_context else None,
            "laya": laya,
            "label": labels.get(trace.trace_id),
            "outcome": outcome,
            "questions": load_questions(),
        }
