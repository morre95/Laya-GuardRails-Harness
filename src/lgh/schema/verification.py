from typing import Literal

from pydantic import Field

from lgh.schema.base import FrozenModel

ResumePolicy = Literal["REEVALUATE_ACTION"]


class VerificationDirective(FrozenModel):
    skill: str
    requirements: list[str]
    resume_policy: ResumePolicy = Field(default="REEVALUATE_ACTION", alias="resumePolicy")
