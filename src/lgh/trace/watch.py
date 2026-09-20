"""Follow the trace log while hooks append to it."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from lgh.paths import traces_dir
from lgh.rules.engine import rule_descriptions
from lgh.schema.decision import GuardrailDecision
from lgh.schema.trace import DecisionTrace, Outcome
from lgh.trace.reader import iter_trace_files, tail_traces

POLL_SECONDS = 0.25

DECISION_COLORS: dict[GuardrailDecision, str] = {
    GuardrailDecision.ALLOW: "32",
    GuardrailDecision.ALLOW_WITH_VERIFICATION: "36",
    GuardrailDecision.REPLAN: "33",
    GuardrailDecision.FRONTIER_REVIEW: "33",
    GuardrailDecision.HUMAN_APPROVAL: "35",
    GuardrailDecision.BLOCK: "31",
}

_DECISION_WIDTH = max(len(str(item)) for item in GuardrailDecision)


def read_new_records(path: Path, offset: int) -> tuple[list[DecisionTrace], int]:
    """Records appended after ``offset`` bytes, plus the offset to resume from.

    A trailing partial line stays unconsumed so the next poll reads it whole.
    """
    size = path.stat().st_size
    if size < offset:
        offset = 0
    if size == offset:
        return [], offset
    with path.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read(size - offset)
    cut = chunk.rfind(b"\n")
    if cut == -1:
        return [], offset
    records = [
        DecisionTrace.model_validate(json.loads(line))
        for line in chunk[: cut + 1].decode("utf-8").splitlines()
        if line.strip()
    ]
    return records, offset + cut + 1


def follow_traces(
    directory: Path | None = None,
    *,
    backlog: int = 0,
    poll_seconds: float = POLL_SECONDS,
) -> Iterator[DecisionTrace]:
    """Yield the last ``backlog`` records, then every record as it is written."""
    root = directory or traces_dir()
    current: Path | None = None
    offset = 0
    files = iter_trace_files(root)
    if files:
        current = files[-1]
        offset = current.stat().st_size
    if backlog:
        yield from tail_traces(backlog, root)
    while True:
        files = iter_trace_files(root)
        newest = files[-1] if files else None
        if newest is not None and newest != current:
            current = newest
            offset = 0
        if current is not None and current.is_file():
            records, offset = read_new_records(current, offset)
            yield from records
        time.sleep(poll_seconds)


def _paint(text: str, code: str | None, color: bool) -> str:
    if not color or code is None:
        return text
    return f"\033[{code}m{text}\033[0m"


def _local_time(timestamp: str) -> str:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return timestamp[11:19] or timestamp
    return parsed.astimezone().strftime("%H:%M:%S")


def _rules_text(matched: list[str]) -> str:
    if not matched:
        return "no rule match"
    descriptions = rule_descriptions()
    return " · ".join(f"{item} {descriptions[item]}" if item in descriptions else item for item in matched)


def _outcome_text(outcome: Outcome) -> str:
    state = "executed" if outcome.executed else "not executed"
    if outcome.exit_code is None:
        return state
    return f"{state} exit={outcome.exit_code}"


def format_trace(
    trace: DecisionTrace,
    *,
    previous: DecisionTrace | None = None,
    color: bool = True,
) -> str:
    """One display line for a trace record.

    The post hook re-appends the pending decision once the tool has run, so a
    record that repeats the previous trace id is rendered as its outcome.
    """
    stamp = _paint(_local_time(trace.timestamp), "90", color)
    if previous is not None and previous.trace_id == trace.trace_id and trace.outcome is not None:
        return f"{stamp}  {'':7}  {'↳ ' + _outcome_text(trace.outcome):{_DECISION_WIDTH}}"
    decision = str(trace.final_decision)
    if trace.policy_decision != trace.final_decision:
        decision = f"{trace.policy_decision}→{trace.final_decision}"
    parts = [
        stamp,
        f"{trace.mode:7}",
        _paint(f"{decision:{_DECISION_WIDTH}}", DECISION_COLORS.get(trace.final_decision), color),
        _rules_text(trace.rule_evaluation.matched),
    ]
    if trace.laya is not None:
        handling = trace.laya.assessment.handling
        parts.append(_paint(f"laya={handling.value} {handling.confidence:.2f}", "90", color))
    if trace.outcome is not None:
        parts.append(_paint(_outcome_text(trace.outcome), "90", color))
    if trace.error:
        parts.append(_paint(f"error={trace.error[:60]}", "31", color))
    return "  ".join(parts)
