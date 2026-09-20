"""XDG-style paths for LGH state, config, and traces."""

from __future__ import annotations

import os
from pathlib import Path


def user_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "lgh"


def user_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    return Path(base) / "lgh"


def user_data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(base) / "lgh"


def user_config_path() -> Path:
    return user_config_dir() / "config.yaml"


def user_rules_path() -> Path:
    return user_config_dir() / "rules.yaml"


def traces_dir() -> Path:
    return user_data_dir() / "traces"


def sessions_dir() -> Path:
    return user_state_dir() / "sessions"


def daemon_pid_path() -> Path:
    return user_state_dir() / "daemon.pid"


def daemon_log_path() -> Path:
    return user_state_dir() / "daemon.log"


def repo_config_dir(repo_root: Path | str | None) -> Path | None:
    if repo_root is None:
        return None
    return Path(repo_root) / ".guardrail"
