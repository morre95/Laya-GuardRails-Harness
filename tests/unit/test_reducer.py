import pytest
from hypothesis import given, settings, strategies as st

from lgh.config.models import LayaThresholds
from lgh.policy.reducer import reduce_decision
from lgh.schema.decision import DECISION_RANK, GuardrailDecision
from lgh.schema.laya import HandlingAssessment, LayaAssessment, ReversibilityAssessment, TaskAlignmentAssessment
from lgh.schema.rules import RuleDisposition, RuleMatch, RuleResult


def assessment(**kwargs) -> LayaAssessment:
    return LayaAssessment(
        model="fake",
        latencyMs=1,
        taskAlignment=TaskAlignmentAssessment(
            value=kwargs.get("task", "aligned"),
            confidence=kwargs.get("task_c", 0.9),
        ),
        destructiveRisk=kwargs.get("destructive", 0.1),
        sensitiveResource=kwargs.get("sensitive", 0.1),
        externalImpact=kwargs.get("external", 0.1),
        reversibility=ReversibilityAssessment(
            value=kwargs.get("rev", "trivial"),
            confidence=0.9,
        ),
        verificationNeeded=kwargs.get("verify", 0.1),
        handling=HandlingAssessment(
            value=kwargs.get("handling", "allow"),
            confidence=kwargs.get("hconf", 0.9),
        ),
    )


def rules(disp: RuleDisposition) -> RuleResult:
    return RuleResult(
        matched=[RuleMatch(id="T", category="t", description="t", disposition=disp)],
        disposition=disp,
    )


def test_hard_block() -> None:
    assert reduce_decision(rules(RuleDisposition.BLOCK), assessment()) == GuardrailDecision.BLOCK


def test_hard_allow_skips_laya() -> None:
    assert reduce_decision(rules(RuleDisposition.ALLOW), assessment(destructive=0.99)) == GuardrailDecision.ALLOW


def test_low_confidence_never_allows() -> None:
    decision = reduce_decision(rules(RuleDisposition.PASS), assessment(hconf=0.2, handling="allow"))
    assert decision != GuardrailDecision.ALLOW
    assert decision == GuardrailDecision.FRONTIER_REVIEW


def test_outside_scope_replans() -> None:
    assert (
        reduce_decision(rules(RuleDisposition.PASS), assessment(task="outside_scope", hconf=0.9))
        == GuardrailDecision.REPLAN
    )


def test_missing_laya_escalates() -> None:
    assert reduce_decision(RuleResult(matched=[], disposition=RuleDisposition.PASS), None) == GuardrailDecision.FRONTIER_REVIEW


@given(
    destructive=st.floats(0, 1),
    extra=st.floats(0, 0.2),
)
@settings(max_examples=40)
def test_raising_destructive_never_milder(destructive: float, extra: float) -> None:
    a1 = assessment(destructive=destructive, hconf=0.9)
    a2 = assessment(destructive=min(1.0, destructive + extra), hconf=0.9)
    d1 = reduce_decision(RuleResult(matched=[], disposition=RuleDisposition.PASS), a1)
    d2 = reduce_decision(RuleResult(matched=[], disposition=RuleDisposition.PASS), a2)
    assert DECISION_RANK[d2] >= DECISION_RANK[d1] or d1 in {
        GuardrailDecision.REPLAN,
        GuardrailDecision.ALLOW_WITH_VERIFICATION,
        GuardrailDecision.ALLOW,
        GuardrailDecision.FRONTIER_REVIEW,
    }
    if min(1.0, destructive + extra) >= 0.85:
        assert d2 == GuardrailDecision.FRONTIER_REVIEW
