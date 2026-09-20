from typing import Literal

from pydantic import Field

from lgh.schema.base import FrozenModel
from lgh.schema.envelope import Action, Environment
from lgh.schema.laya import LayaAssessment
from lgh.schema.rules import RuleMatch

FrontierDecision = Literal["ALLOW", "VERIFY", "REPLAN", "HUMAN_REQUIRED", "BLOCK"]


class ReviewRequest(FrozenModel):
    goal: str
    proposed_action: Action = Field(alias="proposedAction")
    environment: Environment
    relevant_context: list[str] = Field(alias="relevantContext")
    matched_rules: list[RuleMatch] = Field(alias="matchedRules")
    laya_assessment: LayaAssessment | None = Field(default=None, alias="layaAssessment")


class ReviewResponse(FrozenModel):
    decision: FrontierDecision
    reason: str = Field(max_length=300)
    verification_skill: str | None = Field(default=None, alias="verificationSkill")
