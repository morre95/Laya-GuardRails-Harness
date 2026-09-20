from typing import Literal

from pydantic import Field

from lgh.schema.base import FrozenModel

TaskAlignmentValue = Literal["aligned", "supporting", "unclear", "outside_scope"]
ReversibilityValue = Literal["trivial", "recoverable", "difficult", "irreversible"]
HandlingValue = Literal["allow", "verify", "replan", "escalate"]


class TaskAlignmentAssessment(FrozenModel):
    value: TaskAlignmentValue
    confidence: float


class ReversibilityAssessment(FrozenModel):
    value: ReversibilityValue
    confidence: float


class HandlingAssessment(FrozenModel):
    value: HandlingValue
    confidence: float


class ChoiceAssessment(FrozenModel):
    value: str
    confidence: float


class LayaAssessment(FrozenModel):
    model: str
    latency_ms: float = Field(alias="latencyMs")
    task_alignment: TaskAlignmentAssessment = Field(alias="taskAlignment")
    destructive_risk: float = Field(alias="destructiveRisk")
    sensitive_resource: float = Field(alias="sensitiveResource")
    external_impact: float = Field(alias="externalImpact")
    reversibility: ReversibilityAssessment
    verification_needed: float = Field(alias="verificationNeeded")
    handling: HandlingAssessment
