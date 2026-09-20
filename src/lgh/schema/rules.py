from enum import StrEnum

from lgh.schema.base import FrozenModel


class RuleDisposition(StrEnum):
    PASS = "PASS"
    ALLOW = "ALLOW"
    VERIFY = "VERIFY"
    HUMAN = "HUMAN"
    BLOCK = "BLOCK"


DISPOSITION_RANK: dict[RuleDisposition, int] = {
    RuleDisposition.ALLOW: 0,
    RuleDisposition.PASS: 1,
    RuleDisposition.VERIFY: 2,
    RuleDisposition.HUMAN: 3,
    RuleDisposition.BLOCK: 4,
}


class RuleMatch(FrozenModel):
    id: str
    category: str
    description: str
    disposition: RuleDisposition


class RuleResult(FrozenModel):
    matched: list[RuleMatch]
    disposition: RuleDisposition
