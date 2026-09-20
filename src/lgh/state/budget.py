from __future__ import annotations

import json

from lgh.schema.envelope import LayaState

TARGET_TOKENS = 500
HARD_MAX_TOKENS = 700
MAX_RECENT = 5
MAX_CHANGED = 20
MAX_COMMAND_CHARS = 1000


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def state_token_count(state: LayaState) -> int:
    payload = state.model_dump(mode="json", exclude_none=True)
    return estimate_tokens(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _truncate(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def compress_state(state: LayaState) -> LayaState:
    """Deterministically compress LayaState to the v0.1 budget."""
    command = _truncate(state.action.command, MAX_COMMAND_CHARS)
    changed = list(state.repo.changed[:MAX_CHANGED])
    recent = list(state.recent[-MAX_RECENT:])
    goal = state.goal
    plan = state.plan
    current = state.model_copy(
        update={
            "goal": goal,
            "plan": plan,
            "recent": recent,
            "repo": state.repo.model_copy(update={"changed": changed}),
            "action": state.action.model_copy(update={"command": command}),
        }
    )

    steps = [
        lambda s: s.model_copy(update={"plan": None}) if s.plan else s,
        lambda s: s.model_copy(update={"recent": []}) if s.recent else s,
        lambda s: s.model_copy(
            update={"repo": s.repo.model_copy(update={"changed": s.repo.changed[:8]})}
        ),
        lambda s: s.model_copy(update={"goal": _truncate(s.goal, 240) or ""}),
        lambda s: s.model_copy(
            update={
                "action": s.action.model_copy(
                    update={"command": _truncate(s.action.command, 240)}
                )
            }
        ),
        lambda s: s.model_copy(
            update={"repo": s.repo.model_copy(update={"changed": s.repo.changed[:3]})}
        ),
        lambda s: s.model_copy(update={"goal": _truncate(s.goal, 80) or ""}),
    ]

    while state_token_count(current) > TARGET_TOKENS:
        progressed = False
        for step in steps:
            nxt = step(current)
            if nxt != current:
                current = nxt
                progressed = True
                if state_token_count(current) <= TARGET_TOKENS:
                    return current
        if not progressed:
            break

    if state_token_count(current) > HARD_MAX_TOKENS:
        current = current.model_copy(
            update={
                "goal": _truncate(current.goal, 40) or "",
                "plan": None,
                "recent": [],
                "repo": current.repo.model_copy(update={"changed": current.repo.changed[:1]}),
                "action": current.action.model_copy(
                    update={"command": _truncate(current.action.command, 80)}
                ),
            }
        )
    return current
