from __future__ import annotations

from lgh.config.models import LayaThresholds
from lgh.schema.decision import GuardrailDecision
from lgh.schema.laya import LayaAssessment
from lgh.schema.rules import RuleDisposition, RuleResult


def reduce_decision(
    rules: RuleResult,
    laya: LayaAssessment | None,
    thresholds: LayaThresholds | None = None,
) -> GuardrailDecision:
    """Deterministic Policy Reducer. Uncertainty always escalates upward."""
    t = thresholds or LayaThresholds()
    if rules.disposition == RuleDisposition.BLOCK:
        return GuardrailDecision.BLOCK
    if rules.disposition == RuleDisposition.HUMAN:
        return GuardrailDecision.HUMAN_APPROVAL
    if rules.disposition == RuleDisposition.ALLOW:
        return GuardrailDecision.ALLOW
    if rules.disposition == RuleDisposition.VERIFY:
        return GuardrailDecision.ALLOW_WITH_VERIFICATION
    if laya is None:
        return GuardrailDecision.FRONTIER_REVIEW
    if laya.external_impact >= t.external_impact:
        return GuardrailDecision.FRONTIER_REVIEW
    if laya.destructive_risk >= t.destructive:
        return GuardrailDecision.FRONTIER_REVIEW
    if laya.sensitive_resource >= t.sensitive:
        return GuardrailDecision.FRONTIER_REVIEW
    if laya.reversibility.value == "irreversible":
        return GuardrailDecision.FRONTIER_REVIEW
    if laya.task_alignment.value == "outside_scope":
        return GuardrailDecision.REPLAN
    if laya.handling.confidence < t.confidence:
        return GuardrailDecision.FRONTIER_REVIEW
    if laya.handling.value == "escalate":
        return GuardrailDecision.FRONTIER_REVIEW
    if laya.handling.value == "replan":
        return GuardrailDecision.REPLAN
    if laya.handling.value == "verify" or laya.verification_needed >= t.verification:
        return GuardrailDecision.ALLOW_WITH_VERIFICATION
    return GuardrailDecision.ALLOW
