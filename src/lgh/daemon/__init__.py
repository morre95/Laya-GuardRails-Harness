from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from lgh.paths import daemon_log_path, daemon_pid_path, user_state_dir

LAYA_INSTALL_HINT = (
    "Laya is not installed in this environment.\n"
    "`uv sync --extra dev` without `--extra laya` removes the daemon extra.\n"
    "Install it, then start again:\n"
    "  uv sync --extra dev --extra laya\n"
    "  USE_TF=0 uv run lgh daemon start"
)

_HEALTH_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    ConnectionError,
    OSError,
)


class DaemonError(Exception):
    """Raised when the Laya daemon cannot start or stay healthy."""


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


def laya_installed() -> bool:
    return importlib.util.find_spec("laya") is not None


def _log_tail(lines: int = 40) -> str:
    path = daemon_log_path()
    if not path.is_file():
        return "(no daemon log yet)"
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(text[-lines:]) or "(daemon log empty)"


def _read_health(host: str, port: int, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except _HEALTH_ERRORS:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "raw": raw}
    return data if isinstance(data, dict) else {"ok": False, "raw": raw}


def status_text(host: str = "127.0.0.1", port: int = 8765) -> str:
    running = is_running()
    health = _read_health(host, port) or {"ok": False, "error": "unreachable"}
    return f"running={running} pid={_pid()} health={json.dumps(health, ensure_ascii=False)}"


def start(
    host: str = "127.0.0.1",
    port: int = 8765,
    device: str = "cpu",
    timeout: float = 180.0,
) -> None:
    if is_running() and (_read_health(host, port) or {}).get("ok"):
        return
    if is_running() and not (_read_health(host, port) or {}).get("ok"):
        stop()
    if not laya_installed():
        raise DaemonError(LAYA_INSTALL_HINT)
    user_state_dir().mkdir(parents=True, exist_ok=True)
    log_path = daemon_log_path()
    log = log_path.open("a", encoding="utf-8")
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
    deadline = time.monotonic() + timeout
    last_health: dict | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise DaemonError(
                "Laya daemon exited before becoming healthy.\n"
                f"log: {log_path}\n{_log_tail()}"
            )
        last_health = _read_health(host, port, timeout=0.5)
        if last_health and last_health.get("error"):
            stop()
            raise DaemonError(
                "Laya daemon failed to load the model.\n"
                f"{last_health.get('error')}\n"
                f"log: {log_path}\n{_log_tail()}"
            )
        if last_health and last_health.get("ok"):
            return
        time.sleep(0.4)
    stop()
    raise DaemonError(
        "Timed out waiting for the Laya daemon to load the model.\n"
        f"last health={last_health}\nlog: {log_path}\n{_log_tail()}"
    )


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
