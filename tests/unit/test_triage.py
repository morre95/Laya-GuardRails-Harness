from __future__ import annotations

import json

from lgh.eval.labels import append_label, save_skips
from lgh.review.queue import ReviewStore
from lgh.review.triage import score_trace
from lgh.schema.trace import DecisionTrace


def _trace(trace_id: str, command: str, disposition: str = "PASS", matched: list[str] | None = None) -> dict:
    return {
        "traceId": trace_id,
        "timestamp": f"2026-09-30T00:00:0{len(trace_id) % 10}Z",
        "envelopeHash": "h",
        "ruleEvaluation": {"matched": matched or [], "disposition": disposition},
        "state": {
            "goal": "fix the bug",
            "repo": {"branch": "main"},
            "environment": "development",
            "action": {"tool": "shell", "operation": "execute", "command": command},
        },
        "policyDecision": "ALLOW",
        "finalDecision": "ALLOW",
    }


def _write_traces(directory, rows: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "2026-09-30.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")


def _score(command: str, **kwargs) -> tuple[int, list[str]]:
    risk = score_trace(DecisionTrace.model_validate(_trace("t", command, **kwargs)))
    return risk.score, risk.reasons


def test_destructive_command_scores_pattern() -> None:
    score, reasons = _score("docker compose exec db psql -c 'DROP TABLE users'")
    assert "pattern:destructive" in reasons
    assert "pattern:sensitive" in reasons
    assert score == 6


def test_block_rule_outranks_human_rule() -> None:
    block, _ = _score("ls", disposition="BLOCK", matched=["R012"])
    human, _ = _score("ls", disposition="HUMAN", matched=["R040"])
    assert block > human > 0


def test_env_example_is_not_sensitive() -> None:
    assert _score("cat .env.example") == (0, [])
    assert "pattern:sensitive" in _score("cat .env")[1]


def test_risk_candidates_exclude_labeled_and_order_by_score(tmp_path) -> None:
    traces_dir, data_dir = tmp_path / "t", tmp_path / "d"
    _write_traces(
        traces_dir,
        [
            _trace("safe", "ls -la"),
            _trace("push", "git push origin main"),
            _trace("wipe", "git push --force && rm -rf build"),
            _trace("done", "rm -rf dist"),
        ],
    )
    append_label(
        {
            "trace_id": "done",
            "source": "human",
            "handling": "verify",
            "task_alignment": "aligned",
            "reversibility": "recoverable",
            "destructive_risk": 0.5,
            "sensitive_resource": 0,
            "external_impact": 0,
            "verification_needed": 0.8,
        },
        directory=data_dir,
    )
    save_skips({"push"}, directory=data_dir)

    store = ReviewStore(traces_dir=traces_dir, data_dir=data_dir)

    ranked = store.risk_candidates()

    assert [(row["traceId"], row["status"]) for row in ranked] == [("wipe", "unlabeled"), ("push", "skipped")]


def test_queue_rows_carry_risk(tmp_path) -> None:
    traces_dir = tmp_path / "t"
    _write_traces(traces_dir, [_trace("wipe", "rm -rf build")])

    rows = ReviewStore(traces_dir=traces_dir, data_dir=tmp_path / "d").items()

    assert rows[0]["risk"] == 3
    assert rows[0]["riskReasons"] == ["pattern:destructive"]
