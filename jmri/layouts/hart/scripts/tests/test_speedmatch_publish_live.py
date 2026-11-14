"""The Pi publisher of live speed-match runs (publish_live.py), with a fake /tmp."""
from __future__ import annotations

import json
import re
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

DASH = Path(__file__).resolve().parents[1] / "speedmatch" / "dashboard"
sys.path.insert(0, str(DASH))
import publish_live as pl  # noqa: E402

T = 1794300000.0


def fake_fetch(folder):
    """Answer SshSource's list and tail commands from folder instead of the Pi's /tmp."""
    def fetch(cmd):
        if cmd.startswith('echo "@@NOW'):
            files = sorted(Path(folder).glob("*.log"), key=lambda p: -p.stat().st_mtime)
            out = ["@@NOW %d" % int(T + 100)] + ["@@FILE %s %d" % (p, p.stat().st_size) for p in files]
            return ("\n".join(out) + "\n").encode()
        m = re.fullmatch(r"tail -c \+(\d+) (.+)", cmd)
        if m:
            data = Path(shlex.split(m.group(2))[0]).read_bytes()
            return data[int(m.group(1)) - 1:]
        raise AssertionError("unexpected command " + cmd)
    return fetch


STEPRUN = [
    "%.3f RUN loco=CSX 2738 direction=forward" % T,
    "%.3f CFG route=loop1 mode=distance steps=8,16 target_mm=6000 min_blocks=2 max_s=60 rel=0.03 warm_s=0 warm_step=48 cv3=26 cv4=24 mid=x" % T,
    "%.3f STEP 8" % (T + 1),
]


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self.tmp.name) / "tmp"
        self.logs.mkdir()
        self.out = Path(self.tmp.name) / "web" / "live"

    def tearDown(self):
        self.tmp.cleanup()

    def pub(self):
        return pl.Publisher(self.out, fetch=fake_fetch(self.logs))

    def test_a_running_log_is_published_and_grows(self):
        log = self.logs / "steprun_CSX_2738_forward_20261113_120000.log"
        log.write_text("\n".join(STEPRUN) + "\n")
        p = self.pub()
        self.assertEqual(p.once(), 1)
        idx = json.loads((self.out / "index.json").read_text())["runs"]
        self.assertEqual(idx[0]["id"], "steprun_CSX_2738_forward_20261113_120000")
        self.assertIsNone(idx[0]["outcome"])  # no label on the Pi
        snap = json.loads((self.out / idx[0]["file"]).read_text())
        self.assertEqual(snap["mode"], "live")
        self.assertIsNone(snap["note"])
        self.assertIsNone(p.once())  # nothing new: no rewrite
        with open(log, "a") as fh:
            fh.write("%.3f STOP all steps complete\n%.3f END\n" % (T + 2, T + 2))
        self.assertEqual(p.once(), 1)
        snap = json.loads((self.out / idx[0]["file"]).read_text())
        run = next(r for r in snap["runs"] if r["id"].endswith(idx[0]["id"] + ".log"))
        self.assertEqual(run["status"], "done")

    def test_moveto_logs_are_not_published_and_gone_runs_are_removed(self):
        (self.logs / "moveto_CSX_2738_20261113_120000.log").write_text("%.3f GO x\n" % T)
        log = self.logs / "steprun_CSX_2738_forward_20261113_120000.log"
        log.write_text("\n".join(STEPRUN) + "\n")
        p = self.pub()
        p.once()
        self.assertEqual([f.name for f in (self.out / "runs").glob("*.json")],
                         ["steprun_CSX_2738_forward_20261113_120000.json"])
        (self.out / "runs" / "stale_old_run.json").write_text("{}")
        log.unlink()
        p.store.drop(str(log))
        p.once()
        self.assertEqual(list((self.out / "runs").glob("*.json")), [])
        self.assertEqual(json.loads((self.out / "index.json").read_text())["runs"], [])

    def test_no_temporary_files_are_left(self):
        (self.logs / "steprun_CSX_2738_forward_20261113_120000.log").write_text("\n".join(STEPRUN) + "\n")
        self.pub().once()
        self.assertEqual(list(self.out.rglob("*.tmp")), [])


class Page(unittest.TestCase):
    def test_the_pi_page_reads_live_files_every_poll(self):
        with tempfile.TemporaryDirectory() as d:
            pl.build_page(d)
            html = (Path(d) / "index.html").read_text()
            m = re.search(r"window\.SM_RECORDED = (\{.*?\});", html)
            self.assertTrue(m)
            cfg = json.loads(m.group(1))
            self.assertEqual((cfg["base"], cfg["poll"]), ("live/", pl.POLL_MS))
            self.assertLess(html.index("SM_RECORDED"), html.index('src="app.js"'))
            for f in ("app.js", "style.css"):
                self.assertTrue((Path(d) / f).is_file())
            for loco, name in cfg["photos"].items():
                self.assertTrue((Path(d) / name).is_file(), loco)


if __name__ == "__main__":
    unittest.main()
