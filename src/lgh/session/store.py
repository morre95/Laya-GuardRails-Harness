from __future__ import annotations

import json
from pathlib import Path

from lgh.ids import utc_now_iso
from lgh.paths import sessions_dir
from lgh.schema.envelope import ActionSummary


class SessionStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or sessions_dir()
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, session_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_id)
        return self.directory / f"{safe}.json"

    def load(self, session_id: str) -> dict:
        path = self.path(session_id)
        if not path.is_file():
            return {
                "session_id": session_id,
                "recent_actions": [],
                "counters": {},
                "pending_verification": None,
                "pending_human": None,
                "executed_tests": [],
                "last_test_exit": None,
                "changed_files": [],
                "block_violations": [],
                "stop_hook_count": 0,
                "updated_at": utc_now_iso(),
            }
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, session_id: str, data: dict) -> None:
        data["updated_at"] = utc_now_iso()
        self.path(session_id).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_action(self, session_id: str, summary: ActionSummary, changed: list[str] | None = None) -> None:
        data = self.load(session_id)
        items = list(data.get("recent_actions") or [])
        items.append(summary.model_dump(mode="json"))
        data["recent_actions"] = items[-20:]
        if changed:
            seen = list(data.get("changed_files") or [])
            for item in changed:
                if item not in seen:
                    seen.append(item)
            data["changed_files"] = seen
        self.save(session_id, data)

    def recent_summaries(self, session_id: str) -> list[ActionSummary]:
        data = self.load(session_id)
        return [ActionSummary.model_validate(item) for item in data.get("recent_actions") or []]
