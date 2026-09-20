from __future__ import annotations

import json
from typing import Any

from lgh.adapters.claude_code.mapping import map_tool
from lgh.adapters.claude_code.repo import inspect_repo
from lgh.adapters.claude_code.transcript import last_user_goal
from lgh.config.models import GuardrailConfig
from lgh.ids import new_id, utc_now_iso
from lgh.pipeline import EvaluationResult
from lgh.schema.decision import GuardrailDecision, Mode
from lgh.schema.envelope import (
    Action,
    ActionEnvelope,
    ActionSummary,
    Context,
    Environment,
    Event,
    Repo,
    Session,
    Task,
)
from lgh.session.store import SessionStore
from lgh.state.environment import detect_environment


def envelope_from_hook(
    payload: dict[str, Any],
    config: GuardrailConfig,
    *,
    phase: str,
    sessions: SessionStore | None = None,
) -> ActionEnvelope:
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    tool, operation, target, command = map_tool(tool_name, tool_input)
    cwd = str(payload.get("cwd") or ".")
    root, branch, dirty, changed = inspect_repo(cwd)
    env = detect_environment(
        branch=branch,
        command=command,
        cwd=cwd,
        config=config,
        action=Action(tool=tool, operation=operation, target=target, command=command, arguments=tool_input),
    )
    session_id = str(payload.get("session_id") or "unknown")
    recent: list[ActionSummary] = []
    if sessions is not None:
        recent = sessions.recent_summaries(session_id)[-5:]
    return ActionEnvelope(
        schemaVersion="0.1",
        event=Event(id=new_id(), timestamp=utc_now_iso(), phase=phase),  # type: ignore[arg-type]
        session=Session(id=session_id, harness="claude-code"),
        task=Task(
            userGoal=last_user_goal(payload.get("transcript_path")),
            currentPlan=None,
        ),
        repo=Repo(
            cwd=cwd,
            root=root,
            branch=branch,
            dirty=dirty,
            changedFiles=changed,
        ),
        environment=env,
        action=Action(
            tool=tool,
            operation=operation,
            target=target,
            command=command,
            arguments=tool_input,
        ),
        context=Context(activeSkills=[], recentActions=recent),
    )


def pretool_output(result: EvaluationResult, config: GuardrailConfig) -> dict[str, Any] | None:
    mode = result.mode
    decision = result.decision
    if mode == Mode.SHADOW:
        return None
    if mode == Mode.WARN:
        if decision == GuardrailDecision.ALLOW:
            return None
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": _reason(result),
            }
        }
    if decision == GuardrailDecision.ALLOW:
        if config.allow_passthrough:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": "LGH hard-rule allow",
                }
            }
        return None
    if decision == GuardrailDecision.BLOCK:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": _reason(result),
            }
        }
    if decision == GuardrailDecision.HUMAN_APPROVAL:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": result.human_prompt_text or _reason(result),
            }
        }
    if decision == GuardrailDecision.REPLAN:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    "REPLAN: do not execute this action. Choose a different approach. "
                    + _reason(result)
                ),
            }
        }
    if decision == GuardrailDecision.ALLOW_WITH_VERIFICATION:
        directive = result.verification
        req = "; ".join(directive.requirements) if directive else "verify first"
        skill = directive.skill if directive else "generic-verification"
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"ALLOW_WITH_VERIFICATION skill={skill}. "
                    f"Requirements: {req}. resumePolicy=REEVALUATE_ACTION. "
                    "Complete the skill, then retry this exact action."
                ),
            }
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": _reason(result),
        }
    }


def _reason(result: EvaluationResult) -> str:
    if result.human_prompt_text:
        return result.human_prompt_text
    matched = ",".join(item.id for item in result.rules.matched) or "none"
    return f"LGH {result.decision} rules={matched}"
