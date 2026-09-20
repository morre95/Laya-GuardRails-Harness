import json
from unittest.mock import patch

from lgh.daemon import LAYA_INSTALL_HINT, DaemonError, _read_health, laya_installed, start


def test_laya_installed_matches_find_spec() -> None:
    assert laya_installed() is False or laya_installed() is True


def test_start_without_laya_is_explicit() -> None:
    with patch("lgh.daemon.laya_installed", return_value=False):
        with patch("lgh.daemon.is_running", return_value=False):
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
