from __future__ import annotations

import json
from pathlib import Path

from lgh.laya.questions import load_questions
from lgh.schema.trace import DecisionTrace
from lgh.state.builder import build_laya_state
from lgh.config.models import GuardrailConfig
from lgh.schema.envelope import ActionEnvelope


def export_dataset(
    traces: list[DecisionTrace],
    labels: list[dict],
    envelopes: dict[str, ActionEnvelope] | None = None,
    path: Path | None = None,
) -> list[dict]:
    labeled = {item["trace_id"]: item for item in labels}
    questions = load_questions()
    rows: list[dict] = []
    for trace in traces:
        lab = labeled.get(trace.trace_id)
        if not lab:
            continue
        if lab.get("source") == "laya":
            continue
        envelope = (envelopes or {}).get(trace.trace_id)
        state = None
        if envelope is not None:
            state = build_laya_state(envelope, GuardrailConfig()).model_dump(mode="json")
        rows.append(
            {
                "state": state or {"goal": "", "environment": "", "action": ""},
                "questions": questions,
                "labels": {
                    "task_alignment": lab.get("task_alignment"),
                    "destructive_risk": lab.get("destructive_risk"),
                    "verification_needed": lab.get("verification_needed"),
                    "handling": lab.get("handling"),
                },
                "source": lab.get("source"),
                "outcome": lab.get("outcome") or {"successful": None},
            }
        )
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    return rows
