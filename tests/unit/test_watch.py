import json

from lgh.schema.trace import DecisionTrace
from lgh.trace.watch import follow_traces, format_trace, read_new_records

RECORD = {
    "traceId": "t1",
    "timestamp": "2026-09-20T19:01:16.419Z",
    "envelopeHash": "h1",
    "ruleEvaluation": {"matched": ["R025"], "disposition": "HUMAN"},
    "policyDecision": "HUMAN_APPROVAL",
    "finalDecision": "HUMAN_APPROVAL",
    "mode": "shadow",
}


def _write(path, *records) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def test_read_new_records_returns_only_appended(tmp_path) -> None:
    path = tmp_path / "2026-09-20.jsonl"
    _write(path, RECORD)
    first, offset = read_new_records(path, 0)
    assert [item.trace_id for item in first] == ["t1"]

    _write(path, {**RECORD, "traceId": "t2"})
    second, offset = read_new_records(path, offset)
    assert [item.trace_id for item in second] == ["t2"]
    assert read_new_records(path, offset) == ([], offset)


def test_read_new_records_leaves_partial_line(tmp_path) -> None:
    path = tmp_path / "2026-09-20.jsonl"
    path.write_text('{"traceId": "t1"', encoding="utf-8")
    assert read_new_records(path, 0) == ([], 0)


def test_read_new_records_restarts_after_truncation(tmp_path) -> None:
    path = tmp_path / "2026-09-20.jsonl"
    _write(path, RECORD, {**RECORD, "traceId": "t2"})
    _, offset = read_new_records(path, 0)
    path.write_text(json.dumps({**RECORD, "traceId": "t9"}) + "\n", encoding="utf-8")
    records, _ = read_new_records(path, offset)
    assert [item.trace_id for item in records] == ["t9"]


def test_follow_traces_yields_backlog_then_new_records(tmp_path) -> None:
    path = tmp_path / "2026-09-20.jsonl"
    _write(path, RECORD)
    stream = follow_traces(tmp_path, backlog=5, poll_seconds=0.01)
    assert next(stream).trace_id == "t1"
    _write(path, {**RECORD, "traceId": "t2"})
    assert next(stream).trace_id == "t2"
    stream.close()


def test_format_trace_names_the_matched_rule() -> None:
    line = format_trace(DecisionTrace.model_validate(RECORD), color=False)
    assert "HUMAN_APPROVAL" in line
    assert "R025 git push --force" in line


def test_format_trace_shows_escalation_path() -> None:
    record = {**RECORD, "policyDecision": "FRONTIER_REVIEW"}
    line = format_trace(DecisionTrace.model_validate(record), color=False)
    assert "FRONTIER_REVIEW→HUMAN_APPROVAL" in line


def test_format_trace_renders_repeated_id_as_outcome() -> None:
    first = DecisionTrace.model_validate(RECORD)
    second = DecisionTrace.model_validate({**RECORD, "outcome": {"executed": True, "exitCode": 0}})
    line = format_trace(second, previous=first, color=False)
    assert "↳ executed exit=0" in line
    assert "R025" not in line
