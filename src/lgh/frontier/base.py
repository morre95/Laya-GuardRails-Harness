from __future__ import annotations

from typing import Protocol

from lgh.schema.decision import GuardrailDecision
from lgh.schema.frontier import ReviewRequest, ReviewResponse


class FrontierReviewer(Protocol):
    def review(self, request: ReviewRequest) -> ReviewResponse:
        ...


FRONTIER_MAP = {
    "ALLOW": GuardrailDecision.ALLOW,
    "VERIFY": GuardrailDecision.ALLOW_WITH_VERIFICATION,
    "REPLAN": GuardrailDecision.REPLAN,
    "HUMAN_REQUIRED": GuardrailDecision.HUMAN_APPROVAL,
    "BLOCK": GuardrailDecision.BLOCK,
}


def map_frontier(decision: str) -> GuardrailDecision:
    return FRONTIER_MAP.get(decision, GuardrailDecision.HUMAN_APPROVAL)
