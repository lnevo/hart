"""mimic_http.py: the mimic's page and API, served on this machine's loopback over a fake bus (no broker, nothing
published)."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mimic_http as MH  # noqa: E402

LAYOUT = {"blocks": [{"addr": "100"}], "turnouts": [], "heads": []}


class FakeBus:
    """What the handler asks of a Bus, recorded; set_turnout refuses a state as Bus does."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def snapshot(self) -> dict[str, object]:
        return {"mqtt": {"host": "fake", "connected": False}, "sensors": {}, "turnouts": {}, "heads": {}}

    def set_occupancy(self, addr: str, state: str) -> None:
        self.calls.append(("occupancy", addr, state))

    def set_turnout(self, layout: object, addr: str, state: str) -> None:
        raise ValueError("turnout must be CLOSED or THROWN")

    def clear_occupancy(self, layout: object) -> None:
        self.calls.append(("clear",))


class Api(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        web = Path(tmp.name)
        (web / "mimic.css").write_text("body {}\n", encoding="utf-8")
        self.bus = FakeBus()
        handler = MH.make_handler(LAYOUT, self.bus, b"<html></html>", web,  # type: ignore[arg-type]
                                  {"/mimic.css": "text/css; charset=utf-8"})
        handler.log_message = lambda *a: None  # type: ignore[method-assign]
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def get(self, path: str) -> tuple[int, str, bytes]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                return r.status, r.headers["Content-Type"], r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers["Content-Type"], e.read()

    def post(self, path: str, body: object) -> tuple[int, object]:
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null") if e.code == 400 else None

    def test_the_page_its_shared_files_and_the_layout(self) -> None:
        self.assertEqual(self.get("/"), (200, "text/html; charset=utf-8", b"<html></html>"))
        self.assertEqual(self.get("/mimic.css"), (200, "text/css; charset=utf-8", b"body {}\n"))
        status, kind, body = self.get("/api/layout")
        self.assertEqual((status, kind, json.loads(body)), (200, "application/json", LAYOUT))
        self.assertEqual(json.loads(self.get("/api/state")[2])["mqtt"], {"host": "fake", "connected": False})
        self.assertEqual(self.get("/nothing")[0], 404)

    def test_posts_reach_the_bus_and_a_refusal_is_a_400(self) -> None:
        self.assertEqual(self.post("/api/occupancy", {"addr": "100", "state": "ACTIVE"}), (200, {"ok": True}))
        self.assertEqual(self.post("/api/occupancy/clear", {}), (200, {"ok": True}))
        self.assertEqual(self.bus.calls, [("occupancy", "100", "ACTIVE"), ("clear",)])
        self.assertEqual(self.post("/api/turnout", {"addr": "7", "state": "open"}),
                         (400, {"ok": False, "error": "turnout must be CLOSED or THROWN"}))
        self.assertEqual(self.post("/api/occupancy", {"addr": "100"}), (400, {"ok": False, "error": "'state'"}))
        self.assertEqual(self.post("/api/occupancy", ["not", "an", "object"]),
                         (400, {"ok": False, "error": "the request body is not a JSON object"}))
        self.assertEqual(self.post("/api/nothing", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
