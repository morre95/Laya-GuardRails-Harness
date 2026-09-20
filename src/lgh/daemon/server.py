from __future__ import annotations

import json
import os
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

os.environ.setdefault("USE_TF", "0")

MODEL_ID = "convaiinnovations/laya-typed-decisions"
_AGENT: Any = None
_LOADED_AT: str | None = None
_MODEL = MODEL_ID


def load_agent(model: str = MODEL_ID, device: str = "cpu") -> Any:
    global _AGENT, _LOADED_AT, _MODEL
    if _AGENT is not None:
        return _AGENT
    os.environ["USE_TF"] = "0"
    import laya  # type: ignore[import-untyped]

    _AGENT = laya.load(model)
    _MODEL = model
    _LOADED_AT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return _AGENT


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
        _json_response(
            self,
            200,
            {
                "ok": _AGENT is not None,
                "model": _MODEL,
                "loadedAt": _LOADED_AT,
                "tokenizer": True,
            },
        )

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
        load_agent(device=device)
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()
