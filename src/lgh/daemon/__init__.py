from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from lgh.paths import daemon_log_path, daemon_pid_path, user_state_dir


def _pid() -> int | None:
    path = daemon_pid_path()
    if not path.is_file():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def is_running() -> bool:
    pid = _pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def status_text(host: str = "127.0.0.1", port: int = 8765) -> str:
    running = is_running()
    health = "unreachable"
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=1) as resp:
            health = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError):
        pass
    return f"running={running} pid={_pid()} health={health}"


def start(host: str = "127.0.0.1", port: int = 8765, device: str = "cpu") -> None:
    if is_running():
        return
    user_state_dir().mkdir(parents=True, exist_ok=True)
    log = daemon_log_path().open("a", encoding="utf-8")
    env = os.environ.copy()
    env["USE_TF"] = "0"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "lgh.daemon",
            "--host",
            host,
            "--port",
            str(port),
            "--device",
            device,
        ],
        stdout=log,
        stderr=log,
        env=env,
        start_new_session=True,
    )
    daemon_pid_path().write_text(str(proc.pid), encoding="utf-8")
    for _ in range(50):
        if is_running():
            try:
                urllib.request.urlopen(f"http://{host}:{port}/health", timeout=0.2)
                return
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.2)
        else:
            time.sleep(0.2)


def stop() -> None:
    pid = _pid()
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    path = daemon_pid_path()
    if path.exists():
        path.unlink()
