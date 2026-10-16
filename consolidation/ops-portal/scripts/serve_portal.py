#!/usr/bin/env python3
"""Serve consolidation tree + append-only F-root review log API."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

CONSOL = Path(__file__).resolve().parents[2]
LOG_PATH = CONSOL / "sor/desktop/f_root_review_log.jsonl"
API_LOG = "/api/f-root-review/log"


class PortalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(CONSOL), **kwargs)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == API_LOG:
            self._send_json(200, {"entries": _read_log()})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != API_LOG:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self.send_error(400, "Empty body")
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400, "Invalid JSON")
            return
        if not body.get("path"):
            self.send_error(400, "path required")
            return

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "path": body["path"],
            "action": body.get("action", "review"),
            "category": body.get("category", ""),
            "caption": body.get("caption", ""),
            "title": body.get("title", ""),
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._send_json(201, entry)

    def _send_json(self, code: int, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        req = args[0] if args else ""
        if API_LOG in str(req):
            return
        super().log_message(format, *args)


def _read_log() -> list[dict]:
    if not LOG_PATH.is_file():
        return []
    entries: list[dict] = []
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8760
    server = HTTPServer(("127.0.0.1", port), PortalHandler)
    print(f"HART portal → http://127.0.0.1:{port}/ops-portal/", flush=True)
    print(f"F-root review → http://127.0.0.1:{port}/ops-portal/review/f-root/", flush=True)
    print(f"Review log API → {API_LOG}", flush=True)
    print("(Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
