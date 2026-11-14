#!/usr/bin/env python3
"""Publish the speed-match runs on the Pi as files JMRI's web server serves. Python 3 standard
library only; runs on the Pi as the user service hart-speedmatch-live.

    publish_live.py [--out ~/JMRI_UserFiles/web/speedmatch/live] [--interval 1.5]
    publish_live.py --once            one pass, then exit (tests, a manual check)
    publish_live.py --build-page DIR  write the page itself (index.html, app.js, style.css, photos)

Every interval it reads the newest run logs in the Pi's /tmp the way the Mac dashboard does
(dashsources.SshSource, with the same ls, stat and tail commands run locally instead of over
ssh), feeds them through dashstate, and writes index.json and runs/<id>.json in the shape
export_site_runs.py writes for the website (run_view, shared). The page at /web/speedmatch/ is
the dashboard's own client in its recorded mode, re-reading those files every 1.5 s. Files are
written under a temporary name and renamed, so the page never reads half a file. Nothing here
writes anywhere but --out, and it never touches JMRI, the layout or MQTT.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dashsources as sources  # noqa: E402
import dashstate as state  # noqa: E402
import export_site_runs as ex  # noqa: E402

DEFAULT_OUT = Path.home() / "JMRI_UserFiles" / "web" / "speedmatch" / "live"
POLL_MS = 1500
ROSTER = HERE.parents[4] / "resources" / "roster"  # jmri/resources/roster in the repo


def local_fetch(cmd, timeout=10):
    """The SshSource fetch, run on this machine: the commands are ls, stat and tail on /tmp."""
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise OSError((p.stderr or b"command failed").decode("utf-8", "replace").strip()[:200])
    return p.stdout


def write_atomic(path, text):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_lines(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


class Publisher:
    def __init__(self, out, fetch=local_fetch, read=read_lines):
        self.out = Path(out)
        self.src = sources.SshSource(fetch)
        self.store = state.Store()
        self.read = read
        self.reference = sources.reference_curves()
        self.seen = None  # (path, bytes) of every run last written

    def once(self):
        """One poll. Rewrites the files only when a log grew, a run appeared or one went away.
        Returns the number of runs published, or None when nothing changed."""
        ok, msg = self.src.poll(self.store)
        if not ok:
            print("publish_live: %s" % msg, file=sys.stderr)
            return None
        rids = [rid for rid in self.store.runs if state.kind_of_log(Path(rid).name) in ex.PUBLISH]
        seen = tuple(sorted((rid, self.src.offsets.get(rid, 0)) for rid in rids))
        if seen == self.seen:
            return None
        (self.out / "runs").mkdir(parents=True, exist_ok=True)
        index, files = [], set()
        for rid in rids:
            run = self.store.runs[rid]
            if run.t_last is None and run.t0 is None:
                continue  # nothing readable yet
            lines = self.read(rid) if run.kind == "stoptest" else []
            snap, entry = ex.run_view(self.store, rid, lines, self.reference, None,
                                      now=None if run.t_end else time.time(), mode="live")
            write_atomic(self.out / entry["file"], json.dumps(snap, separators=(",", ":"), sort_keys=True) + "\n")
            files.add(Path(entry["file"]).name)
            index.append(entry)
        index.sort(key=lambda r: (-(r["start"] or 0), r["id"]))
        write_atomic(self.out / "index.json", json.dumps({"runs": index}, indent=1, sort_keys=True) + "\n")
        for f in (self.out / "runs").glob("*.json"):  # runs whose log is gone (a reboot clears /tmp)
            if f.name not in files:
                f.unlink()
        self.seen = seen
        return len(index)


def build_page(dest):
    """The Pi page: the live dashboard's index.html, set to read live/ every POLL_MS, plus
    app.js, style.css and the roster photos of the two locos."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    static = HERE / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    photos = {}
    for loco in ("2121", "2738"):
        jpg = ROSTER / (loco + ".jpg")
        if jpg.is_file():
            shutil.copy2(jpg, dest / jpg.name)
            photos[loco] = jpg.name
    cfg = '<script>window.SM_RECORDED = %s;</script>\n<script src="app.js"></script>' % json.dumps(
        {"base": "live/", "poll": POLL_MS, "photos": photos})
    html, n = re.subn(r'<script src="app\.js"></script>', cfg, html)
    if n != 1:
        raise SystemExit("static/index.html: expected one app.js script tag")
    html = html.replace("<title>Speed-match live</title>", "<title>Speed-match live (Pi)</title>")
    (dest / "index.html").write_text(html, encoding="utf-8")
    for f in ("app.js", "style.css"):
        shutil.copy2(static / f, dest / f)
    return dest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="where index.json and runs/ go")
    ap.add_argument("--interval", type=float, default=POLL_MS / 1000.0, help="seconds between polls")
    ap.add_argument("--once", action="store_true", help="one poll, then exit")
    ap.add_argument("--build-page", metavar="DIR", help="write the page into DIR and exit")
    a = ap.parse_args(argv)
    if a.build_page:
        print("page written to %s" % build_page(a.build_page))
        return
    state.warm_caches()
    pub = Publisher(a.out)
    while True:
        try:
            n = pub.once()
            if a.once:
                print("published %s runs in %s" % (n if n is not None else 0, a.out))
                return
        except Exception as e:  # keep serving: the next poll starts again
            print("publish_live: %s: %s" % (e.__class__.__name__, e), file=sys.stderr)
            if a.once:
                raise
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
