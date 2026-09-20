from __future__ import annotations

import json
from pathlib import Path


def last_user_goal(transcript_path: str | None, limit: int = 400) -> str:
    if not transcript_path:
        return ""
    path = Path(transcript_path)
    if not path.is_file():
        return ""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > 512_000:
                handle.seek(-512_000, 2)
            data = handle.read().decode("utf-8", errors="ignore")
    except OSError:
        return ""
    goal = ""
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = _extract_text(payload)
        role = str(payload.get("type") or payload.get("role") or "")
        if role in {"user", "human"} and text:
            goal = text
        message = payload.get("message")
        if isinstance(message, dict) and message.get("role") == "user":
            extracted = _extract_text(message)
            if extracted:
                goal = extracted
    goal = " ".join(goal.split())
    if len(goal) > limit:
        return goal[: limit - 1] + "…"
    return goal


def _extract_text(payload: dict) -> str:
    content = payload.get("content") or payload.get("text") or payload.get("message")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        bits: list[str] = []
        for item in content:
            if isinstance(item, str):
                bits.append(item)
            elif isinstance(item, dict):
                if item.get("type") == "text" or "text" in item:
                    bits.append(str(item.get("text") or ""))
        return "\n".join(bits)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    return ""
