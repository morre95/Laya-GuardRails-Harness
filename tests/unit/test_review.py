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
from lgh.teacher import TeacherError
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


class FakeTeacher:
    kind = "llm"
    provider = "openrouter"
    model = "x-ai/grok-4"

    def __init__(self, *, invalid: bool = False) -> None:
        self.invalid = invalid
        self.calls: list[dict] = []

    def propose(self, state: dict, questions: dict | None = None) -> dict:
        self.calls.append(state)
        if self.invalid:
            raise TeacherError("teacher returned an invalid label: handling must be one of")
        return {
            "model": self.model,
            "reason": "push leaves the machine",
            "task_alignment": "aligned",
            "destructive_risk": 0.2,
            "sensitive_resource": 0.0,
            "external_impact": 0.8,
            "reversibility": "recoverable",
            "verification_needed": 0.7,
            "handling": "verify",
        }


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
        cfg = json.loads(urlopen(base + "/api/config", timeout=2).read())
        assert cfg["propose"] is False
        queue = json.loads(urlopen(base + "/api/queue", timeout=2).read())
        assert queue["counts"]["unlabeled"] == 1
        page = urlopen(base + "/", timeout=2).read().decode("utf-8")
        assert "LGH review" in page
        assert 'id="teacher-on"' in page
        assert 'id="teacher-toggle"' in page
        assert 'id="select-visible"' in page
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
        propose = Request(
            base + "/api/propose",
            data=json.dumps({"trace_id": result.trace.trace_id}).encode(),
            method="POST",
        )
        propose.add_header("Content-Type", "application/json")
        from urllib.error import HTTPError

        with pytest.raises(HTTPError) as disabled:
            urlopen(propose, timeout=2)
        assert disabled.value.code == 400
    finally:
        httpd.shutdown()


def test_review_http_propose(tmp_path) -> None:
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError

    pipe, env = _pipe(tmp_path, command="git push origin HEAD")
    result = pipe.evaluate(env)
    store = ReviewStore(traces_dir=tmp_path / "t", data_dir=tmp_path)
    teacher = FakeTeacher()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, teacher=teacher))
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"
        cfg = json.loads(urlopen(base + "/api/config", timeout=2).read())
        assert cfg["propose"] is True
        assert cfg["model"] == "x-ai/grok-4"
        req = Request(
            base + "/api/propose",
            data=json.dumps({"trace_id": result.trace.trace_id}).encode(),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        proposed = json.loads(urlopen(req, timeout=2).read())
        assert proposed["handling"] == "verify"
        assert proposed["reason"] == "push leaves the machine"
        assert teacher.calls and teacher.calls[0]["action"]["command"] == "git push origin HEAD"
        missing = Request(
            base + "/api/propose",
            data=json.dumps({"trace_id": "missing"}).encode(),
            method="POST",
        )
        missing.add_header("Content-Type", "application/json")
        with pytest.raises(HTTPError) as exc:
            urlopen(missing, timeout=2)
        assert exc.value.code == 404
    finally:
        httpd.shutdown()


def _label_body(**extra) -> dict:
    return {
        "source": "human",
        "handling": "allow",
        "task_alignment": "aligned",
        "reversibility": "trivial",
        "destructive_risk": 0.0,
        "sensitive_resource": 0.0,
        "external_impact": 0.0,
        "verification_needed": 0.1,
        **extra,
    }


def test_review_http_bulk_labels(tmp_path) -> None:
    from http.server import ThreadingHTTPServer

    pipe, env = _pipe(tmp_path, command="echo one")
    first = pipe.evaluate(env)
    second = pipe.evaluate(make_envelope(command="echo two", goal="say hello"))
    store = ReviewStore(traces_dir=tmp_path / "t", data_dir=tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"
        body = json.dumps(
            _label_body(
                trace_ids=[first.trace.trace_id, second.trace.trace_id],
                handling="verify",
            )
        ).encode()
        req = Request(base + "/api/labels", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        saved = json.loads(urlopen(req, timeout=2).read())
        assert saved["count"] == 2
        assert {row["trace_id"] for row in saved["labels"]} == {
            first.trace.trace_id,
            second.trace.trace_id,
        }
        assert all(row["handling"] == "verify" for row in saved["labels"])
        queue = json.loads(urlopen(base + "/api/queue", timeout=2).read())
        assert queue["counts"]["labeled"] == 2
        assert queue["counts"]["unlabeled"] == 0
    finally:
        httpd.shutdown()


def test_review_http_bulk_skip(tmp_path) -> None:
    from http.server import ThreadingHTTPServer

    pipe, env = _pipe(tmp_path, command="echo one")
    first = pipe.evaluate(env)
    second = pipe.evaluate(make_envelope(command="echo two", goal="say hello"))
    store = ReviewStore(traces_dir=tmp_path / "t", data_dir=tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        base = f"http://127.0.0.1:{port}"
        req = Request(
            base + "/api/skip",
            data=json.dumps(
                {"trace_ids": [first.trace.trace_id, second.trace.trace_id]}
            ).encode(),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        skipped = json.loads(urlopen(req, timeout=2).read())
        assert skipped["count"] == 2
        queue = json.loads(urlopen(base + "/api/queue", timeout=2).read())
        assert queue["counts"]["skipped"] == 2
        assert queue["counts"]["unlabeled"] == 0
    finally:
        httpd.shutdown()


def test_send_swallows_broken_pipe(tmp_path) -> None:
    """A browser that reloads mid-teacher-call must not crash the handler thread."""
    import io

    class BrokenSocket(io.RawIOBase):
        def write(self, _data) -> int:
            raise BrokenPipeError(32, "Broken pipe")

    store = ReviewStore(traces_dir=tmp_path / "t", data_dir=tmp_path)
    Handler = make_handler(store)
    handler = Handler.__new__(Handler)
    handler.wfile = BrokenSocket()
    handler.request_version = "HTTP/1.1"
    handler.close_connection = False
    handler._headers_buffer = []
    handler.requestline = "POST /api/propose HTTP/1.1"
    handler.command = "POST"
    handler._json(200, {"ok": True})
    assert handler.close_connection is True


def test_append_labels_writes_each_trace(tmp_path) -> None:
    from lgh.eval.labels import append_labels, latest_labels

    rows = append_labels(
        [
            _label_body(trace_id="a", handling="replan"),
            _label_body(trace_id="b", handling="replan"),
        ],
        directory=tmp_path,
    )
    assert len(rows) == 2
    latest = latest_labels(tmp_path)
    assert latest["a"]["handling"] == "replan"
    assert latest["b"]["handling"] == "replan"
