from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from lgh.eval.labels import LabelError, append_labels, load_skips, save_skips
from lgh.resources import read_package_text
from lgh.review.queue import ReviewStore
from lgh.teacher import TeacherError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770
MAX_BULK = 200
LABEL_FIELDS = (
    "source",
    "task_alignment",
    "destructive_risk",
    "sensitive_resource",
    "external_impact",
    "reversibility",
    "verification_needed",
    "handling",
)


def _trace_ids(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("trace_ids")
    if raw is None:
        one = str(payload.get("trace_id") or "").strip()
        return [one] if one else []
    if not isinstance(raw, list):
        raise LabelError("trace_ids must be a list")
    ids: list[str] = []
    seen: set[str] = set()
    for item in raw:
        trace_id = str(item or "").strip()
        if not trace_id or trace_id in seen:
            continue
        seen.add(trace_id)
        ids.append(trace_id)
    return ids


def _label_answers(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key) for key in LABEL_FIELDS}


def make_handler(
    store: ReviewStore,
    teacher: Any | None = None,
) -> type[BaseHTTPRequestHandler]:
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
            if path == "/api/config":
                self._json(
                    200,
                    {
                        "propose": teacher is not None,
                        "teacher": getattr(teacher, "kind", None) if teacher else None,
                        "model": getattr(teacher, "model", None) if teacher else None,
                        "provider": getattr(teacher, "provider", None) if teacher else None,
                    },
                )
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
            if path == "/api/propose":
                self._propose(payload)
                return
            if path in {"/api/labels", "/api/labels/bulk"}:
                self._labels(payload)
                return
            if path == "/api/skip":
                self._skip(payload)
                return
            if path == "/api/unskip":
                trace_id = str(payload.get("trace_id") or "").strip()
                skipped = load_skips(store.data_dir)
                skipped.discard(trace_id)
                save_skips(skipped, store.data_dir)
                self._json(200, {"ok": True, "skipped": False})
                return
            self._json(404, {"error": "not found"})

        def _labels(self, payload: dict[str, Any]) -> None:
            try:
                ids = _trace_ids(payload)
            except LabelError as exc:
                self._json(400, {"error": str(exc)})
                return
            if not ids:
                self._json(400, {"error": "trace_id is required"})
                return
            if len(ids) > MAX_BULK:
                self._json(400, {"error": f"at most {MAX_BULK} traces per save"})
                return
            by_id = {row["traceId"]: row for row in store.items()}
            missing = [tid for tid in ids if tid not in by_id]
            if missing:
                self._json(404, {"error": "trace not found: " + ", ".join(missing[:8])})
                return
            no_state = [tid for tid in ids if not by_id[tid].get("hasState")]
            if no_state:
                self._json(400, {"error": "trace has no state: " + ", ".join(no_state[:8])})
                return
            answers = _label_answers(payload)
            records = [{"trace_id": tid, **answers} for tid in ids]
            try:
                saved = append_labels(records, directory=store.data_dir)
            except LabelError as exc:
                self._json(400, {"error": str(exc)})
                return
            skipped = load_skips(store.data_dir)
            changed = False
            for record in saved:
                if record["trace_id"] in skipped:
                    skipped.remove(record["trace_id"])
                    changed = True
            if changed:
                save_skips(skipped, store.data_dir)
            self._json(200, {"ok": True, "count": len(saved), "labels": saved, "label": saved[0]})

        def _skip(self, payload: dict[str, Any]) -> None:
            try:
                ids = _trace_ids(payload)
            except LabelError as exc:
                self._json(400, {"error": str(exc)})
                return
            if not ids:
                self._json(400, {"error": "trace_id is required"})
                return
            if len(ids) > MAX_BULK:
                self._json(400, {"error": f"at most {MAX_BULK} traces per skip"})
                return
            skipped = load_skips(store.data_dir)
            skipped.update(ids)
            save_skips(skipped, store.data_dir)
            self._json(200, {"ok": True, "skipped": True, "count": len(ids), "trace_ids": ids})

        def _propose(self, payload: dict[str, Any]) -> None:
            if teacher is None:
                self._json(400, {"error": "proposals are disabled; start with lgh review --propose"})
                return
            trace_id = str(payload.get("trace_id") or "").strip()
            if not trace_id:
                self._json(400, {"error": "trace_id is required"})
                return
            item = store.payload(trace_id)
            if item is None:
                self._json(404, {"error": "trace not found"})
                return
            state = item.get("state")
            if not state:
                self._json(400, {"error": "trace has no state"})
                return
            try:
                proposal = teacher.propose(state, item.get("questions"))
            except TeacherError as exc:
                self._json(502, {"error": str(exc)})
                return
            self._json(200, {"ok": True, "trace_id": trace_id, **proposal})

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
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The browser closed the socket before the reply landed
                # (page reload or trace switch while a slow teacher call was
                # in flight). Nothing to recover; the label was never written.
                self.close_connection = True

    return Handler


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    traces_dir: Path | None = None,
    data_dir: Path | None = None,
    open_browser: bool = True,
    teacher: Any | None = None,
) -> None:
    import webbrowser

    store = ReviewStore(traces_dir=traces_dir, data_dir=data_dir)
    httpd = ThreadingHTTPServer((host, port), make_handler(store, teacher=teacher))
    url = f"http://{host}:{port}/"
    print(f"LGH review UI at {url}", flush=True)
    if teacher is not None:
        model = getattr(teacher, "model", "llm")
        print(f"Teacher proposals on ({model}). Suggestions fill the form; Save still labels as human.", flush=True)
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
