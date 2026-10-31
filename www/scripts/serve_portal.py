#!/usr/bin/env python3
"""Serve the website tree + F-root review log API + archive bucket API."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = ROOT / "www/review-data/f_root_review_log.jsonl"
API_LOG = "/api/f-root-review/log"
ARCHIVE_PATH = ROOT / "www/data/archive.json"
ARCHIVE_LOG = ROOT / "www/review-data/archive_review_log.jsonl"
API_ARCHIVE = "/api/archive/item"
API_ARCHIVE_PING = "/api/archive/ping"
API_ARCHIVE_TO_LAYOUT = "/api/archive/to-layout"
API_GALLERY = "/api/gallery/item"
API_GALLERY_PING = "/api/gallery/ping"
GALLERY_PATH = ROOT / "www/data/gallery.json"
ARCHIVE_BUCKETS = {"curated", "review", "discard"}
ARCHIVE_KINDS = {"photo", "ad", "clipping", "map", "document", "graphic"}
ARCHIVE_CONFIDENCE = {"verified", "likely", "none"}
ARCHIVE_TEXT_FIELDS = ("title", "caption", "date", "credit", "source_url", "reason", "rights")
LOCAL_NAMES = {"127.0.0.1", "localhost", "[::1]"}
SERVED_ROOTS = {"www", "external", "media", "ops"}


class PortalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _servable_path(self) -> bool:
        """Serve only the website and its media; the repo root holds .env.local and .git."""
        parts = [p for p in unquote(urlsplit(self.path).path).split("/") if p]
        if not parts or parts[0] not in SERVED_ROOTS or any(p.startswith(".") for p in parts):
            self.send_error(404, "Not found")
            return False
        return True

    def _local_host(self) -> bool:
        """Refuse requests whose Host is not this machine (DNS rebinding reads the whole tree)."""
        host = (self.headers.get("Host") or "").strip().lower()
        name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]", 1)[0] + "]"
        if name in LOCAL_NAMES:
            return True
        self.send_error(403, "Local requests only")
        return False

    def _same_origin_json(self) -> bool:
        """Edits must come from a portal page here: JSON body and a local Origin.

        Requiring application/json forces a CORS preflight that this server never
        answers, so another site open in the browser cannot post edits.
        """
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            self.send_error(415, "Expected application/json")
            return False
        origin = urlsplit(self.headers.get("Origin") or "")
        if origin.scheme != "http" or (origin.hostname or "") not in LOCAL_NAMES:
            self.send_error(403, "Cross-origin edits refused")
            return False
        return True

    def do_HEAD(self) -> None:
        if self._local_host():
            super().do_HEAD()

    def do_GET(self) -> None:
        if not self._local_host():
            return
        if not self._servable_path():
            return
        route = self.path.split("?", 1)[0]
        if route == API_LOG:
            self._send_json(200, {"entries": _read_log()})
            return
        if route in (API_ARCHIVE_PING, API_GALLERY_PING):
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
        if not (self._local_host() and self._same_origin_json()):
            return
        route = self.path.split("?", 1)[0]
        if route == API_ARCHIVE:
            body = self._read_body()
            if body is not None:
                code, payload = _update_archive_item(body)
                self._send_json(code, payload)
            return
        if route == API_GALLERY:
            body = self._read_body()
            if body is not None:
                code, payload = _update_gallery_item(body)
                self._send_json(code, payload)
            return
        if route == API_ARCHIVE_TO_LAYOUT:
            body = self._read_body()
            if body is not None:
                code, payload = _move_archive_item_to_layout(body)
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
    url = changes.get("source_url")
    if url and urlsplit(url).scheme not in ("http", "https"):
        return 400, {"error": "source_url must be an http(s) link"}
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


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _move_archive_item_to_layout(body: dict) -> tuple[int, dict]:
    """Move an archive item into the Layout photos gallery (data/gallery.json, album "layout")."""
    item_id = str(body.get("id") or "")
    if not item_id:
        return 400, {"error": "id required"}
    data = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    items = data.get("items", [])
    item = next((it for it in items if it.get("id") == item_id), None)
    if item is None:
        return 404, {"error": f"no archive item {item_id}"}
    gallery = json.loads(GALLERY_PATH.read_text(encoding="utf-8"))
    g_items = gallery.setdefault("items", [])
    if not any(g.get("src") == item.get("src") for g in g_items):
        g_items.append(
            {
                "album": "layout",
                "src": item.get("src"),
                "title": item.get("title") or "",
                "caption": item.get("caption") or "",
                "credit": item.get("credit") or "HART layout photos",
            }
        )
    for album in gallery.get("albums", []):
        album["count"] = sum(1 for g in g_items if g.get("album") == album.get("id"))
    data["items"] = [it for it in items if it.get("id") != item_id]
    _write_json_atomic(GALLERY_PATH, gallery)
    _write_json_atomic(ARCHIVE_PATH, data)
    ARCHIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVE_LOG.open("a", encoding="utf-8") as fh:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "id": item_id, "before": {"bucket": item.get("bucket")}, "after": {"moved_to": "layout-photos"}}
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 200, {"moved": item_id}


def _update_gallery_item(body: dict) -> tuple[int, dict]:
    """Curate the layout-room gallery (data/gallery.json): album, text, order, or send back to Photos."""
    src = str(body.get("src") or "")
    if not src:
        return 400, {"error": "src required"}
    gallery = json.loads(GALLERY_PATH.read_text(encoding="utf-8"))
    items = gallery.setdefault("items", [])
    idx = next((i for i, it in enumerate(items) if it.get("src") == src), None)
    if idx is None:
        return 404, {"error": f"no gallery item {src}"}
    item = items[idx]
    before = {k: item.get(k) for k in ("album", "title", "caption")}
    after: dict = {}

    if body.get("to_archive"):
        # Back to the Photos archive's To review tab, where it can be curated or discarded.
        data = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        ids = {it.get("id") for it in data.get("items", [])}
        base = "layout-" + "".join(c if c.isalnum() else "-" for c in Path(src).stem.lower()).strip("-")
        new_id, n = base, 2
        while new_id in ids:
            new_id, n = f"{base}-{n}", n + 1
        data.setdefault("items", []).append(
            {
                "id": new_id,
                "src": src,
                "bucket": "review",
                "kind": "photo",
                "title": item.get("title") or "",
                "caption": item.get("caption") or "",
                "date": "",
                "tags": [],
                "credit": item.get("credit") or "",
                "source_url": "",
                "credit_confidence": "none",
                "rights": "",
                "reason": "Sent back from the layout room gallery.",
            }
        )
        del items[idx]
        after = {"moved_to": "photos-review", "id": new_id}
        _write_json_atomic(ARCHIVE_PATH, data)
    else:
        albums = {a.get("id") for a in gallery.get("albums", [])}
        if "album" in body:
            if body["album"] not in albums:
                return 400, {"error": "unknown album"}
            item["album"] = after["album"] = body["album"]
        for field in ("title", "caption"):
            if field in body:
                item[field] = after[field] = str(body[field] or "").strip()
        move = body.get("move")
        if move in ("up", "down"):
            # Swap with the neighbouring item in the same album.
            same = [i for i, it in enumerate(items) if it.get("album") == item.get("album")]
            pos = same.index(idx)
            other = pos - 1 if move == "up" else pos + 1
            if 0 <= other < len(same):
                j = same[other]
                items[idx], items[j] = items[j], items[idx]
            after["move"] = move
        if not after:
            return 400, {"error": "nothing to change"}

    for album in gallery.get("albums", []):
        album["count"] = sum(1 for g in items if g.get("album") == album.get("id"))
    _write_json_atomic(GALLERY_PATH, gallery)
    ARCHIVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVE_LOG.open("a", encoding="utf-8") as fh:
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "gallery_src": src, "before": before, "after": after}
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 200, {"gallery": gallery}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", type=int, default=8760, help="port on 127.0.0.1 (default %(default)s)")
    port = parser.parse_args().port
    server = HTTPServer(("127.0.0.1", port), PortalHandler)
    print(f"HART portal → http://127.0.0.1:{port}/www/", flush=True)
    print(f"F-root review → http://127.0.0.1:{port}/www/review/f-root/", flush=True)
    print(f"Archive → http://127.0.0.1:{port}/www/archive/ (edits save to data/archive.json)", flush=True)
    print(f"Review log API → {API_LOG}", flush=True)
    print("(Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
