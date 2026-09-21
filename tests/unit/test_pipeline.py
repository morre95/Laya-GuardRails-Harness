from lgh.config.models import GuardrailConfig
from lgh.frontier.stub import StubReviewer
from lgh.human.prompt import human_prompt
from lgh.laya.client import FakeLayaClient
from lgh.pipeline import Pipeline, effective_mode
from lgh.schema.decision import GuardrailDecision, Mode
from lgh.schema.frontier import ReviewResponse
from lgh.schema.laya import HandlingAssessment, LayaAssessment, ReversibilityAssessment, TaskAlignmentAssessment
from lgh.session.antiloop import action_key, apply_antiloop
from lgh.session.store import SessionStore
from lgh.trace.writer import TraceWriter
from tests.helpers import make_envelope


def _assess(**kwargs) -> LayaAssessment:
    return LayaAssessment(
        model="fake",
        latencyMs=1,
        taskAlignment=TaskAlignmentAssessment(value=kwargs.get("task", "aligned"), confidence=0.9),
        destructiveRisk=kwargs.get("d", 0.1),
        sensitiveResource=0.1,
        externalImpact=0.1,
        reversibility=ReversibilityAssessment(value="trivial", confidence=0.9),
        verificationNeeded=kwargs.get("v", 0.1),
        handling=HandlingAssessment(value=kwargs.get("h", "allow"), confidence=kwargs.get("c", 0.9)),
    )


def test_shadow_never_blocks_trace_still_records(tmp_path) -> None:
    cfg = GuardrailConfig(mode=Mode.SHADOW)
    pipe = Pipeline(
        cfg,
        laya=FakeLayaClient(_assess()),
        reviewer=StubReviewer(unavailable=True),
        sessions=SessionStore(tmp_path / "s"),
        traces=TraceWriter(tmp_path / "t"),
    )
    result = pipe.evaluate(make_envelope(command="rm -rf /"))
    assert result.decision == GuardrailDecision.BLOCK
    assert result.mode == Mode.SHADOW
    assert result.trace.final_decision == GuardrailDecision.BLOCK
    assert result.trace.state is not None
    assert result.trace.state.action.command == "rm -rf /"
    assert result.trace.state.goal == "Do a thing"


def test_human_prompt_is_concrete() -> None:
    env = make_envelope(command="git push --force origin main", goal="Fix OAuth")
    from lgh.rules.engine import evaluate_rules

    rules = evaluate_rules(env, GuardrailConfig())
    text = human_prompt(env, rules)
    assert "git push --force origin main" in text
    assert "Approve this exact action?" in text
    assert "Always allow" not in text


def test_antiloop_escalates(tmp_path) -> None:
    store = SessionStore(tmp_path)
    key = action_key("npm run db:reset", None, "shell", "execute")
    d = GuardrailDecision.ALLOW_WITH_VERIFICATION
    for _ in range(3):
        d = apply_antiloop(session_id="s", store=store, key=key, decision=GuardrailDecision.ALLOW_WITH_VERIFICATION)
    assert d in {GuardrailDecision.FRONTIER_REVIEW, GuardrailDecision.HUMAN_APPROVAL}


def test_shadow_skips_frontier_and_keeps_policy_decision(tmp_path) -> None:
    cfg = GuardrailConfig(mode=Mode.SHADOW)
    reviewer = StubReviewer(unavailable=True)
    pipe = Pipeline(
        cfg,
        laya=FakeLayaClient(_assess(h="escalate", c=0.95)),
        reviewer=reviewer,
        sessions=SessionStore(tmp_path / "s"),
        traces=TraceWriter(tmp_path / "t"),
    )
    result = pipe.evaluate(make_envelope(command="echo hi"))
    assert result.policy_decision == GuardrailDecision.FRONTIER_REVIEW
    assert result.decision == GuardrailDecision.FRONTIER_REVIEW
    assert reviewer.calls == []
    assert "skipped" in (result.error or "")


def test_shadow_runs_frontier_when_opted_in(tmp_path) -> None:
    cfg = GuardrailConfig(mode=Mode.SHADOW)
    cfg.review.run_in_shadow = True
    reviewer = StubReviewer(unavailable=True)
    pipe = Pipeline(
        cfg,
        laya=FakeLayaClient(_assess(h="escalate", c=0.95)),
        reviewer=reviewer,
        sessions=SessionStore(tmp_path / "s"),
        traces=TraceWriter(tmp_path / "t"),
    )
    result = pipe.evaluate(make_envelope(command="echo hi"))
    assert len(reviewer.calls) == 1
    assert result.decision == GuardrailDecision.HUMAN_APPROVAL


def test_default_reviewer_is_claude_cli_when_frontier_enabled(tmp_path) -> None:
    from lgh.frontier.claude_cli import ClaudeCliReviewer

    pipe = Pipeline(
        GuardrailConfig(),
        laya=FakeLayaClient(_assess()),
        sessions=SessionStore(tmp_path / "s"),
        traces=TraceWriter(tmp_path / "t"),
    )
    assert isinstance(pipe.reviewer, ClaudeCliReviewer)


def test_laya_down_enforce_goes_frontier(tmp_path) -> None:
    cfg = GuardrailConfig(mode=Mode.ENFORCE)
    pipe = Pipeline(
        cfg,
        laya=FakeLayaClient(None),
        reviewer=StubReviewer(unavailable=True),
        sessions=SessionStore(tmp_path / "s"),
        traces=TraceWriter(tmp_path / "t"),
    )
    result = pipe.evaluate(make_envelope(command="echo hi"))
    assert result.decision == GuardrailDecision.HUMAN_APPROVAL
