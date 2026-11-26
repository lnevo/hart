"""tools/hosts/sandbox/panel_snapshot.py (Jython, inside PanelPro): when the panel never appears it writes
OUT.error naming the panel and exits 1, instead of calling methods on None inside invokeAndWait.

The script runs under CPython in a subprocess with fake jmri, java, javax and time modules: the fake clock
moves a second per call, so the 120 s wait ends at once."""
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
    import runpy, sys, types

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
    class Swing:
        calls = []
        @staticmethod
        def invokeAndWait(r):
            Swing.calls.append(r)
            r.run()
    java = mod("java")
    java.lang = mod("java.lang", System=types.SimpleNamespace(exit=sys_exit), Runnable=Runnable)
    java.awt = mod("java.awt")
    java.awt.image = mod("java.awt.image", BufferedImage=object)
    java.io = mod("java.io", File=object)
    javax = mod("javax")
    javax.imageio = mod("javax.imageio", ImageIO=object)
    javax.swing = mod("javax.swing", SwingUtilities=Swing)

    class Manager:
        @staticmethod
        def getList():
            return []          # no panel ever loads
    class Editors:
        pass
    jmri = mod("jmri")
    jmri.InstanceManager = types.SimpleNamespace(getDefault=lambda cls: Manager)
    jmri.jmrit = types.SimpleNamespace(display=types.SimpleNamespace(
        EditorManager=Editors, layoutEditor=types.SimpleNamespace(LayoutEditor=Editors)))

    try:
        runpy.run_path(sys.argv[1], run_name="__main__")
    except SystemExit as exc:
        print("invokeAndWait calls: %d" % len(Swing.calls))
        raise
''')


class MissingPanel(unittest.TestCase):
    def test_no_panel_writes_the_error_and_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "panel.png"
            boot = Path(t) / "boot.py"
            boot.write_text(BOOT, encoding="utf-8")
            done = subprocess.run([sys.executable, "-I", str(boot), str(SCRIPT)], capture_output=True,
                                  text=True, env={"HART_SNAPSHOT_OUT": str(out)}, cwd=t, timeout=30)
            self.assertEqual(1, done.returncode, done.stderr)
            self.assertIn("invokeAndWait calls: 0", done.stdout)
            error = Path(f"{out}.error").read_text(encoding="utf-8")
            self.assertIn('no Layout Editor panel "HART Railroad" appeared within 120 s', error)
            self.assertFalse(Path(f"{out}.done").exists())
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
