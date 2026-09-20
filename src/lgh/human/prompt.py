from __future__ import annotations

from lgh.schema.envelope import ActionEnvelope
from lgh.schema.rules import RuleResult


def human_prompt(
    envelope: ActionEnvelope,
    rules: RuleResult,
    *,
    extra_reasons: list[str] | None = None,
) -> str:
    action = envelope.action
    displayed = action.command or action.target or f"{action.tool}:{action.operation}"
    reasons = [item.description for item in rules.matched]
    reasons.extend(extra_reasons or [])
    if not reasons:
        reasons = ["policy required explicit approval"]
    bullets = "\n".join(f"• {reason}" for reason in reasons[:6])
    return (
        "Approval required\n\n"
        f"Action:\n{displayed}\n\n"
        f"Why flagged:\n{bullets}\n\n"
        f"Agent goal:\n{envelope.task.user_goal}\n\n"
        "Approve this exact action?\n\n"
        "[Approve once]\n"
        "[Deny]"
    )
