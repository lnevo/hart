"""hide_band_panels.py: it hides the band panels once JMRI has opened them, keeps them hidden for a few passes, and
gives up saying which never opened. The script runs as it loads, so each test gives it fake JMRI and AWT modules and
runs the delayed passes itself."""
import ast
import contextlib
import io
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1]
from hartlib import tables  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "hide_band_panels.py"


class Frame:
    def __init__(self, title, visible=True):
        self.title, self.visible, self.hides = title, visible, 0

    def getTitle(self):
        return self.title

    def isVisible(self):
        return self.visible

    def setVisible(self, on):
        if not on:
            self.hides += 1
        self.visible = on


class Jvm:
    def __init__(self):
        self.frames = {}
        self.plain = []
        self.delayed = []
        self.out = io.StringIO()

    def open(self, title, visible=True):
        self.frames[title] = Frame(title, visible)
        return self.frames[title]

    def load(self, case, scope=None):
        def mod(name, **attrs):
            m = types.ModuleType(name)
            m.__dict__.update(attrs)
            return m
        awt = mod("java.awt", Frame=Frame, Window=types.SimpleNamespace(getWindows=lambda: list(self.plain)))
        util = mod("jmri.util", JmriJFrame=types.SimpleNamespace(getFrame=self.frames.get),
                   ThreadingUtil=types.SimpleNamespace(runOnGUI=lambda f: f(),
                                                       runOnGUIDelayed=lambda f, ms: self.delayed.append((f, ms))))
        fakes = {"java": mod("java", awt=awt), "java.awt": awt, "jmri": mod("jmri", util=util), "jmri.util": util}
        saved = {k: sys.modules.get(k) for k in fakes}
        sys.modules.update(fakes)

        def restore():
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        case.addCleanup(restore)
        with contextlib.redirect_stdout(self.out):
            exec(compile(SCRIPT.read_text(encoding="ascii"), str(SCRIPT), "exec"),
                 {"__name__": "under_test"} if scope is None else scope)

    def tick(self, n=1000, between=None):
        ran = 0
        with contextlib.redirect_stdout(self.out):
            while self.delayed and ran < n:
                f, _ = self.delayed.pop(0)
                if between:
                    between(ran)
                f()
                ran += 1
        return ran

    def printed(self):
        return self.out.getvalue().splitlines()


class HideBandPanels(unittest.TestCase):
    def test_the_names_are_hartlibs(self):
        cls = next(n for n in ast.parse(SCRIPT.read_text()).body if isinstance(n, ast.ClassDef))
        node = next(n for n in cls.body if isinstance(n, ast.Assign) and n.targets[0].id == "BAND_PANELS")
        self.assertEqual(tuple(ast.literal_eval(node.value)), tuple(tables.BAND_PANEL_NAMES.values()))

    def test_it_defines_one_module_name_and_leaves_the_cats_scripts_names_alone(self):
        """The shared Jython engine: hide_cats_desk_windows.py's queued passes look up _state and _pass again."""
        tree = ast.parse(SCRIPT.read_text())
        names = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets}
        names |= {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        self.assertEqual(names, {"HartBandPanelHider"})
        jvm = Jvm()
        shared = {"__name__": "shared", "_state": {"hid": False}, "_pass": "cats"}
        jvm.load(self, scope=shared)
        self.assertEqual((shared["_state"], shared["_pass"]), ({"hid": False}, "cats"))

    def test_open_windows_are_hidden_and_the_passes_stop_once_stable(self):
        jvm = Jvm()
        frames = [jvm.open(t) for t in tables.BAND_PANEL_NAMES.values()]
        jvm.load(self)
        jvm.tick()
        self.assertTrue(all(not f.visible for f in frames))
        self.assertEqual(jvm.delayed, [])
        self.assertEqual(jvm.printed(), ["HART: hid the band panels Staging Level, Main Level, Upper Level"])

    def test_windows_that_open_late_are_hidden_when_they_open(self):
        jvm = Jvm()
        names = list(tables.BAND_PANEL_NAMES.values())
        jvm.load(self)
        self.assertEqual([ms for _, ms in jvm.delayed], [500])

        def opening(ran):
            if ran == 3:
                for t in names:
                    jvm.open(t)
        jvm.tick(between=opening)
        self.assertTrue(all(not jvm.frames[t].visible for t in names))
        self.assertEqual(jvm.delayed, [])

    def test_a_window_shown_again_soon_after_is_hidden_again(self):
        jvm = Jvm()
        frames = [jvm.open(t) for t in tables.BAND_PANEL_NAMES.values()]
        jvm.load(self)

        def reshow(ran):
            if ran == 2:
                frames[1].visible = True
        jvm.tick(between=reshow)
        self.assertFalse(frames[1].visible)
        self.assertEqual(frames[1].hides, 2)

    def test_a_plain_frame_with_the_title_counts(self):
        jvm = Jvm()
        names = list(tables.BAND_PANEL_NAMES.values())
        for t in names[:2]:
            jvm.open(t)
        plain = Frame(names[2])
        jvm.plain.append(plain)
        jvm.load(self)
        jvm.tick()
        self.assertFalse(plain.visible)

    def test_it_gives_up_and_names_the_missing_windows(self):
        jvm = Jvm()
        jvm.open("Staging Level")
        jvm.load(self)
        jvm.tick()
        self.assertEqual(jvm.delayed, [])
        self.assertEqual(jvm.printed(), ["HART: band panels not all open after 120 passes; never found: "
                                         "Main Level, Upper Level"])

    def test_the_script_stays_ascii(self):
        SCRIPT.read_bytes().decode("ascii")
        self.assertFalse([l for l in SCRIPT.read_text().splitlines() if l.startswith("from __future__")])


if __name__ == "__main__":
    unittest.main()
