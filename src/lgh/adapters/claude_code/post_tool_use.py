from __future__ import annotations

import json
import sys
from typing import Any

from lgh.adapters.claude_code.hooks import envelope_from_hook
from lgh.adapters.claude_code.mapping import map_tool
from lgh.config.loader import load_config
from lgh.schema.envelope import ActionSummary
from lgh.schema.trace import Outcome
from lgh.session.store import SessionStore
from lgh.trace.reader import iter_traces
from lgh.trace.writer import TraceWriter


def _exit_code(tool_response: Any) -> int | None:
    if isinstance(tool_response, dict):
        if "exitCode" in tool_response:
            try:
                return int(tool_response["exitCode"])
            except (TypeError, ValueError):
                return None
        if "exit_code" in tool_response:
            try:
                return int(tool_response["exit_code"])
            except (TypeError, ValueError):
                return None
        stdout = str(tool_response.get("stdout") or "")
        stderr = str(tool_response.get("stderr") or "")
        if "error" in stderr.lower() or "failed" in stdout.lower():
            return 1
    return 0


def run_post(payload: dict[str, Any] | None = None) -> int:
    if payload is None:
        payload = json.load(sys.stdin)
    cwd = payload.get("cwd")
    config = load_config(cwd=cwd)
    sessions = SessionStore()
    try:
        envelope = envelope_from_hook(payload, config, phase="POST_ACTION", sessions=sessions)
        tool_name = str(payload.get("tool_name") or "")
        tool_input = payload.get("tool_input") or {}
        tool, operation, target, command = map_tool(tool_name, tool_input if isinstance(tool_input, dict) else {})
        summary = ActionSummary(
            tool=tool,
            operation=operation,
            target=target,
            command=command,
            summary=f"{operation} {target or command or tool}",
        )
        changed = []
        if target:
            changed = [target]
        sessions.record_action(envelope.session.id, summary, changed)
        data = sessions.load(envelope.session.id)
        exit_code = _exit_code(payload.get("tool_response"))
        command_text = command or ""
        if any(command_text.startswith(cmd) or cmd in command_text for cmd in config.known_test_commands):
            tests = list(data.get("executed_tests") or [])
            tests.append(command_text)
            data["executed_tests"] = tests
            data["last_test_exit"] = exit_code
            sessions.save(envelope.session.id, data)
        if data.get("pending_human"):
            data["pending_human"] = {"requested": True, "decision": "approved"}
            sessions.save(envelope.session.id, data)
        writer = TraceWriter()
        # Outcome-only append as a lightweight follow-up trace is avoided; update last matching hash in session.
        traces = list(iter_traces())
        if traces:
            last = traces[-1]
            if last.envelope_hash:
                updated = last.model_copy(
                    update={"outcome": Outcome(executed=True, exitCode=exit_code)}
                )
                writer.append(updated)
        return 0
    except Exception:
        return 0


def main() -> None:
    raise SystemExit(run_post())


if __name__ == "__main__":
    main()
