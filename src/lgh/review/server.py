from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lgh.eval.labels import LabelError, append_label, load_skips, save_skips
from lgh.resources import read_package_text
from lgh.review.queue import ReviewStore

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770


def make_handler(store: ReviewStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "lgh-review/0.1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                body = read_package_text("review", "page.html").encode("utf-8")
                self._send(200, body, "text/html; charset=utf-8")
                return
            if path == "/api/queue":
                rows = store.items()
                self._json(200, {"counts": store.counts(rows), "items": rows})
                return
            if path.startswith("/api/traces/"):
                trace_id = path.removeprefix("/api/traces/").strip("/")
                payload = store.payload(trace_id)
                if payload is None:
                    self._json(404, {"error": "trace not found"})
                    return
                self._json(200, payload)
                return
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid json"})
                return
            if path == "/api/labels":
                try:
                    record = append_label(payload, directory=store.data_dir)
                except LabelError as exc:
                    self._json(400, {"error": str(exc)})
                    return
                skipped = load_skips(store.data_dir)
                if record["trace_id"] in skipped:
                    skipped.remove(record["trace_id"])
                    save_skips(skipped, store.data_dir)
                self._json(200, {"ok": True, "label": record})
                return
            if path == "/api/skip":
                trace_id = str(payload.get("trace_id") or "").strip()
                if not trace_id:
                    self._json(400, {"error": "trace_id is required"})
                    return
                skipped = load_skips(store.data_dir)
                skipped.add(trace_id)
                save_skips(skipped, store.data_dir)
                self._json(200, {"ok": True, "skipped": True})
                return
            if path == "/api/unskip":
                trace_id = str(payload.get("trace_id") or "").strip()
                skipped = load_skips(store.data_dir)
                skipped.discard(trace_id)
                save_skips(skipped, store.data_dir)
                self._json(200, {"ok": True, "skipped": False})
                return
            self._json(404, {"error": "not found"})

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise json.JSONDecodeError("object required", raw.decode("utf-8"), 0)
            return data

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._send(status, body, "application/json")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    traces_dir: Path | None = None,
    data_dir: Path | None = None,
    open_browser: bool = True,
) -> None:
    import webbrowser

    store = ReviewStore(traces_dir=traces_dir, data_dir=data_dir)
    httpd = ThreadingHTTPServer((host, port), make_handler(store))
    url = f"http://{host}:{port}/"
    print(f"LGH review UI at {url}", flush=True)
    print("Old traces without state cannot be labeled. New hook events store redacted LayaState.", flush=True)
    print("Ctrl-C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
