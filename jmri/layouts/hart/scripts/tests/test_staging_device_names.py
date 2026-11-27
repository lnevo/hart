"""Staging's rows of devices.csv (level 1) against tables.xml: the public names and hardware ADR-005 fixes. The name
map that once held them (public_name_map.csv, then the pnm_ columns) is gone (R9e, ADR-029)."""
from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


HART_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HART_ROOT.parents[2] / "tools" / "hartlib" / "src")]
from hartlib import devices, railroad  # noqa: E402

CSV_PATH = HART_ROOT / "data" / devices.MASTER_FILE
TABLES_PATH = HART_ROOT / "output" / "tables.xml"

# ADR-024 adds milepost intermediates (Mast 67, Mast A84): a bare number, lettered by level off staging.
MAST_PROPOSED_RE = re.compile(r"^Mast (?:\d{1,3}[LR][ABC]?|\d{4}|[A-Z]?\d{2,3})$")
HEAD_PROPOSED_RE = re.compile(
    r"^Head (?:\d{1,3}[LR][AB]?|\d{4}|[A-Z]?\d{2,3})(?:\s+(Top|Bottom))?$"
)

HARDWARE_RE = re.compile(r"^(?:M2T\d+|M2S\d+|IH\d+|MTT\d+)$")


def load_csv_rows() -> list[dict[str, str]]:
    """Staging's rows of devices.csv in the device layers, each with its JMRI comment (hartlib.devices.comment_of)."""
    return [{**row.cells(), "comment": devices.comment_of(row)} for row in devices.load(CSV_PATH)
            if row.level_cell == railroad.STAGING_LEVEL and row.layer != "sensor"]


def parse_tables_names() -> tuple[set[str], set[str]]:
    root = ET.parse(TABLES_PATH).getroot()
    system_names: set[str] = set()
    user_names: set[str] = set()
    for element in root.iter():
        if element.tag == "systemName" and element.text:
            system_names.add(element.text.strip())
        elif element.tag == "userName" and element.text:
            user_names.add(element.text.strip())
    return system_names, user_names


def turnout_user_names_by_system() -> dict[str, str]:
    root = ET.parse(TABLES_PATH).getroot()
    by_system: dict[str, str] = {}
    for turnout in root.iter("turnout"):
        system_name = (turnout.findtext("systemName") or "").strip()
        user_name = (turnout.findtext("userName") or "").strip()
        if system_name.startswith("M2T") and user_name.startswith("Switch "):
            by_system[system_name] = user_name
    return by_system


class StagingDeviceNamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_csv_rows()
        cls.by_layer = defaultdict(list)
        for row in cls.rows:
            cls.by_layer[row["layer"]].append(row)
        cls.tables_system_names, cls.tables_user_names = parse_tables_names()
        cls.tables_all_names = cls.tables_system_names | cls.tables_user_names

    def test_the_master_holds_staging_rows(self) -> None:
        self.assertTrue(CSV_PATH.is_file(), f"missing {CSV_PATH}")
        self.assertEqual(len(self.rows), 250)

    def test_live_mqtt_turnouts_have_rows(self) -> None:
        turnouts = {row["user_name"]: row for row in self.by_layer["turnout"]}
        xml_turnouts = turnout_user_names_by_system()
        missing = [f"{system} {name}" for system, name in sorted(xml_turnouts.items()) if name not in turnouts]
        self.assertEqual(missing, [])
        self.assertEqual({system: turnouts[name]["system_name"] for system, name in xml_turnouts.items()},
                         {system: system for system in xml_turnouts})
        self.assertTrue(turnouts["Switch 1"]["comment"].startswith("Node:"), turnouts["Switch 1"])

    def test_hardware_and_jmri_names_exist_in_tables_xml(self) -> None:
        missing = [f"{row['layer']} {row['user_name']!r}: {column} {row[column]!r} is no systemName or userName "
                   "in tables.xml"
                   for row in self.rows for column in ("system_name", "jmri_name")
                   if row[column] and (column == "jmri_name" or HARDWARE_RE.match(row[column]))
                   and row[column] not in self.tables_all_names]
        self.assertEqual(missing, [])

    def test_mast_and_head_names_match_adr_grammar(self) -> None:
        violations: list[str] = []
        for row in self.by_layer["mast"]:
            if not MAST_PROPOSED_RE.match(row["user_name"]):
                violations.append(f"mast {row['user_name']!r}")
        for row in self.by_layer["head"]:
            # IH9990 is the panel's turnout-mode lamp, not a field head.
            if row["role"] != "panel_status" and not HEAD_PROPOSED_RE.match(row["user_name"]):
                violations.append(f"head {row['user_name']!r}")
        self.assertEqual(violations, [])

    def test_live_tables_usernames_are_staging_rows(self) -> None:
        """Every live public userName of a staging bean is a staging row's user name. The main and upper levels'
        objects stand on internal system names (blocks IB:C3:, masts and heads on IH:HART:C3: heads;
        build_layout_le.py, hartlib.level_masts): their rows are their level's."""
        import sys
        sys.path.insert(0, str(HART_ROOT.parents[2] / "tools/hartlib/src"))
        from hartlib import level_masts
        by_name = {(row["layer"], row["user_name"]) for row in self.rows}
        missing: list[str] = []

        root = ET.parse(TABLES_PATH).getroot()

        def child(el: ET.Element, tag: str) -> str:
            value = el.findtext(tag)
            return value.strip() if value else ""

        for turnout in root.iter("turnout"):
            user_name = child(turnout, "userName")
            system_name = child(turnout, "systemName")
            if user_name.startswith("Switch ") and system_name.startswith("M2T"):
                if ("turnout", user_name) not in by_name:
                    missing.append(f"turnout {user_name!r}")

        seen_blocks: set[str] = set()
        for block in root.iter("block"):
            system_name = (block.get("systemName") or child(block, "systemName")).strip()
            if not system_name.startswith("IB") or system_name.startswith("IB:C3:") or system_name in seen_blocks:
                continue
            seen_blocks.add(system_name)
            user_name = child(block, "userName")
            if user_name and ("block", user_name) not in by_name:
                missing.append(f"block {user_name!r}")

        for tag in ("signalmast", "virtualsignalmast"):
            for mast in root.iter(tag):
                user_name = child(mast, "userName")
                system_name = child(mast, "systemName")
                if level_masts.is_level_mast(system_name) or level_masts.is_level_virtual(system_name):
                    continue        # main and upper masts, visible or hidden, are named by their level's rule
                if user_name and ("mast", user_name) not in by_name:
                    missing.append(f"mast {user_name!r}")

        for head in root.iter("signalhead"):
            system_name = child(head, "systemName")
            user_name = child(head, "userName")
            if level_masts.is_level_head(system_name):
                continue
            if system_name.startswith("IH") and user_name and ("head", user_name) not in by_name:
                missing.append(f"head {user_name!r}")

        self.assertEqual(missing, [])

    def test_field_hardware_is_in_tables(self) -> None:
        """Each staging device the master has in the field (assignment field) under an M2T, M2S, IH or MTT system name
        is a system name in tables.xml."""
        names = [row["system_name"] for row in self.rows
                 if row["assignment"] == "field" and row["system_name"].startswith(("M2T", "M2S", "IH", "MTT"))]
        self.assertGreater(len(names), 0)
        self.assertEqual([n for n in names if n not in self.tables_system_names], [])

    def test_wired_hardware_carries_its_wiring_comment(self) -> None:
        """MQTT occupancy, feedback, head and turnout rows carry their wiring comment."""
        missing = [f"{row['layer']} {row['user_name']!r}" for row in self.rows
                   if row["layer"] in {"occupancy", "fb", "head", "turnout"}
                   # staging's internal heads (IH:HART:C1:*; ADR-024) are not wired, so they carry no port comment
                   and re.match(r"^(?:M2T|M2S|IH|MTT)\d", row["system_name"]) and not row["comment"].strip()]
        self.assertEqual(missing, [])

    def test_lcc_turnout_rows_cover_mtt_100_119(self) -> None:
        aliases = {row["system_name"]: row for row in self.by_layer["turnout"] if row["system_name"].startswith("MTT")}
        self.assertEqual(sorted(aliases), sorted(f"MTT{n}" for n in range(100, 120)))
        self.assertEqual([h for h, row in aliases.items() if not row["user_name"].startswith("DCC Switch ")], [])
        self.assertEqual([h for h, row in aliases.items() if row["role"] != "lcc_alias"], [])

    def test_mast_comments_name_the_protected_switch(self) -> None:
        by_name = {row["user_name"]: row for row in self.by_layer["mast"]}
        self.assertEqual(by_name["Mast 2L"]["comment"], "Brick | Switch 1")
        self.assertEqual(by_name["Mast 67"]["comment"], "Princess")

if __name__ == "__main__":
    unittest.main()
