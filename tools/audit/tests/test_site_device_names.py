"""Published layout index must name masts and heads as tables.xml does.

www/scripts/build_layout_index.py reads its device rows straight from tables.xml
(it used to read a hand-kept JSON copy that kept the dwarf masts as AAR-1946:SL-1-low
long after tables.xml moved them to basic:one-low). This checks the rows it builds
and the published www/data/layout-index.json against tables.xml.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

ROOT = paths.REPO_ROOT
INDEX = ROOT / "www/data/layout-index.json"
SIGNAL_KINDS = ("signal mast", "signal head")


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_layout_index", ROOT / "www/scripts/build_layout_index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SiteDeviceNamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # The masts and heads the site covers (load_devices' own filter), and the published index.
        cls.expected = {sn: d["userName"] for sn, d in _load_builder().load_devices(paths.TABLES_XML).items()
                        if d["kind"] in SIGNAL_KINDS}
        cls.items = json.loads(INDEX.read_text(encoding="utf-8"))["items"]
        cls.published = {it["systemName"] for it in cls.items if it.get("systemName")}

    def test_filter_finds_the_signal_hardware(self) -> None:
        self.assertGreater(len(self.expected), 50)

    def test_every_mast_and_head_is_published_under_a_tables_name(self) -> None:
        # Panel signals carry the mast's user name, device rows its system name.
        for sn, user in self.expected.items():
            with self.subTest(device=sn):
                self.assertTrue(sn in self.published or user in self.published, f"{sn} / {user} not in the index")

    def test_published_signal_names_are_tables_names(self) -> None:
        names = set(self.expected) | set(self.expected.values())
        for item in self.items:
            if item["kind"] == "signal":
                with self.subTest(item=item["id"]):
                    self.assertIn(item["systemName"], names)


if __name__ == "__main__":
    unittest.main()
