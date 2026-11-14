"""Website device data must name masts and heads as tables.xml does.

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
from hartlib import paths, tables  # noqa: E402

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
        root = tables.read(paths.TABLES_XML)
        cls.live = {tables.system_name(b): tables.user_name(b)
                    for b in list(tables.masts(root)) + list(tables.signal_heads(root))}
        cls.devices = _load_builder().load_devices(paths.TABLES_XML)

    def test_every_mast_and_head_is_listed_as_tables_names_it(self) -> None:
        listed = {sn: d["userName"] for sn, d in self.devices.items() if d["kind"] in SIGNAL_KINDS}
        for sn, user in self.live.items():
            if sn.startswith("IH9990"):
                continue  # lamp head, not signal hardware
            with self.subTest(device=sn):
                self.assertEqual(listed.get(sn), user)

    def test_published_index_signal_devices_match_tables(self) -> None:
        index = json.loads(INDEX.read_text(encoding="utf-8"))
        for item in index["items"]:
            sn = item.get("systemName")
            if item["id"].startswith("dev-") and sn in self.live:
                with self.subTest(device=sn):
                    self.assertEqual(self.devices[sn]["userName"], self.live[sn])


if __name__ == "__main__":
    unittest.main()
