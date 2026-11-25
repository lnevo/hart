"""Speed-match dashboard server (speedmatch/dashboard/server.py): loco info, the HTTP handler, the source choice.

The handler runs on a loopback port with a replayed log, and the live source gets a fetcher that is never called,
so nothing here uses ssh or the network beyond 127.0.0.1."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

DASH = Path(__file__).resolve().parents[1] / "speedmatch" / "dashboard"
sys.path.insert(0, str(DASH))
import dashsources as src  # noqa: E402
import server  # noqa: E402

T = 1794300000.0
LOG = ["%.3f RUN loco=2121 direction=forward" % T, "%.3f STEP 8" % (T + 1)]


class LocoInfo(unittest.TestCase):
    def test_model_comes_from_the_roster_file_and_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "2121.xml").write_text('<roster><locomotive id="CSX 2121" model="GP38-2"/></roster>')
            (Path(d) / "2738.xml").write_text('<roster><locomotive id="CSX 2738" model=""/></roster>')
            with mock.patch.object(server, "ROSTER_XML", Path(d)):
                self.assertEqual(server.loco_info("2121")["model"], "GP38-2")
                self.assertEqual(server.loco_info(2738)["model"], "Diesel locomotive")     # empty model
                self.assertEqual(server.loco_info("9999")["model"], "Diesel locomotive")   # no roster file

    def test_road_name_and_photo(self):
        with tempfile.TemporaryDirectory() as d:
            photos = Path(d)
            (photos / "2121.jpg").write_bytes(b"jpg")
            with mock.patch.object(server, "ROSTER_PHOTOS", photos):
                info = server.loco_info("2121")
                self.assertEqual((info["road"], info["photo"]), ("CSX 2121", "/roster/2121.jpg"))
                self.assertEqual(server.loco_info("4678")["road"], "CSX 4678")    # a number: CSX by default
                self.assertIsNone(server.loco_info("4678")["photo"])
                self.assertEqual(server.loco_info("NWR06")["road"], "NWR06")

    def test_the_roster_is_the_macs_jmri_user_files(self):
        sys.path.insert(0, str(src.REPO / "tools/hartlib/src"))
        from hartlib import paths
        self.assertEqual(server.ROSTER_XML, paths.JMRI_USER_FILES / "roster")


class Handler(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        photos = Path(self.tmp.name)
        (photos / "2121.jpg").write_bytes(b"\xff\xd8photo")
        patch = mock.patch.object(server, "ROSTER_PHOTOS", photos)
        patch.start()
        self.addCleanup(patch.stop)
        self.hub = server.Hub(src.ReplaySource([("a.log", LOG)], rate=1e6, clock=lambda: 0.0), 0.25)
        self.hub.poll_once()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(self.hub))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_state_is_the_hubs_snapshot_with_loco_details(self):
        code, headers, body = self.get("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Cache-Control"], "no-store")
        snap = json.loads(body)
        self.assertEqual(snap["mode"], "replay")
        self.assertIn("reference", snap)
        run = [r for r in snap["runs"] if r["loco"] == "2121"][0]
        self.assertEqual(run["photo"], "/roster/2121.jpg")
        self.assertIn("model", run)

    def test_state_takes_a_focus_run(self):
        with mock.patch.object(self.hub, "snapshot", wraps=self.hub.snapshot) as snap:
            self.assertEqual(self.get("/api/state?run=a.log")[0], 200)
        snap.assert_called_once_with("a.log")

    def test_static_files_and_the_index(self):
        code, headers, body = self.get("/")
        self.assertEqual((code, headers["Content-Type"]), (200, "text/html; charset=utf-8"))
        self.assertEqual(body, (server.STATIC / "index.html").read_bytes())
        code, headers, _ = self.get("/app.js")
        self.assertEqual((code, headers["Content-Type"]), (200, "text/javascript; charset=utf-8"))

    def test_roster_photos_are_served_and_nothing_outside_static(self):
        code, headers, body = self.get("/roster/2121.jpg")
        self.assertEqual((code, headers["Content-Type"], body), (200, "image/jpeg", b"\xff\xd8photo"))
        self.assertEqual(self.get("/roster/9999.jpg")[0], 404)
        self.assertEqual(self.get("/roster/../server.py")[0], 404)
        self.assertEqual(self.get("/%2e%2e/server.py")[0], 404)
        self.assertEqual(self.get("/missing.css")[0], 404)


class Sources(unittest.TestCase):
    def args(self, *argv):
        return argparse.Namespace(demo="--demo" in argv, replay=[a for a in argv if a.endswith(".log")] or None,
                                  rate=20.0, pi="otherpi" if "--pi" in argv else None)

    def test_demo_replay_and_live(self):
        self.assertEqual(server.build_source(self.args("--demo")).mode, "replay")
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "steprun_x.log"
            log.write_text("\n".join(LOG) + "\n")
            source = server.build_source(self.args(str(log)))
            self.assertEqual(source.mode, "replay")
            self.assertEqual(len(source.items), 2)
        with mock.patch.object(src, "ssh_fetcher", return_value=lambda cmd: b"") as fetcher:
            self.assertEqual(server.build_source(self.args("--pi")).mode, "live")
        fetcher.assert_called_once_with("otherpi")

    def test_main_serves_until_interrupted_and_stops_the_poller(self):
        made = {}

        class FakeServer:
            def __init__(self, addr, handler):
                made["addr"] = addr

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                made["closed"] = True

        with mock.patch.object(server, "ThreadingHTTPServer", FakeServer), \
                mock.patch.object(server.Hub, "run", lambda self: None), mock.patch("builtins.print"):
            server.main(["--demo", "--port", "9999"])
        self.assertEqual(made, {"addr": ("127.0.0.1", 9999), "closed": True})


if __name__ == "__main__":
    unittest.main()
