#!/usr/bin/env python3
"""Live dashboard for speed-matching runs. Python 3 standard library only.

    python3 server.py                       watch the Pi (ssh host from HART_PI_SSH, default "pi")
    python3 server.py --demo                synthetic runs for CSX 2121 and 2738
    python3 server.py --replay a.log b.log --rate 20

Then open http://127.0.0.1:8765/. Read only toward the Pi: ls, stat and tail over ssh.
Nothing is sent to JMRI, the layout or MQTT.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import dashsources as sources
import dashstate as state

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
ROSTER_PHOTOS = sources.REPO / "jmri/resources/roster"
ROSTER_XML = Path(os.path.expanduser("~/JMRI_UserFiles/roster"))
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".jpg": "image/jpeg", ".svg": "image/svg+xml"}


def loco_info(loco):
    """{road, model, photo} for a roster id; model from the roster file when it has one."""
    loco = str(loco)
    model = None
    try:
        m = re.search(r'<locomotive[^>]*\smodel="([^"]*)"', (ROSTER_XML / (loco + ".xml")).read_text(errors="replace"))
        model = m.group(1) if m and m.group(1) else None
    except OSError:
        pass
    photo = "/roster/%s.jpg" % loco if (ROSTER_PHOTOS / (loco + ".jpg")).exists() else None
    return {"road": state.LOCO_ROAD.get(loco, "CSX " + loco if loco.isdigit() else loco),
            "model": model or "Diesel locomotive", "photo": photo}


class Hub:
    def __init__(self, source, interval):
        self.source = source
        self.interval = interval
        self.store = state.Store()
        self.ok, self.message = True, None
        self.reference = sources.reference_curves()
        self._info = {}
        self.stop = threading.Event()

    def run(self):
        while not self.stop.is_set():
            self.ok, self.message = self.source.poll(self.store)
            self.stop.wait(self.interval)

    def snapshot(self):
        now = time.time() if self.source.mode == "live" else self.source.now
        snap = self.store.snapshot(now, self.ok, self.message, self.source.mode)
        for r in snap["runs"]:
            if r["loco"] is not None:
                if r["loco"] not in self._info:
                    self._info[r["loco"]] = loco_info(r["loco"])
                r.update({k: self._info[r["loco"]][k] for k in ("model", "photo")})
        snap["reference"] = self.reference
        return snap


def make_handler(hub):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/state":
                return self.send(200, json.dumps(hub.snapshot()).encode(), "application/json")
            if path == "/":
                path = "/index.html"
            m = re.fullmatch(r"/roster/(\w+)\.jpg", path)
            if m:
                f = ROSTER_PHOTOS / (m.group(1) + ".jpg")
            else:
                f = (STATIC / path.lstrip("/")).resolve()
                if STATIC.resolve() not in f.parents:
                    return self.send(404, b"not found", "text/plain")
            if not f.is_file():
                return self.send(404, b"not found", "text/plain")
            self.send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))

    return H


def build_source(a):
    if a.demo:
        return sources.ReplaySource(sources.demo_logs(), rate=a.rate)
    if a.replay:
        return sources.ReplaySource(sources.read_logs(a.replay), rate=a.rate)
    return sources.SshSource(sources.ssh_fetcher(a.pi))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="address to listen on (0.0.0.0 for the LAN)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--pi", default=None, help="ssh host (default $HART_PI_SSH, else pi)")
    ap.add_argument("--interval", type=float, default=1.5, help="seconds between ssh polls")
    ap.add_argument("--replay", nargs="+", metavar="LOG", help="replay local logs instead of the Pi")
    ap.add_argument("--demo", action="store_true", help="synthetic distance-mode runs")
    ap.add_argument("--rate", type=float, default=20.0, help="replay speed-up (default 20)")
    a = ap.parse_args(argv)
    src = build_source(a)
    hub = Hub(src, a.interval if src.mode == "live" else 0.25)
    threading.Thread(target=hub.run, daemon=True).start()
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(hub))
    print("Speed-match dashboard on http://%s:%d/ (%s)" % (a.host, a.port, src.mode))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop.set()
        srv.server_close()


if __name__ == "__main__":
    main()
