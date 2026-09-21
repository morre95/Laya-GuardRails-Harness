from __future__ import annotations

import json
from pathlib import Path

from lgh.config.models import GuardrailConfig
from lgh.laya.questions import load_questions
from lgh.schema.envelope import ActionEnvelope
from lgh.schema.trace import DecisionTrace
from lgh.state.builder import build_laya_state


def _state_payload(
    trace: DecisionTrace,
    envelopes: dict[str, ActionEnvelope] | None,
) -> dict | None:
    if trace.state is not None:
        return trace.state.model_dump(mode="json")
    envelope = (envelopes or {}).get(trace.trace_id)
    if envelope is None:
        return None
    return build_laya_state(envelope, GuardrailConfig()).model_dump(mode="json")


def export_dataset(
    traces: list[DecisionTrace],
    labels: list[dict],
    envelopes: dict[str, ActionEnvelope] | None = None,
    path: Path | None = None,
) -> list[dict]:
    labeled = {item["trace_id"]: item for item in labels}
    questions = load_questions()
    rows: list[dict] = []
    seen: set[str] = set()
    for trace in reversed(traces):
        if trace.trace_id in seen:
            continue
        seen.add(trace.trace_id)
        lab = labeled.get(trace.trace_id)
        if not lab:
            continue
        if lab.get("source") == "laya":
            continue
        state = _state_payload(trace, envelopes)
        if state is None:
            continue
        rows.append(
            {
                "state": state,
                "questions": questions,
                "labels": {
                    "task_alignment": lab.get("task_alignment"),
                    "destructive_risk": lab.get("destructive_risk"),
                    "sensitive_resource": lab.get("sensitive_resource"),
                    "external_impact": lab.get("external_impact"),
                    "reversibility": lab.get("reversibility"),
                    "verification_needed": lab.get("verification_needed"),
                    "handling": lab.get("handling"),
                },
                "source": lab.get("source"),
                "outcome": lab.get("outcome") or {"successful": None},
            }
        )
    rows.reverse()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    return rows
