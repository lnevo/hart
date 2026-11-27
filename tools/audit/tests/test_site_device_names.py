"""Published layout index must name masts and heads as tables.xml does.

www/scripts/build_layout_index.py reads its device rows straight from tables.xml
(it used to read a hand-kept JSON copy that kept the dwarf masts as AAR-1946:SL-1-low
long after tables.xml moved them to basic:one-low). This checks the rows it builds
and the published www/data/layout-index.json against tables.xml. The JSON is not committed (ADR-036): this builds it
in memory with index_text(), the text the site build publishes, so no file on disk is read in its place.
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
from hartlib import devices  # noqa: E402

ROOT = paths.REPO_ROOT
SIGNAL_KINDS = ("signal mast", "signal head")


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_layout_index", ROOT / "www/scripts/build_layout_index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BlockKindFromTheMaster(unittest.TestCase):
    """A block's kind on the site is its devices.csv role (hand-off row 8); a block not on the layout yet (a level-less
    row, its beans from its jmri_bean) is a plain block, with no role asked of it."""

    def test_a_level_less_block_is_a_plain_block(self) -> None:
        import tempfile
        import xml.etree.ElementTree as ET
        from hartlib import jmri_bean, tables_sections
        el = ET.fromstring('<block systemName="IB999" length="0.0" curve="0"><systemName>IB999</systemName>'
                           '<userName>OS Store Added</userName><permissive>no</permissive></block>')
        row = {c: "" for c in devices.COLUMNS}
        row.update(layer="block", user_name="OS Store Added", assignment="field", system_name="IB999",
                   jmri_name="IB999", description="Added in PanelPro.")
        row["jmri_bean"] = jmri_bean.bean_json([(tables_sections.BLOCKS, el)], row)
        with tempfile.TemporaryDirectory() as d:
            files = devices.Files(Path(d) / devices.MASTER_FILE, devices.Files.here().dictionary)
            devices.write_one_file([r.cells() for r in devices.load()] + [row], files)
            doc = ET.parse(paths.TABLES_XML)
            section = next(s for s in doc.getroot().iter("blocks"))
            section.append(el)
            tables_xml = Path(d) / "tables.xml"
            doc.write(tables_xml, encoding="utf-8", xml_declaration=True)
            got = _load_builder().load_devices(tables_xml, files)
        self.assertEqual(got["IB999"]["kind"], "block")
        kinds = {d["userName"]: d["kind"] for d in got.values()}
        self.assertEqual((kinds["OS Switch 101"], kinds["Track Helix Inner"]), ("os block", "block"))


class SiteDeviceNamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # The masts and heads the site covers (load_devices' own filter), and the published index.
        builder = _load_builder()
        cls.expected = {sn: d["userName"] for sn, d in builder.load_devices(paths.TABLES_XML).items()
                        if d["kind"] in SIGNAL_KINDS}
        cls.items = json.loads(builder.index_text())["items"]
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
