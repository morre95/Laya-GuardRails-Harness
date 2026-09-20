from __future__ import annotations

import json
import shutil
from pathlib import Path

HOOKS = {
    "PreToolUse": "lgh hook pre",
    "PostToolUse": "lgh hook post",
    "Stop": "lgh hook stop",
}


def install_hooks(settings_path: Path, timeout: int = 30) -> Path:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    backup = settings_path.with_suffix(settings_path.suffix + ".lgh.bak")
    data: dict = {}
    if settings_path.is_file():
        shutil.copy2(settings_path, backup)
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    hooks = data.setdefault("hooks", {})
    for event, command in HOOKS.items():
        entries = hooks.setdefault(event, [])
        already = False
        for entry in entries:
            for hook in entry.get("hooks") or []:
                if hook.get("command") == command:
                    already = True
        if already:
            continue
        entries.append(
            {
                "matcher": "",
                "hooks": [{"type": "command", "command": command, "timeout": timeout}],
            }
        )
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return settings_path
