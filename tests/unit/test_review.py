from __future__ import annotations

import json
from threading import Thread
from urllib.request import Request, urlopen

from lgh.config.models import GuardrailConfig
from lgh.eval.labels import LabelError, append_label, normalize_label
from lgh.frontier.stub import StubReviewer
from lgh.laya.client import FakeLayaClient
from lgh.pipeline import Pipeline
from lgh.review.queue import ReviewStore, unique_traces
from lgh.review.server import make_handler
from lgh.schema.trace import DecisionTrace
from lgh.session.store import SessionStore
from lgh.trace.writer import TraceWriter
from tests.helpers import make_envelope
from tests.unit.test_pipeline import _assess
import pytest


def _pipe(tmp_path, command: str = "echo hi", goal: str = "say hello"):
    return Pipeline(
        GuardrailConfig(),
        laya=FakeLayaClient(_assess()),
        reviewer=StubReviewer(unavailable=True),
        sessions=SessionStore(tmp_path / "s"),
        traces=TraceWriter(tmp_path / "t"),
    ), make_envelope(command=command, goal=goal)


def test_unique_traces_keeps_last() -> None:
    first = DecisionTrace.model_validate(
        {
            "traceId": "a",
            "timestamp": "2026-01-01T00:00:00Z",
            "envelopeHash": "h",
            "ruleEvaluation": {"matched": [], "disposition": "PASS"},
            "policyDecision": "ALLOW",
            "finalDecision": "ALLOW",
        }
    )
    second = first.model_copy(update={"mode": "enforce"})
    out = unique_traces([first, second])
    assert len(out) == 1
    assert out[0].mode == "enforce"


def test_normalize_label_requires_seven_questions() -> None:
    with pytest.raises(LabelError):
        normalize_label({"trace_id": "x", "source": "human", "handling": "allow"})
    row = normalize_label(
        {
            "trace_id": "x",
            "source": "human",
            "handling": "verify",
            "task_alignment": "aligned",
            "reversibility": "trivial",
            "destructive_risk": True,
            "sensitive_resource": 0.0,
            "external_impact": 0.3,
            "verification_needed": 1,
        }
    )
    assert row["destructive_risk"] == 1.0
    assert row["sensitive_resource"] == 0.0


def test_review_queue_statuses(tmp_path) -> None:
    pipe, env = _pipe(tmp_path, command="uv add laya")
    result = pipe.evaluate(env)
    store = ReviewStore(traces_dir=tmp_path / "t", data_dir=tmp_path)
    unlabeled = [row for row in store.items() if row["status"] == "unlabeled"]
    assert unlabeled and unlabeled[0]["summary"] == "uv add laya"
    append_label(
        {
            "trace_id": result.trace.trace_id,
            "source": "human",
            "handling": "verify",
            "task_alignment": "supporting",
            "reversibility": "recoverable",
            "destructive_risk": 0.1,
            "sensitive_resource": 0.0,
            "external_impact": 0.0,
            "verification_needed": 0.9,
        },
        directory=tmp_path,
    )
    labeled = store.items()
    assert labeled[0]["status"] == "labeled"
    payload = store.payload(result.trace.trace_id)
    assert payload is not None
    assert payload["state"]["action"]["command"] == "uv add laya"
    assert payload["label"]["handling"] == "verify"


def test_review_http_roundtrip(tmp_path) -> None:
    from http.server import ThreadingHTTPServer

    pipe, env = _pipe(tmp_path, command="git push origin HEAD")
    result = pipe.evaluate(env)
    store = ReviewStore(traces_dir=tmp_path / "t", data_dir=tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"
        queue = json.loads(urlopen(base + "/api/queue", timeout=2).read())
        assert queue["counts"]["unlabeled"] == 1
        page = urlopen(base + "/", timeout=2).read().decode("utf-8")
        assert "LGH review" in page
        body = json.dumps(
            {
                "trace_id": result.trace.trace_id,
                "source": "human",
                "handling": "replan",
                "task_alignment": "outside_scope",
                "reversibility": "difficult",
                "destructive_risk": 0.4,
                "sensitive_resource": 0.1,
                "external_impact": 0.8,
                "verification_needed": 0.7,
            }
        ).encode()
        req = Request(base + "/api/labels", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        saved = json.loads(urlopen(req, timeout=2).read())
        assert saved["label"]["handling"] == "replan"
        queue = json.loads(urlopen(base + "/api/queue", timeout=2).read())
        assert queue["counts"]["labeled"] == 1
        assert queue["counts"]["unlabeled"] == 0
    finally:
        httpd.shutdown()
