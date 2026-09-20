import json
from unittest.mock import patch

from lgh.daemon import (
    LAYA_INSTALL_HINT,
    DaemonError,
    _read_health,
    endpoint_from_url,
    laya_installed,
    start,
)


def test_endpoint_from_url() -> None:
    assert endpoint_from_url("http://127.0.0.1:8765") == ("127.0.0.1", 8765)
    assert endpoint_from_url("http://localhost:9001/") == ("localhost", 9001)


def test_start_refuses_foreign_listener() -> None:
    with (
        patch("lgh.daemon.is_running", return_value=False),
        patch("lgh.daemon._read_health", return_value=None),
        patch("lgh.daemon._port_open", return_value=True),
        patch("lgh.daemon._port_owner", return_value="python3 -m http.server"),
        patch("lgh.daemon.laya_installed", return_value=True),
    ):
        try:
            start(port=8765)
        except DaemonError as exc:
            assert "not an LGH daemon" in str(exc)
            assert "daemon_url" in str(exc)
        else:
            raise AssertionError("expected DaemonError")


def test_laya_installed_matches_find_spec() -> None:
    assert laya_installed() is False or laya_installed() is True


def test_start_without_laya_is_explicit() -> None:
    with (
        patch("lgh.daemon.laya_installed", return_value=False),
        patch("lgh.daemon.is_running", return_value=False),
        patch("lgh.daemon._read_health", return_value=None),
        patch("lgh.daemon._port_open", return_value=False),
    ):
        try:
            start()
        except DaemonError as exc:
            assert "--extra laya" in str(exc)
            assert "uv sync" in str(exc)
        else:
            raise AssertionError("expected DaemonError")
    assert "Laya is not installed" in LAYA_INSTALL_HINT


def test_read_health_swallows_disconnect() -> None:
    class Boom(ConnectionError):
        pass

    with patch("urllib.request.urlopen", side_effect=Boom("closed")):
        assert _read_health("127.0.0.1", 8765) is None


def test_read_health_parses_json() -> None:
    class Resp:
        def read(self) -> bytes:
            return json.dumps({"ok": True, "loading": False}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=Resp()):
        health = _read_health("127.0.0.1", 8765)
    assert health == {"ok": True, "loading": False}
