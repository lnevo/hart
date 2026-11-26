from __future__ import annotations

import importlib.util
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import level_masts, paths  # noqa: E402

ROOT = paths.REPO_ROOT
SCRIPT = ROOT / "tools/mqtt-mimic/qa/run_native_sml_qa.py"
TABLES = paths.TABLES_XML


def load_module():
    spec = importlib.util.spec_from_file_location("run_native_sml_qa", SCRIPT)
    mod = sys.modules["run_native_sml_qa"] = importlib.util.module_from_spec(spec)   # its dataclasses look it up
    spec.loader.exec_module(mod)
    return mod


def table_masts() -> dict[str, tuple[str, ...]]:
    masts = {}
    for mast in ET.parse(TABLES).getroot().iter("signalmast"):
        name = mast.findtext("userName")
        if name:
            masts[name] = tuple(level_masts.mast_heads(mast.findtext("systemName") or ""))
    return masts


class NativeSmlQaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qa = load_module()
        cls.qa.MAST_HEADS.update(cls.qa.load_mast_heads())     # as main() does

    def test_masts_and_heads_match_tables(self) -> None:
        masts = table_masts()
        self.assertEqual(set(self.qa.MAST_HEADS), self.qa.LIVE_MASTS)
        for mast, heads in self.qa.MAST_HEADS.items():
            self.assertEqual(masts.get(mast), heads, mast)

    def test_heads_come_from_tables(self) -> None:
        self.assertEqual(self.qa.load_mast_heads(TABLES), self.qa.MAST_HEADS)
        self.assertEqual(self.qa.MAST_HEADS["Mast 6LB"], ("IH432",))
        self.assertEqual(self.qa.MAST_HEADS["Mast 40LA"], ("IH:HART:C1:40LA_Top", "IH:HART:C1:40LA_Bottom"))

    def test_live_masts_are_staging_visible_masts(self) -> None:
        self.assertIn("Mast 67", self.qa.LIVE_MASTS)
        self.assertNotIn("Mast 4LA", self.qa.LIVE_MASTS)     # hidden virtual mast
        self.assertNotIn("Mast 108LA", self.qa.LIVE_MASTS)   # main level

    def test_unreadable_head_mast_fails_loudly(self) -> None:
        import tempfile
        xml = (
            "<layout-config><signalmasts>"
            "<signalmast><systemName>IF$shsm:basic:one-low(IH1)</systemName><userName>Mast A</userName></signalmast>"
            "<signalmast><systemName>IF$shsm:basic:one-low(Head B)</systemName><userName>Mast B</userName></signalmast>"
            "</signalmasts></layout-config>"
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "tables.xml"
            path.write_text(xml, encoding="utf-8")
            with self.assertRaises(self.qa.QAError) as ctx:
                self.qa.load_mast_heads(path)
        self.assertIn("Mast B", str(ctx.exception))

    def test_expected_mast_names_exist(self) -> None:
        named = {mast for st in self.qa.SCENARIO for mast in st.expect}
        self.assertIn("Mast 40LA", named)
        self.assertLessEqual(named, set(table_masts()))

    def test_scenario_drives_known_switches_and_blocks(self) -> None:
        for st in self.qa.SCENARIO:
            for change in (*st.before, *st.after):
                self.assertIn(change.name, self.qa.TO if change.what == "turnout" else self.qa.OCC, st.tag)

    def test_run_drives_and_checks_each_step_with_no_broker(self) -> None:
        from unittest import mock
        applied, seen = [], []
        snap = {"Mast A": {"aspect": "Stop", "held": None}}
        steps = (self.qa.Step("t1", "d", {"Mast A": "stop"}, before=(self.qa.turnout("113", "THROWN"),),
                              after=(self.qa.occupancy("K-1", "INACTIVE"),)),
                 self.qa.Step("t2", "d", {"Mast A": "nonstop"}))
        run = self.qa.Run()
        with mock.patch.object(self.qa, "set_to", lambda sw, st: applied.append(("to", sw, st))), \
                mock.patch.object(self.qa, "set_occ", lambda b, st: applied.append(("occ", b, st))), \
                mock.patch.object(self.qa, "pub", side_effect=AssertionError("published")), \
                mock.patch.object(self.qa, "jmri_snapshot", lambda: seen.append(1) or snap), \
                mock.patch.object(self.qa, "mqtt_heads", lambda: {}), mock.patch.object(self.qa, "SETTLE", 0), \
                mock.patch("sys.stdout"):
            self.qa.run_scenario(run, steps)
        self.assertEqual(applied, [("to", "113", "THROWN"), ("occ", "K-1", "INACTIVE")])
        self.assertEqual(len(seen), 2)
        self.assertEqual(run.failures, ["[FAIL] t2: Mast A = 'Stop' (expected nonstop)"])
        self.assertEqual(len(run.notes), 2)

    def test_missing_client_is_a_qa_error(self) -> None:
        from unittest import mock
        with mock.patch.object(self.qa, "CLIENT_DIRS", ("/nonexistent",)):
            with self.assertRaisesRegex(self.qa.QAError, "mosquitto_pub is not in PATH"):
                self.qa.client("mosquitto_pub")

    def test_bad_tables_end_main_with_one_line_and_nothing_driven(self) -> None:
        import io
        from unittest import mock
        err = io.StringIO()
        with mock.patch.object(self.qa, "client", lambda name: f"/bin/{name}"), \
                mock.patch.object(self.qa, "load_mast_heads", side_effect=self.qa.QAError("tables.xml head masts x")), \
                mock.patch.object(self.qa, "capture_baseline", side_effect=AssertionError("ran")), \
                mock.patch("sys.stderr", err):
            self.assertEqual(self.qa.main(), 2)
        self.assertEqual(err.getvalue(), "run_native_sml_qa: tables.xml head masts x\n")

    def test_an_http_error_falls_back_to_the_heads(self) -> None:
        import http.client
        import io
        from unittest import mock
        with mock.patch.object(self.qa.urllib.request, "urlopen", side_effect=http.client.BadStatusLine("x")), \
                mock.patch.object(self.qa, "mqtt_heads", lambda: {}), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(set(self.qa.jmri_snapshot()), set(self.qa.MAST_HEADS))

    def test_snapshot_names_each_server_that_did_not_answer(self) -> None:
        import io
        import urllib.error
        from unittest import mock
        err = io.StringIO()
        with mock.patch.object(self.qa.urllib.request, "urlopen", side_effect=urllib.error.URLError("refused")), \
                mock.patch.object(self.qa, "mqtt_heads", lambda: {}), mock.patch("sys.stderr", err):
            snap = self.qa.jmri_snapshot()
        self.assertIn("refused", err.getvalue())
        self.assertIn("no JMRI JSON", err.getvalue())
        self.assertEqual(set(snap), set(self.qa.MAST_HEADS))

    def test_output_stays_beside_the_script(self) -> None:
        self.assertEqual(self.qa.OUT, SCRIPT.parent)

    def test_aspects_from_heads_use_basic_names(self) -> None:
        cases = [
            (["Green", "Red"], "Clear"),
            (["Yellow", "Red"], "Approach"),
            (["Red", "Green"], "Diverging Clear"),
            (["Red", "Yellow"], "Diverging Approach"),
            (["Red", "Red"], "Stop"),
            (["Green"], "Clear"),
            (["Red"], "Stop"),
            ([None], "Stop"),
        ]
        for colors, aspect in cases:
            self.assertEqual(self.qa.aspect_from_heads(colors), aspect, colors)


if __name__ == "__main__":
    unittest.main()
