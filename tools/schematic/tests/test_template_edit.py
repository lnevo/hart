"""template_edit.py: edits of data/tables_template.xml on a temporary copy (no PanelPro, no rebuild)."""
from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import template_edit as te  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402


class TemplateEditTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = self.dir / "tables_template.xml"
        shutil.copyfile(tb.TEMPLATE, self.path)
        self.original = self.path.read_bytes()

    def run_cmd(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = te.main(["--template", str(self.path), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_list_shows_kinds_and_writes_nothing(self):
        code, out, _ = self.run_cmd("list")
        self.assertEqual(code, 0)
        for want in ("memory  IMRATEFACTOR", "sensor  ISCLOCKRUNNING", "clock   rate=1.0", "setting blockrouting=yes",
                     "logixng IQ:AUTO:0001"):
            self.assertIn(want, out)
        _, only, _ = self.run_cmd("list", "memory")
        self.assertNotIn("sensor", only)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_no_op_set_is_byte_identical(self):
        code, out, _ = self.run_cmd("memory", "set", "IMRATEFACTOR", "--user-name", "Clock rate")
        self.assertEqual(code, 0)
        self.assertIn("no change", out)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_add_set_remove_round_trip(self):
        code, out, _ = self.run_cmd("memory", "add", "IMZZ_TEST", "--user-name", "Test memory", "--comment", "A test")
        self.assertEqual(code, 0)
        self.assertIn("add memory IMZZ_TEST", out)
        text = self.path.read_text()
        self.assertIn("<systemName>IMZZ_TEST</systemName>\n      <userName>Test memory</userName>\n      <comment>A test"
                      "</comment>", text)
        self.assertEqual(tb.read_template(self.path).root.tag, "layout-config")
        self.assertEqual(self.run_cmd("memory", "set", "IMZZ_TEST", "--comment", "Changed")[0], 0)
        self.assertIn("<comment>Changed</comment>", self.path.read_text())
        self.assertEqual(self.run_cmd("memory", "remove", "IMZZ_TEST")[0], 0)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_add_keeps_jmri_order_and_untouched_items(self):
        self.run_cmd("memory", "add", "IMAAA", "--user-name", "First")
        text = self.path.read_text()
        self.assertLess(text.index("IMAAA"), text.index("IMCURRENTTIME"))
        self.run_cmd("memory", "remove", "IMAAA")
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_refusals_write_nothing(self):
        cases = [
            ("memory", "add", "IMRATEFACTOR", "--user-name", "X"),            # duplicate system name
            ("memory", "add", "IMNEW", "--user-name", "Clock rate"),          # duplicate user name
            ("memory", "add", "NEW", "--user-name", "X"),                     # not an IM name
            ("memory", "add", "IM BAD", "--user-name", "X"),                  # space
            ("memory", "add", "IMNEW"),                                       # no user name
            ("memory", "set", "IMNOPE", "--comment", "x"),                    # unknown
            ("memory", "set", "IMRATEFACTOR"),                                # nothing to set
            ("memory", "set", "IMRATEFACTOR", "--user-name", "Current time"),  # clash
            ("memory", "remove", "IMNOPE"),
            ("clock", "set", "nope=1"),
            ("clock", "set", "run=maybe"),
            ("clock", "set", "rate=fast"),
            ("clock", "set", "rate=0"),
            ("clock", "set", "rate"),
            ("setting", "set", "blockrouting=perhaps"),
            ("setting", "set", "logicdelay=-1"),
            ("setting", "set", "closedspeed=Warp"),
            ("setting", "set", "closedspeed=Global"),
            ("setting", "set", "logicdelay=1.5"),
            ("clock", "set", "rate=nan"),
            ("clock", "set", "rate=inf"),
            ("clock", "set", "startclockoption=3"),
            ("memory", "remove", "IMHART_MIMIC"),                             # read by mimic_relay.py
            ("memory", "add", "IMNEW", "--user-name", "Hide WiThrottle"),     # a ConditionalNG's user name
            ("setting", "set", "nothing=1"),
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                code, _, err = self.run_cmd(*argv)
                self.assertEqual(code, 1)
                self.assertIn("template_edit.py:", err)
                self.assertEqual(self.path.read_bytes(), self.original)

    def test_remove_refuses_a_used_memory(self):
        doc = tb.read_template(self.path)
        sock = doc.root.find(".//LogixNG/ConditionalNGs")
        sock.append(ET.Element("systemName"))
        sock[-1].text = "IMRATEFACTOR"
        doc.save(self.path)
        before = self.path.read_bytes()
        code, _, err = self.run_cmd("memory", "remove", "IMRATEFACTOR")
        self.assertEqual(code, 1)
        self.assertIn("is used by", err)
        self.assertEqual(self.path.read_bytes(), before)

    def test_clock_and_settings_change_only_their_line(self):
        self.assertEqual(self.run_cmd("clock", "set", "rate=2.0", "startrunning=no")[0], 0)
        a = self.original.decode().splitlines()
        b = self.path.read_text().splitlines()
        changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        self.assertEqual(len(a), len(b))
        self.assertEqual(len(changed), 1)
        self.assertIn('rate="2.0"', b[changed[0]])
        self.assertIn('startrunning="no"', b[changed[0]])
        self.assertEqual(self.run_cmd("clock", "set", "rate=1.0", "startrunning=yes")[0], 0)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(self.run_cmd("setting", "set", "blockrouting=no", "logicdelay=250", "blockspeed=Slow",
                                      "closedspeed=Slow", "thrownspeed=Slow")[0], 0)
        text = self.path.read_text()
        self.assertIn('blockrouting="no"', text)
        self.assertIn("<logicDelay>250</logicDelay>", text)
        self.assertEqual(text.count("<defaultclosedspeed>Slow</defaultclosedspeed>"), 3)
        self.run_cmd("setting", "set", "blockrouting=yes", "logicdelay=500", "blockspeed=Normal",
                     "closedspeed=Normal", "thrownspeed=Restricted")
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_clock_rate_written_as_jmri_does(self):
        self.run_cmd("clock", "set", "rate=2", "startrate=3", "startclockoption=4")
        text = self.path.read_text()
        self.assertIn('rate="2.0" startrate="3.0"', text)
        self.assertIn('startclockoption="4"', text)

    def test_logicdelay_strips_zeros_and_block_speed_accepts_number(self):
        self.run_cmd("setting", "set", "logicdelay=0250", "closedspeed=Block", "blockspeed=40")
        text = self.path.read_text()
        self.assertIn("<logicDelay>250</logicDelay>", text)
        self.assertIn("<defaultclosedspeed>Block</defaultclosedspeed>", text)

    def test_missing_template_is_a_message(self):
        self.path.unlink()
        code, _, err = self.run_cmd("list")
        self.assertEqual(code, 1)
        self.assertIn("template_edit.py:", err)

    def test_failed_rebuild_restores_both_files(self):
        built = self.dir / "tables.xml"
        built.write_bytes(b"built")
        with mock.patch.object(te.paths, "REPO_TABLES_XML", built), mock.patch.object(te, "rebuild") as rb:
            def fail():
                built.write_bytes(b"half written")
                return 1
            rb.side_effect = fail
            self.path.write_bytes(self.original + b"<!-- edited -->")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(te.rebuild_or_restore(self.path, self.original), 1)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(built.read_bytes(), b"built")

    def test_missing_plugin_names_the_fix(self):
        built = self.dir / "tables.xml"
        built.write_bytes(b"built")
        err = io.StringIO()
        with mock.patch.object(te.paths, "REPO_TABLES_XML", built), mock.patch.object(te, "rebuild", return_value=3), \
                contextlib.redirect_stderr(err):
            te.rebuild_or_restore(self.path, self.original)
        self.assertIn("--no-build", err.getvalue())

    def test_dry_run_writes_nothing(self):
        for argv in (("memory", "add", "IMZZ", "--user-name", "Z"), ("clock", "set", "rate=3.0"),
                     ("memory", "set", "IMRATEFACTOR", "--comment", "Other")):
            with self.subTest(argv=argv):
                code, out, _ = self.run_cmd("--dry-run", *argv)
                self.assertEqual(code, 0)
                self.assertIn("dry run", out)
                self.assertEqual(self.path.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
