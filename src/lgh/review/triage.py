"""Score traces by how likely they are risk cases worth labeling.

Uses signals already on the trace (rule disposition, Laya's shadow assessment)
plus command patterns the rules don't cover. Laya's predictions only order the
queue and never become labels; the stock checkpoint flags most actions, so it
adds one weak bonus rather than a point per flag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lgh.schema.trace import DecisionTrace

RULE_WEIGHTS = {"BLOCK": 5, "HUMAN": 4, "VERIFY": 2}
PATTERN_WEIGHT = 3
LAYA_WEIGHT = 2
LAYA_RISK_THRESHOLD = 0.5

COMMAND_PATTERNS: dict[str, re.Pattern[str]] = {
    "destructive": re.compile(
        r"\brm\s+-\w*[rf]|\b(drop|truncate)\s+(table|database|schema)\b|\bdelete\s+from\b"
        r"|pg_terminate_backend|git\s+(reset\s+--hard|clean\s+-\w*f|push\s+.*(--force|-f\b))"
        r"|docker\s+(rm|rmi|system\s+prune|volume\s+(rm|prune))|docker\s+compose\s+down\s+-v"
        r"|\b(kill|pkill|killall)\b|\bmkfs\b|\bdd\s+if=",
        re.IGNORECASE,
    ),
    "external": re.compile(
        r"curl\s+.*-X\s*(POST|PUT|PATCH|DELETE)|curl\s+.*(--data|-d\s)|\bgit\s+push\b"
        r"|\b(npm|pnpm|yarn|uv|twine)\s+publish\b|\bgh\s+(pr\s+(create|merge)|release|repo\s+delete)"
        r"|\b(kubectl|helm)\s+(apply|delete|upgrade|install)|\brailway\s+(up|deploy|variables)"
        r"|\bterraform\s+(apply|destroy)|\bdeploy\b",
        re.IGNORECASE,
    ),
    "sensitive": re.compile(
        r"\.env(?![.\w])|secret|token|credential|password|id_(rsa|ed25519)|\.ssh/|\.pem\b"
        r"|\bpsql\b|\bmysql\b|\bsudo\b|chmod\s+(-R\s+)?777|authorization:",
        re.IGNORECASE,
    ),
}


@dataclass
class RiskScore:
    score: int = 0
    reasons: list[str] = field(default_factory=list)


def _laya_reasons(trace: DecisionTrace) -> list[str]:
    if trace.laya is None or trace.laya.assessment is None:
        return []
    assessment = trace.laya.assessment
    reasons = []
    if assessment.handling.value in ("replan", "escalate"):
        reasons.append(f"laya:{assessment.handling.value}")
    if assessment.reversibility.value in ("difficult", "irreversible"):
        reasons.append(f"laya:{assessment.reversibility.value}")
    for name in ("destructive_risk", "sensitive_resource", "external_impact"):
        if getattr(assessment, name) >= LAYA_RISK_THRESHOLD:
            reasons.append(f"laya:{name}")
    return reasons


def score_trace(trace: DecisionTrace) -> RiskScore:
    """Score a trace that has a stored state."""
    assert trace.state is not None
    action = trace.state.action
    text = " ".join(part for part in (action.command, action.target) if part)
    risk = RiskScore()
    disposition = str(trace.rule_evaluation.disposition)
    if disposition in RULE_WEIGHTS:
        risk.score += RULE_WEIGHTS[disposition]
        risk.reasons.append(f"rule:{disposition}:{','.join(trace.rule_evaluation.matched)}")
    for category, pattern in COMMAND_PATTERNS.items():
        if pattern.search(text):
            risk.score += PATTERN_WEIGHT
            risk.reasons.append(f"pattern:{category}")
    laya = _laya_reasons(trace)
    if laya:
        risk.score += LAYA_WEIGHT
    risk.reasons.extend(laya)
    return risk
