#!/usr/bin/env python3
"""Serve consolidation tree + F-root review log API + archive bucket API."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

CONSOL = Path(__file__).resolve().parents[2]
LOG_PATH = CONSOL / "sor/desktop/f_root_review_log.jsonl"
API_LOG = "/api/f-root-review/log"
ARCHIVE_PATH = CONSOL / "ops-portal/data/archive.json"
ARCHIVE_LOG = CONSOL / "sor/desktop/archive_review_log.jsonl"
API_ARCHIVE = "/api/archive/item"
API_ARCHIVE_PING = "/api/archive/ping"
ARCHIVE_BUCKETS = {"curated", "review", "discard"}
ARCHIVE_KINDS = {"photo", "ad", "clipping", "map", "document"}
ARCHIVE_CONFIDENCE = {"verified", "likely", "none"}
ARCHIVE_TEXT_FIELDS = ("title", "caption", "date", "credit", "source_url", "reason", "rights")


class PortalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(CONSOL), **kwargs)

    def do_GET(self) -> None:
        route = self.path.split("?", 1)[0]
        if route == API_LOG:
            self._send_json(200, {"entries": _read_log()})
            return
        if route == API_ARCHIVE_PING:
            self._send_json(200, {"ok": True})
            return
        super().do_GET()

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self.send_error(400, "Empty body")
            return None
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400, "Invalid JSON")
            return None
        if not isinstance(body, dict):
            self.send_error(400, "Expected a JSON object")
            return None
        return body

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0]
        if route == API_ARCHIVE:
            body = self._read_body()
            if body is not None:
                code, payload = _update_archive_item(body)
                self._send_json(code, payload)
            return
        if route != API_LOG:
            self.send_error(404)
            return
        body = self._read_body()
        if body is None:
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
        if API_LOG in str(req) or "/api/archive/" in str(req):
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


def _update_archive_item(body: dict) -> tuple[int, dict]:
    """Apply an owner edit (bucket move, caption fix) to data/archive.json and log it."""
    item_id = str(body.get("id") or "")
    if not item_id:
        return 400, {"error": "id required"}
    changes: dict = {}
    if "bucket" in body:
        if body["bucket"] not in ARCHIVE_BUCKETS:
            return 400, {"error": "bucket must be curated, review, or discard"}
        changes["bucket"] = body["bucket"]
    if "kind" in body:
        if body["kind"] not in ARCHIVE_KINDS:
            return 400, {"error": "unknown kind"}
        changes["kind"] = body["kind"]
    if "credit_confidence" in body:
        if body["credit_confidence"] not in ARCHIVE_CONFIDENCE:
            return 400, {"error": "credit_confidence must be verified, likely, or none"}
        changes["credit_confidence"] = body["credit_confidence"]
    for field in ARCHIVE_TEXT_FIELDS:
        if field in body:
            changes[field] = str(body[field] or "").strip()
    if "tags" in body:
        tags = body["tags"]
        if isinstance(tags, str):
            tags = tags.split(",")
        changes["tags"] = [str(t).strip() for t in tags if str(t).strip()]
    if not changes:
        return 400, {"error": "nothing to change"}

    # HTTPServer is single-threaded, so read-modify-write here cannot interleave.
    data = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    item = next((it for it in data.get("items", []) if it.get("id") == item_id), None)
    if item is None:
        return 404, {"error": f"no archive item {item_id}"}
    before = {k: item.get(k) for k in changes}
    item.update(changes)
    tmp = ARCHIVE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, ARCHIVE_PATH)
    ARCHIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVE_LOG.open("a", encoding="utf-8") as fh:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "id": item_id, "before": before, "after": changes}
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 200, {"item": item}


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8760
    server = HTTPServer(("127.0.0.1", port), PortalHandler)
    print(f"HART portal → http://127.0.0.1:{port}/ops-portal/", flush=True)
    print(f"F-root review → http://127.0.0.1:{port}/ops-portal/review/f-root/", flush=True)
    print(f"Archive → http://127.0.0.1:{port}/ops-portal/archive/ (edits save to data/archive.json)", flush=True)
    print(f"Review log API → {API_LOG}", flush=True)
    print("(Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
