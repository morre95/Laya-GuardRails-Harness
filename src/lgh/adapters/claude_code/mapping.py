from __future__ import annotations

from typing import Any

from lgh.schema.envelope import ToolName

TOOL_MAP: dict[str, tuple[ToolName, str]] = {
    "Bash": ("shell", "execute"),
    "Write": ("write", "write"),
    "Edit": ("edit", "edit"),
    "MultiEdit": ("edit", "edit"),
    "NotebookEdit": ("edit", "edit"),
    "Read": ("read", "read"),
    "Grep": ("read", "search"),
    "Glob": ("read", "glob"),
    "LS": ("read", "list"),
    "WebFetch": ("network", "fetch"),
    "WebSearch": ("network", "search"),
}


def map_tool(tool_name: str, tool_input: dict[str, Any] | None = None) -> tuple[ToolName, str, str | None, str | None]:
    tool_input = tool_input or {}
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        operation = parts[-1] if len(parts) > 2 else tool_name
        return "mcp", operation, tool_input.get("server") or (parts[1] if len(parts) > 1 else None), None
    mapped = TOOL_MAP.get(tool_name)
    if mapped is None:
        return "unknown", tool_name.lower(), None, None
    tool, operation = mapped
    target = (
        tool_input.get("file_path")
        or tool_input.get("path")
        or tool_input.get("notebook_path")
        or tool_input.get("url")
    )
    command = tool_input.get("command")
    if tool == "shell" and command and command.strip().startswith("git "):
        return "git", "execute", target, command
    return tool, operation, target, command
