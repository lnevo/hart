"""The mimic's web side: the page, its shared style and render files, and the JSON API over one Bus.

    GET  /                      the page (lcos_mqtt_mimic.html)
    GET  /mimic.css, ...        the files shared with the JMRI-hosted page (shared_files)
    GET  /api/layout            the layout (mimic_records.Layout)
    GET  /api/state             what the broker has said so far (mimic_bus.State)
    GET  /api/events            a server-sent event stream of each change
    POST /api/occupancy         {"addr", "state"}: set one detector
    POST /api/turnout           {"addr", "state"}: set one switch's status (and its feedback sensors)
    POST /api/occupancy/clear   set every detector INACTIVE
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from mimic_bus import Bus
from mimic_records import Layout


def make_handler(layout: Layout, bus: Bus, html: bytes, shared_web: Path,
                 shared_files: Mapping[str, str]) -> type[BaseHTTPRequestHandler]:
    """The request handler class for one server: `html` at /, each of shared_files (URL path -> content type) read
    from shared_web on each request, and the API over layout and bus."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            if "GET /api/events" in (format % args):
                return
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

        def _json(self, code: int, obj: object) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, object]:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            body = json.loads(raw.decode() or "{}")
            if not isinstance(body, dict):
                raise ValueError("the request body is not a JSON object")
            return body

        def _events(self) -> None:
            """The event stream: a hello, then each Bus event, with a ping after 20 s of quiet."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = bus.add_sub()
            try:
                self.wfile.write(b"data: " + json.dumps({"type": "hello"}).encode() + b"\n\n")
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=20)
                        self.wfile.write(b"data: " + msg.encode() + b"\n\n")
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                bus.drop_sub(q)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            if path in shared_files:
                body = (shared_web / path.lstrip("/")).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", shared_files[path])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/api/layout":
                self._json(200, layout)
                return
            if path == "/api/state":
                self._json(200, bus.snapshot())
                return
            if path == "/api/events":
                self._events()
                return
            self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                body = self._read_json()
                if path == "/api/occupancy":
                    bus.set_occupancy(str(body["addr"]), str(body["state"]))
                    self._json(200, {"ok": True})
                    return
                if path == "/api/turnout":
                    bus.set_turnout(layout, str(body["addr"]), str(body["state"]))
                    self._json(200, {"ok": True})
                    return
                if path == "/api/occupancy/clear":
                    bus.clear_occupancy(layout)
                    self._json(200, {"ok": True})
                    return
            except (KeyError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as e:
                self._json(400, {"ok": False, "error": str(e)})
                return
            self.send_error(404)

    return Handler
