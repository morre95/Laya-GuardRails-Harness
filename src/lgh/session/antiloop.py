from __future__ import annotations

from lgh.schema.decision import GuardrailDecision
from lgh.session.store import SessionStore
from lgh.trace.hashing import sha256_text


def action_key(command: str | None, target: str | None, tool: str, operation: str) -> str:
    return sha256_text("|".join([tool, operation, target or "", command or ""]))[:16]


def apply_antiloop(
    *,
    session_id: str,
    store: SessionStore,
    key: str,
    decision: GuardrailDecision,
    max_verification: int = 2,
    max_replans: int = 2,
) -> GuardrailDecision:
    data = store.load(session_id)
    counters: dict = data.setdefault("counters", {})
    slot = counters.setdefault(key, {"verification": 0, "replan": 0, "frontier": 0})
    if decision == GuardrailDecision.ALLOW_WITH_VERIFICATION:
        slot["verification"] += 1
        if slot["verification"] > max_verification:
            slot["frontier"] += 1
            decision = GuardrailDecision.FRONTIER_REVIEW
    elif decision == GuardrailDecision.REPLAN:
        slot["replan"] += 1
        if slot["replan"] > max_replans:
            slot["frontier"] += 1
            decision = GuardrailDecision.FRONTIER_REVIEW
    if decision == GuardrailDecision.FRONTIER_REVIEW and slot["frontier"] > 1:
        decision = GuardrailDecision.HUMAN_APPROVAL
    if decision == GuardrailDecision.FRONTIER_REVIEW:
        slot["frontier"] += 1
    counters[key] = slot
    data["counters"] = counters
    store.save(session_id, data)
    return decision
