"""tools/hosts/sandbox/panel_snapshot.py (Jython, inside PanelPro): it paints the panel to OUT and writes OUT.done
with the size; when the panel never appears, has no size, or a step on the Swing thread fails, it writes OUT.error
with the reason and exits 1 instead of leaving PanelPro open.

The script runs under CPython in a subprocess with fake jmri, java, javax and time modules: the fake clock moves a
second per call, so the 120 s wait ends at once. FAKE_PANEL picks the panel the fake JMRI holds."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/hosts/sandbox/panel_snapshot.py"

BOOT = textwrap.dedent('''
    import os, runpy, sys, types

    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        sys.modules[name] = m
        return m

    class Clock:
        now = 0.0
    def fake_time():
        Clock.now += 1
        return Clock.now
    mod("time", time=fake_time, sleep=lambda s: None)

    def sys_exit(code):
        raise SystemExit(code)
    class Runnable:
        pass
    class Throwable(Exception):
        pass
    class Swing:
        calls = []
        @staticmethod
        def invokeAndWait(r):
            Swing.calls.append(r)
            r.run()
    class Graphics:
        disposed = 0
        def dispose(self):
            Graphics.disposed += 1
    class BufferedImage:
        TYPE_INT_RGB = 1
        def __init__(self, w, h, kind):
            self.size = (w, h)
        def createGraphics(self):
            return Graphics()
    class File:
        def __init__(self, path):
            self.path = path
    class ImageIO:
        @staticmethod
        def write(img, fmt, f):
            with open(f.path, "wb") as out:
                out.write(b"PNG %dx%d" % img.size)
            return True
    java = mod("java")
    java.lang = mod("java.lang", System=types.SimpleNamespace(exit=sys_exit), Runnable=Runnable, Throwable=Throwable)
    java.awt = mod("java.awt")
    java.awt.image = mod("java.awt.image", BufferedImage=BufferedImage)
    java.io = mod("java.io", File=File)
    javax = mod("javax")
    javax.imageio = mod("javax.imageio", ImageIO=ImageIO)
    javax.swing = mod("javax.swing", SwingUtilities=Swing)

    KIND = os.environ["FAKE_PANEL"]
    class Size:
        def __init__(self, w, h):
            self.width, self.height = w, h
    class Frame:
        def setSize(self, w, h):
            print("frame %dx%d" % (w, h))
        def validate(self):
            pass
    class Target:
        def getPreferredSize(self):
            return Size(0, 0) if KIND == "zero" else Size(1900, 1000)
        def setSize(self, w, h):
            pass
        def paint(self, g):
            if KIND == "paint fails":
                raise Throwable("NullPointerException in paint")
    class LayoutEditor:
        def getLayoutName(self):
            return "HART Railroad"
        def setZoom(self, z):
            pass
        def getTargetPanel(self):
            return Target()
        def getTargetFrame(self):
            return Frame()
    class Other:
        pass
    class Manager:
        @staticmethod
        def getList():
            return [Other()] if KIND == "none" else [Other(), LayoutEditor()]
    jmri = mod("jmri")
    jmri.InstanceManager = types.SimpleNamespace(getDefault=lambda cls: Manager)
    jmri.jmrit = types.SimpleNamespace(display=types.SimpleNamespace(
        EditorManager=object, layoutEditor=types.SimpleNamespace(LayoutEditor=LayoutEditor)))

    try:
        runpy.run_path(sys.argv[1], run_name="__main__")
    except SystemExit as exc:
        print("invokeAndWait calls: %d" % len(Swing.calls))
        print("graphics disposed: %d" % Graphics.disposed)
        raise
''')


class Snapshot(unittest.TestCase):
    def run_with(self, kind: str) -> tuple[subprocess.CompletedProcess[str], Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "panel.png"
        boot = Path(tmp.name) / "boot.py"
        boot.write_text(BOOT, encoding="utf-8")
        done = subprocess.run([sys.executable, "-I", str(boot), str(SCRIPT)], capture_output=True, text=True,
                              env={"HART_SNAPSHOT_OUT": str(out), "FAKE_PANEL": kind}, cwd=tmp.name, timeout=30)
        return done, out

    def test_the_panel_is_painted_whole_and_the_size_written(self) -> None:
        done, out = self.run_with("ok")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(out.read_bytes(), b"PNG 1900x1000")
        self.assertEqual(Path(f"{out}.done").read_text(encoding="utf-8"), "1900x1000\n")
        self.assertFalse(Path(f"{out}.error").exists())
        self.assertEqual(done.stdout.count("frame 2100x1200"), 2)       # grown once to load, once to paint
        self.assertIn("invokeAndWait calls: 2", done.stdout)
        self.assertIn("graphics disposed: 1", done.stdout)

    def test_no_panel_writes_the_error_and_exits_1(self) -> None:
        done, out = self.run_with("none")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("invokeAndWait calls: 0", done.stdout)
        error = Path(f"{out}.error").read_text(encoding="utf-8")
        self.assertIn('no Layout Editor panel "HART Railroad" appeared within 120 s', error)
        self.assertFalse(Path(f"{out}.done").exists())
        self.assertFalse(out.exists())

    def test_a_panel_with_no_size_is_an_error(self) -> None:
        done, out = self.run_with("zero")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn('grow failed: panel "HART Railroad" has no size to paint (0x0)',
                      Path(f"{out}.error").read_text(encoding="utf-8"))
        self.assertFalse(Path(f"{out}.done").exists())

    def test_an_error_on_the_swing_thread_is_written_and_exits_1(self) -> None:
        done, out = self.run_with("paint fails")
        self.assertEqual(1, done.returncode, done.stderr)
        self.assertIn("paint failed: NullPointerException in paint", Path(f"{out}.error").read_text(encoding="utf-8"))
        self.assertIn("graphics disposed: 1", done.stdout)
        self.assertFalse(Path(f"{out}.done").exists())


if __name__ == "__main__":
    unittest.main()
