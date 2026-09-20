from lgh.schema.decision import GuardrailDecision, Mode
from lgh.adapters.claude_code.hooks import pretool_output
from lgh.config.models import GuardrailConfig
from lgh.pipeline import EvaluationResult
from lgh.schema.rules import RuleDisposition, RuleResult
from lgh.schema.trace import DecisionTrace, RuleEvaluation
from tests.helpers import make_envelope


def _result(decision: GuardrailDecision, mode: Mode) -> EvaluationResult:
    env = make_envelope(command="echo")
    rules = RuleResult(matched=[], disposition=RuleDisposition.PASS)
    trace = DecisionTrace(
        traceId="t",
        timestamp="2026-01-01T00:00:00Z",
        envelopeHash="0" * 64,
        ruleEvaluation=RuleEvaluation(matched=[], disposition="PASS"),
        policyDecision=decision,
        finalDecision=decision,
        mode=str(mode),
    )
    return EvaluationResult(
        envelope=env,
        rules=rules,
        decision=decision,
        policy_decision=decision,
        laya=None,
        frontier=None,
        verification=None,
        human_prompt_text="Approval required\n\nAction:\necho",
        trace=trace,
        error=None,
        mode=mode,
    )


def test_all_decisions_x_modes() -> None:
    cfg = GuardrailConfig(mode=Mode.ENFORCE, allow_passthrough=True)
    for decision in GuardrailDecision:
        shadow = pretool_output(_result(decision, Mode.SHADOW), cfg)
        assert shadow is None
        warn = pretool_output(_result(decision, Mode.WARN), cfg)
        if decision == GuardrailDecision.ALLOW:
            assert warn is None
        else:
            assert warn is not None
        enforce = pretool_output(_result(decision, Mode.ENFORCE), cfg)
        if decision == GuardrailDecision.ALLOW:
            assert enforce["hookSpecificOutput"]["permissionDecision"] == "allow"
        elif decision == GuardrailDecision.HUMAN_APPROVAL:
            assert enforce["hookSpecificOutput"]["permissionDecision"] == "ask"
        elif decision in {
            GuardrailDecision.BLOCK,
            GuardrailDecision.REPLAN,
            GuardrailDecision.ALLOW_WITH_VERIFICATION,
        }:
            assert enforce["hookSpecificOutput"]["permissionDecision"] == "deny"
