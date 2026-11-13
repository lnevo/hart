from __future__ import annotations

import importlib.util
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
SCRIPT = ROOT / "tools/mqtt-mimic/qa/run_native_sml_qa.py"
TABLES = paths.TABLES_XML


def load_module():
    spec = importlib.util.spec_from_file_location("run_native_sml_qa", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def table_masts() -> dict[str, tuple[str, ...]]:
    masts = {}
    for mast in ET.parse(TABLES).getroot().iter("signalmast"):
        name = mast.findtext("userName")
        if name:
            masts[name] = tuple(re.findall(r"IH\d+", mast.findtext("systemName") or ""))
    return masts


class NativeSmlQaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qa = load_module()

    def test_masts_and_heads_match_tables(self) -> None:
        masts = table_masts()
        self.assertEqual(set(self.qa.MAST_HEADS), self.qa.LIVE_MASTS)
        for mast, heads in self.qa.MAST_HEADS.items():
            self.assertEqual(masts.get(mast), heads, mast)

    def test_heads_come_from_tables(self) -> None:
        self.assertEqual(self.qa.load_mast_heads(TABLES), self.qa.MAST_HEADS)
        self.assertEqual(self.qa.MAST_HEADS["Mast 6LB"], ("IH432",))
        self.assertEqual(self.qa.MAST_HEADS["Mast 40LA"], ("IH1132", "IH1135"))

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
            with self.assertRaises(SystemExit) as ctx:
                self.qa.load_mast_heads(path)
        self.assertIn("Mast B", str(ctx.exception))

    def test_expected_mast_names_exist(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        named = set(re.findall(r'"(Mast \w+)"', source))
        self.assertLessEqual(named, set(table_masts()))

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
