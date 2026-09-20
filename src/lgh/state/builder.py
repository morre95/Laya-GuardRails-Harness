from __future__ import annotations

from lgh.config.models import GuardrailConfig
from lgh.schema.envelope import (
    ActionEnvelope,
    ActionSummary,
    LayaAction,
    LayaRepo,
    LayaState,
)
from lgh.state.budget import compress_state
from lgh.state.environment import detect_environment
from lgh.state.redact import redact_text


def summarize_action(summary: ActionSummary) -> str:
    if summary.summary:
        return summary.summary
    bits = [summary.operation, summary.tool]
    if summary.target:
        bits.append(summary.target)
    elif summary.command:
        bits.append(summary.command[:80])
    return " ".join(str(b) for b in bits if b)


def build_laya_state(envelope: ActionEnvelope, config: GuardrailConfig | None = None) -> LayaState:
    del config
    action = envelope.action
    state = LayaState(
        goal=redact_text(envelope.task.user_goal) or "",
        plan=redact_text(envelope.task.current_plan),
        repo=LayaRepo(
            branch=envelope.repo.branch,
            dirty=envelope.repo.dirty,
            changed=list(envelope.repo.changed_files),
        ),
        environment=envelope.environment.name,
        action=LayaAction(
            tool=action.tool,
            operation=action.operation,
            command=redact_text(action.command),
            target=action.target,
        ),
        recent=[summarize_action(item) for item in envelope.context.recent_actions],
    )
    return compress_state(state)


def apply_environment(envelope: ActionEnvelope, config: GuardrailConfig) -> ActionEnvelope:
    detected = detect_environment(
        branch=envelope.repo.branch,
        command=envelope.action.command,
        cwd=envelope.repo.cwd,
        config=config,
        action=envelope.action,
    )
    if envelope.environment.name == "unknown" or detected.confidence > envelope.environment.confidence:
        return envelope.model_copy(update={"environment": detected})
    return envelope
