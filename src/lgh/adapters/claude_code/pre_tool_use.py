from __future__ import annotations

import json
import sys
from typing import Any

from lgh.adapters.claude_code.hooks import envelope_from_hook, pretool_output
from lgh.config.loader import load_config
from lgh.pipeline import Pipeline
from lgh.session.store import SessionStore
from lgh.trace.writer import TraceWriter


def run_pre(payload: dict[str, Any] | None = None) -> int:
    if payload is None:
        payload = json.load(sys.stdin)
    cwd = payload.get("cwd")
    config = load_config(cwd=cwd)
    sessions = SessionStore()
    pipeline = Pipeline(config, sessions=sessions, traces=TraceWriter())
    try:
        envelope = envelope_from_hook(payload, config, phase="PRE_ACTION", sessions=sessions)
        result = pipeline.evaluate(envelope)
        output = pretool_output(result, config)
        if output is not None:
            json.dump(output, sys.stdout)
            sys.stdout.write("\n")
        return 0
    except Exception:
        if config.mode.value == "shadow":
            return 0
        return 0


def main() -> None:
    raise SystemExit(run_pre())


if __name__ == "__main__":
    main()
