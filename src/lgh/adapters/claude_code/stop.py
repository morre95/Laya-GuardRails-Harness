from __future__ import annotations

import json
import sys
from typing import Any

from lgh.adapters.claude_code.hooks import envelope_from_hook
from lgh.config.loader import load_config
from lgh.schema.decision import Mode
from lgh.session.store import SessionStore
from lgh.stopguard.checks import stop_issues
from lgh.trace.writer import TraceWriter


def run_stop(payload: dict[str, Any] | None = None) -> int:
    if payload is None:
        payload = json.load(sys.stdin)
    cwd = payload.get("cwd") or "."
    config = load_config(cwd=cwd)
    sessions = SessionStore()
    try:
        envelope = envelope_from_hook(
            {**payload, "tool_name": "Stop", "tool_input": {}},
            config,
            phase="STOP",
            sessions=sessions,
        )
        session = sessions.load(envelope.session.id)
        if payload.get("stop_hook_active"):
            return 0
        issues = stop_issues(envelope, session, config)
        traces = TraceWriter()
        from lgh.pipeline import Pipeline

        pipeline = Pipeline(config, sessions=sessions, traces=traces)
        pipeline.evaluate(envelope)
        if not issues:
            return 0
        session["stop_hook_count"] = int(session.get("stop_hook_count") or 0) + 1
        sessions.save(envelope.session.id, session)
        if config.mode == Mode.SHADOW:
            return 0
        output = {
            "decision": "block",
            "reason": "Stop blocked by LGH: " + "; ".join(issues),
        }
        json.dump(output, sys.stdout)
        sys.stdout.write("\n")
        return 0
    except Exception:
        return 0


def main() -> None:
    raise SystemExit(run_stop())


if __name__ == "__main__":
    main()
