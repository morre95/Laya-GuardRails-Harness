from __future__ import annotations

import subprocess
from pathlib import Path


def inspect_repo(cwd: str) -> tuple[str | None, str | None, bool, list[str]]:
    root = _git(cwd, ["rev-parse", "--show-toplevel"])
    branch = _git(cwd, ["branch", "--show-current"])
    porcelain = _git(cwd, ["status", "--porcelain"])
    changed: list[str] = []
    dirty = False
    if porcelain:
        dirty = True
        for line in porcelain.splitlines():
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path:
                changed.append(path)
    if root is None:
        root = str(Path(cwd).resolve()) if Path(cwd).exists() else cwd
    return root, branch or None, dirty, changed[:50]


def _git(cwd: str, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()
