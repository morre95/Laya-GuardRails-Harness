from __future__ import annotations

import json
from pathlib import Path

from lgh.schema.envelope import InstructionContext
from lgh.state.redact import redact_text

MAX_TRANSCRIPT_BYTES = 512_000
MAX_INSTRUCTIONS = 4
MAX_INSTRUCTION_CHARS = 4_000


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 1)] + '…'


def read_instruction_context(transcript_path: str | None) -> InstructionContext:
    """Read genuine user text, never tool results or generated context.

    Keep a recent window, rather than guessing where one task ends and another
    starts. The snapshot is taken by the hook; review never rereads live history.
    """
    if not transcript_path:
        return InstructionContext()
    try:
        with Path(transcript_path).open('rb') as handle:
            size = handle.seek(0, 2)
            offset = max(0, size - MAX_TRANSCRIPT_BYTES)
            handle.seek(offset)
            data = handle.read().decode('utf-8', errors='ignore')
    except OSError:
        return InstructionContext()
    messages: list[str] = []
    for line in data.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get('isMeta') or payload.get('isCompactSummary'):
            continue
        message = payload.get('message')
        if isinstance(message, dict):
            role = message.get('role') or payload.get('type') or payload.get('role')
        else:
            message = payload
            role = payload.get('type') or payload.get('role')
        if role not in ('user', 'human'):
            continue
        text = _extract_text(message).strip()
        if text:
            messages.append(redact_text(text) or '')
    recent = messages[-MAX_INSTRUCTIONS:]
    return InstructionContext(
        messages=[_shorten(text, MAX_INSTRUCTION_CHARS) for text in recent],
        history_truncated=offset > 0 or len(messages) > MAX_INSTRUCTIONS,
        text_truncated=any(len(text) > MAX_INSTRUCTION_CHARS for text in recent),
    )


def goal_from_context(context: InstructionContext, limit: int = 400) -> str:
    """Give each retained instruction space so short followups keep context."""
    messages = [' '.join(text.split()) for text in context.messages]
    if not messages or limit <= 0:
        return ''
    if len(messages) == 1:
        return _shorten(messages[0], limit)
    prefixes = [f'[{i + 1}] ' for i in range(len(messages))]
    available = limit - sum(map(len, prefixes)) - (len(messages) - 1)
    if available < len(messages):
        return _shorten(messages[-1], limit)
    share, extra = divmod(available, len(messages))
    return '\n'.join(prefix + _shorten(text, share + (i < extra))
                     for i, (prefix, text) in enumerate(zip(prefixes, messages)))


def last_user_goal(transcript_path: str | None, limit: int = 400) -> str:
    return goal_from_context(read_instruction_context(transcript_path), limit)


def _extract_text(payload: dict) -> str:
    if payload.get('type') == 'tool_result':
        return ''
    content = payload.get('content', payload.get('text', ''))
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(
            item if isinstance(item, str) else item['text']
            for item in content
            if isinstance(item, str) or (
                isinstance(item, dict) and item.get('type') == 'text'
                and isinstance(item.get('text'), str)
            )
        )
    if isinstance(content, dict) and content.get('type') in (None, 'text'):
        text = content.get('text')
        return text if isinstance(text, str) else ''
    return ''
