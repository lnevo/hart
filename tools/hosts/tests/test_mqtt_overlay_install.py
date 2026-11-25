"""tools/jmri/mqtt_overlay/install_overlay.py: jmri.conf gets the overlay's --cp:p and keeps every other option.

Each test works in a temp folder with a fake jmri.jar holding only jmri/Version.properties; no JMRI is touched.
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/jmri/mqtt_overlay"))
import install_overlay as io_  # noqa: E402

JAR = ROOT / "tools/jmri/mqtt_overlay" / io_.JAR_NAME


def fake_jmri(home: Path, minor: str = "16", rev: str = "909e15189e") -> Path:
    home.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(home / "jmri.jar", "w") as z:
        z.writestr("jmri/Version.properties",
                   f"release.major=5\nrelease.minor={minor}\nrelease.build=0\nrelease.revision_id={rev}\n")
    return home


class EditConf(unittest.TestCase):
    def test_new_file(self):
        out = io_.edit_conf(None, "/u/.jmri/hart-mqtt-race-fix.jar")
        self.assertTrue(out.endswith('default_options="--cp:p=/u/.jmri/hart-mqtt-race-fix.jar"\n'))

    def test_keeps_other_options(self):
        out = io_.edit_conf('# c\ndefault_options="-Dpi4j.linking=dynamic"\n', "/u/.jmri/hart-mqtt-race-fix.jar")
        self.assertEqual(out, '# c\ndefault_options="--cp:p=/u/.jmri/hart-mqtt-race-fix.jar -Dpi4j.linking=dynamic"\n')

    def test_idempotent_and_moves_old_path(self):
        once = io_.edit_conf('default_options="--cp:p=/old/hart-mqtt-race-fix.jar -J-Xmx2g"\n', "/new/hart-mqtt-race-fix.jar")
        self.assertEqual(once, 'default_options="--cp:p=/new/hart-mqtt-race-fix.jar -J-Xmx2g"\n')
        self.assertEqual(io_.edit_conf(once, "/new/hart-mqtt-race-fix.jar"), once)

    def test_windows_path_and_crlf(self):
        src = 'default_options=""\r\n'
        out = io_.edit_conf(src, r"C:\Users\x\JMRI\hart-mqtt-race-fix.jar")
        self.assertEqual(out, 'default_options="--cp:p=C:\\Users\\x\\JMRI\\hart-mqtt-race-fix.jar"\r\n')
        self.assertEqual(io_.edit_conf(out, None), src)

    def test_leaves_other_prepends_and_comments(self):
        src = '# default_options="--cp:p=/x/hart-mqtt-race-fix.jar"\ndefault_options="--cp:p=/x/other.jar"\n'
        out = io_.edit_conf(src, "/y/hart-mqtt-race-fix.jar")
        self.assertEqual(out.splitlines()[0], '# default_options="--cp:p=/x/hart-mqtt-race-fix.jar"')
        self.assertEqual(out.splitlines()[1], 'default_options="--cp:p=/y/hart-mqtt-race-fix.jar --cp:p=/x/other.jar"')

    def test_other_forms_refuse_rather_than_shadow(self):
        for src in ("default_options='-J-Xmx2g'\n", 'export default_options="-J-Xmx2g"\n',
                    'default_options="-J-Xmx2g" # heap\n', "default_options=-J-Xmx2g\n"):
            with self.subTest(src=src), self.assertRaises(io_.UnknownConf):
                io_.edit_conf(src, "/u/hart-mqtt-race-fix.jar")

    def test_multi_entry_prepend_keeps_the_others(self):
        out = io_.edit_conf('default_options="--cp:p=/opt/extra.jar:/u/hart-mqtt-race-fix.jar"\n', None)
        self.assertEqual(out, 'default_options="--cp:p=/opt/extra.jar"\n')
        out = io_.edit_conf('default_options="--cp:p=C:\\x\\a.jar;C:\\u\\hart-mqtt-race-fix.jar"\n', None)
        self.assertEqual(out, 'default_options="--cp:p=C:\\x\\a.jar"\n')

    def test_remove_from_absent_line_changes_nothing(self):
        self.assertEqual(io_.edit_conf("# only a comment\n", None), "# only a comment\n")


class Install(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.tmp = Path(d.name)
        self.settings = self.tmp / "settings"

    def run_main(self, *args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = io_.main(list(args))
        return rc, buf.getvalue()

    def test_installs_on_matching_build(self):
        home = fake_jmri(self.tmp / "jmri")
        self.settings.mkdir()
        (self.settings / "jmri.conf").write_text('default_options="-Dpi4j.linking=dynamic"\n')
        rc, _ = self.run_main("--jar", str(JAR), "--settings-dir", str(self.settings), "--jmri-home", str(home))
        self.assertEqual(rc, 0)
        dest = self.settings / io_.JAR_NAME
        self.assertEqual(dest.read_bytes(), JAR.read_bytes())
        self.assertEqual((self.settings / "jmri.conf").read_text(),
                         f'default_options="--cp:p={dest} -Dpi4j.linking=dynamic"\n')
        rc, out = self.run_main("--jar", str(JAR), "--settings-dir", str(self.settings), "--jmri-home", str(home))
        self.assertIn("already loads it", out)

    def test_other_build_takes_it_out(self):
        home = fake_jmri(self.tmp / "jmri")
        self.run_main("--jar", str(JAR), "--settings-dir", str(self.settings), "--jmri-home", str(home))
        upgraded = fake_jmri(self.tmp / "jmri519", minor="19", rev="abc")
        rc, out = self.run_main("--jar", str(JAR), "--settings-dir", str(self.settings), "--jmri-home", str(upgraded))
        self.assertEqual(rc, 0)
        self.assertIn("WARNING", out)
        self.assertFalse((self.settings / io_.JAR_NAME).exists())
        self.assertNotIn(io_.JAR_NAME, (self.settings / "jmri.conf").read_text())

    def test_missing_jmri_jar_warns_and_runs_stock(self):
        rc, out = self.run_main("--jar", str(JAR), "--settings-dir", str(self.settings),
                                "--jmri-home", str(self.tmp / "nowhere"))
        self.assertEqual(rc, 0)
        self.assertIn("WARNING", out)

    def test_unknown_conf_form_is_left_alone(self):
        home = fake_jmri(self.tmp / "jmri")
        self.settings.mkdir()
        conf = self.settings / "jmri.conf"
        conf.write_text("default_options='-J-Xmx2g'\n")
        rc, out = self.run_main("--jar", str(JAR), "--settings-dir", str(self.settings), "--jmri-home", str(home))
        self.assertEqual(rc, 0)
        self.assertIn("by hand", out)
        self.assertEqual(conf.read_text(), "default_options='-J-Xmx2g'\n")

    def test_committed_jar_names_its_base(self):
        self.assertEqual(io_.overlay_base(JAR), "5.16.0 909e15189e")


if __name__ == "__main__":
    unittest.main()
