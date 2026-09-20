from enum import StrEnum


class GuardrailDecision(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_WITH_VERIFICATION = "ALLOW_WITH_VERIFICATION"
    REPLAN = "REPLAN"
    FRONTIER_REVIEW = "FRONTIER_REVIEW"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    BLOCK = "BLOCK"


class Mode(StrEnum):
    SHADOW = "shadow"
    WARN = "warn"
    ENFORCE = "enforce"


DECISION_RANK: dict[GuardrailDecision, int] = {
    GuardrailDecision.ALLOW: 0,
    GuardrailDecision.ALLOW_WITH_VERIFICATION: 1,
    GuardrailDecision.REPLAN: 2,
    GuardrailDecision.FRONTIER_REVIEW: 3,
    GuardrailDecision.HUMAN_APPROVAL: 4,
    GuardrailDecision.BLOCK: 5,
}

MODE_RANK: dict[Mode, int] = {
    Mode.SHADOW: 0,
    Mode.WARN: 1,
    Mode.ENFORCE: 2,
}
