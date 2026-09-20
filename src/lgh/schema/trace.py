from typing import Literal

from pydantic import Field

from lgh.schema.base import FrozenModel
from lgh.schema.decision import GuardrailDecision
from lgh.schema.laya import LayaAssessment


class RuleEvaluation(FrozenModel):
    matched: list[str]
    disposition: str


class LayaTrace(FrozenModel):
    model: str
    assessment: LayaAssessment
    error: str | None = None


class FrontierTrace(FrozenModel):
    model: str
    decision: str
    reason: str


class HumanTrace(FrozenModel):
    requested: bool
    decision: Literal["approved", "denied"] | None = None


class Outcome(FrozenModel):
    executed: bool
    exit_code: int | None = Field(default=None, alias="exitCode")
    verification_passed: bool | None = Field(default=None, alias="verificationPassed")


class DecisionTrace(FrozenModel):
    trace_id: str = Field(alias="traceId")
    timestamp: str
    envelope_hash: str = Field(alias="envelopeHash")
    prev_hash: str | None = Field(default=None, alias="prevHash")
    rule_evaluation: RuleEvaluation = Field(alias="ruleEvaluation")
    laya: LayaTrace | None = None
    policy_decision: GuardrailDecision = Field(alias="policyDecision")
    frontier: FrontierTrace | None = None
    human: HumanTrace | None = None
    verification_skill: str | None = Field(default=None, alias="verificationSkill")
    final_decision: GuardrailDecision = Field(alias="finalDecision")
    outcome: Outcome | None = None
    error: str | None = None
    contents_logged: bool = Field(default=False, alias="contentsLogged")
    mode: str = "shadow"
