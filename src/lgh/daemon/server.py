from __future__ import annotations

import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

os.environ.setdefault("USE_TF", "0")

MODEL_ID = "convaiinnovations/laya-typed-decisions"
_AGENT: Any = None
_LOADED_AT: str | None = None
_MODEL = MODEL_ID
_LOAD_ERROR: str | None = None
_LOADING = False

# Config/docs historically used "gpu"; torch.device() wants "cuda".
_DEVICE_ALIASES = {"gpu": "cuda"}


def resolve_device(device: str) -> str:
    key = device.strip().lower()
    return _DEVICE_ALIASES.get(key, key)


def load_agent(model: str = MODEL_ID, device: str = "cpu") -> Any:
    global _AGENT, _LOADED_AT, _MODEL, _LOAD_ERROR, _LOADING
    if _AGENT is not None:
        return _AGENT
    _LOADING = True
    os.environ["USE_TF"] = "0"
    try:
        import laya  # type: ignore[import-untyped]

        _AGENT = laya.load(model, device=resolve_device(device))
        _MODEL = model
        _LOADED_AT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _LOAD_ERROR = None
        return _AGENT
    except Exception as exc:
        _LOAD_ERROR = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _LOADING = False


def health_payload() -> dict[str, Any]:
    return {
        "ok": _AGENT is not None,
        "loading": _LOADING and _AGENT is None,
        "error": _LOAD_ERROR,
        "model": _MODEL,
        "loadedAt": _LOADED_AT,
        "tokenizer": _AGENT is not None,
    }


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server_version = "lgh-daemon/0.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/health":
            _json_response(self, 404, {"error": "not found"})
            return
        payload = health_payload()
        _json_response(self, 200, payload)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "invalid json"})
            return
        path = self.path.split("?", 1)[0]
        if path == "/tokens":
            text = json.dumps(payload.get("state") or payload)
            tokens = max(1, (len(text) + 3) // 4)
            if _AGENT is not None:
                tokenizer = getattr(_AGENT, "tokenizer", None) or getattr(_AGENT, "tok", None)
                if tokenizer is not None and hasattr(tokenizer, "encode"):
                    try:
                        tokens = len(tokenizer.encode(text))
                    except Exception:
                        pass
            _json_response(self, 200, {"tokens": tokens})
            return
        if path != "/predict":
            _json_response(self, 404, {"error": "not found"})
            return
        if _LOAD_ERROR:
            _json_response(self, 503, {"error": _LOAD_ERROR})
            return
        if _AGENT is None:
            _json_response(self, 503, {"error": "model still loading"})
            return
        try:
            agent = load_agent()
            started = time.perf_counter()
            result = agent.predict(payload.get("state") or {}, payload.get("questions") or {})
            latency_ms = (time.perf_counter() - started) * 1000.0
            body = dict(result) if isinstance(result, dict) else {"answers": result}
            body["latency_ms"] = latency_ms
            body["model"] = _MODEL
            _json_response(self, 200, body)
        except Exception as exc:
            _json_response(
                self,
                500,
                {"error": str(exc), "trace": traceback.format_exc()[-1500:]},
            )


def serve(host: str = "127.0.0.1", port: int = 8765, preload: bool = True, device: str = "cpu") -> None:
    if preload:
        threading.Thread(
            target=_preload,
            kwargs={"device": device},
            name="lgh-laya-load",
            daemon=True,
        ).start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()


def _preload(device: str = "cpu") -> None:
    try:
        load_agent(device=device)
    except Exception:
        traceback.print_exc()
