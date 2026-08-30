from __future__ import annotations

import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


polish = load_module("polish_hart_layout_editor", SCRIPTS / "polish_hart_layout_editor.py")
icons = load_module(
    "add_digicon_le_signal_icons",
    ROOT / "cats/scripts/add_digicon_le_signal_icons.py",
)


class PolishHartLayoutEditorTest(unittest.TestCase):
    def test_signal_generators_share_exact_placements(self):
        generated = {name: (x, y, degrees) for name, x, y, degrees in icons.PLACEMENTS}
        self.assertEqual(polish.SIGNAL_PLACEMENTS, generated)
        self.assertEqual(23, len(generated))

    def test_visual_polish_is_idempotent_and_preserves_topology(self):
        source = ROOT / "tables/new_tables.xml"
        before_root = ET.parse(source).getroot()
        before_le = polish.find_layout_editor(before_root)
        before_topology = [
            (
                el.tag,
                el.get("ident"),
                el.get("connect1name"),
                el.get("connect2name"),
                el.get("connectaname"),
                el.get("connectbname"),
                el.get("connectcname"),
                el.get("connectdname"),
            )
            for el in before_le
            if el.tag in {"tracksegment", "layoutturnout", "positionablepoint"}
        ]

        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "tables.xml"
            target.write_bytes(source.read_bytes())
            polish.apply_visual_standard(target)
            _changes, errors = polish.apply_visual_standard(target, check=True)
            self.assertEqual([], errors)

            after_root = ET.parse(target).getroot()
            after_le = polish.find_layout_editor(after_root)
            leftover = [
                icon.get("sensor")
                for icon in after_le.findall("sensoricon")
                if polish.REDUNDANT_OCCUPANCY_SENSOR.fullmatch(
                    (icon.get("sensor") or "").strip()
                )
                and (icon.get("sensor") or "").strip()
                not in polish.OS_OCCUPANCY_ICONS
            ]
            self.assertFalse(leftover)
            os_present = {
                (icon.get("sensor") or "").strip()
                for icon in after_le.findall("sensoricon")
                if (icon.get("sensor") or "").strip() in polish.OS_OCCUPANCY_ICONS
            }
            self.assertEqual(os_present, set(polish.OS_OCCUPANCY_ICONS))
            after_topology = [
                (
                    el.tag,
                    el.get("ident"),
                    el.get("connect1name"),
                    el.get("connect2name"),
                    el.get("connectaname"),
                    el.get("connectbname"),
                    el.get("connectcname"),
                    el.get("connectdname"),
                )
                for el in after_le
                if el.tag in {"tracksegment", "layoutturnout", "positionablepoint"}
            ]
            self.assertEqual(before_topology, after_topology)

    def test_block_contents_icons_move_to_label_layer(self):
        xml = """<?xml version='1.0' encoding='UTF-8'?>
        <layout-config>
          <LayoutEditor name="HART Railroad">
            <BlockContentsIcon blockcontents="Track West Main Ext" x="1394" y="232" level="0" fontFamily="Lucida Grande" fontname="LucidaGrande-Bold" size="12" red="51" green="51" blue="51" />
            <tracksegment ident="T1" />
          </LayoutEditor>
        </layout-config>
        """
        root = ET.fromstring(xml)
        le = root.find("LayoutEditor")
        assert le is not None
        changes, errors = polish.ensure_block_contents_visible(le, check=False)
        self.assertEqual([], errors)
        self.assertGreater(changes, 0)
        icon = le.find("BlockContentsIcon")
        assert icon is not None
        self.assertEqual("4", icon.get("level"))
        self.assertEqual("0", icon.get("red"))
        self.assertNotIn("fontFamily", icon.attrib)
        self.assertNotIn("fontname", icon.attrib)
        _, leftover = polish.ensure_block_contents_visible(le, check=True)
        self.assertEqual([], leftover)


if __name__ == "__main__":
    unittest.main()
