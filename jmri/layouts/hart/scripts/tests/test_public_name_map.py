from __future__ import annotations

import csv
import re
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


HART_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = HART_ROOT / "data" / "public_name_map.csv"
TABLES_PATH = HART_ROOT / "output" / "tables.xml"
BASELINE_PATH = HART_ROOT / "data" / "baselines" / "hardware_identity.csv"

REQUIRED_COLUMNS = ("layer", "current", "proposed", "cp", "hardware")
COMMENT_COLUMN = "comment"

BLOCK_ALIAS_CURRENT_SETS = frozenset(
    {
        frozenset({"Main West Brick-Plane", "Block 100-102"}),
        frozenset({"Yard T9", "ET-3", "Engine House 1"}),
        frozenset({"Yard T10", "ET-2", "Engine House 2"}),
        frozenset({"Yard T11", "ET-1", "Engine House 3"}),
        frozenset({"Yard T1", "South Yard Scale"}),
        frozenset({"Yard T6", "South Yard West"}),
        frozenset({"Yard Track 1", "South Yard 1"}),
        frozenset({"Yard Track 2", "South Yard 2"}),
        frozenset({"Yard Track 3", "South Yard 3"}),
        frozenset({"Yard Track 4", "South Yard 4"}),
        frozenset({"Yard Track 5", "South Yard 5"}),
        frozenset({"East Lead", "South Yard East"}),
    }
)

# ADR-024 adds milepost intermediates (Mast 67, Mast A84): a bare number, lettered by level off staging.
MAST_PROPOSED_RE = re.compile(r"^Mast (?:\d{1,3}[LR][ABC]?|\d{4}|[A-Z]?\d{2,3})$")
HEAD_PROPOSED_RE = re.compile(
    r"^Head (?:\d{1,3}[LR][AB]?|\d{4}|[A-Z]?\d{2,3})(?:\s+(Top|Bottom))?$"
)

HARDWARE_TOKEN_RE = re.compile(
    r"^(?:M2T\d+|M2S\d+|IH\d+|MTT\d+|Block \d+-\d+)$"
)


def load_csv_rows() -> list[dict[str, str]]:
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise AssertionError(f"{CSV_PATH}: missing header row")
        missing = [column for column in REQUIRED_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise AssertionError(f"{CSV_PATH}: missing columns {missing}")
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized = {
                key: (value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            rows.append(normalized)
        return rows


def hardware_tokens(hardware: str) -> list[str]:
    return [token for token in hardware.split() if token]


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


class PublicNameMapContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_csv_rows()
        cls.by_layer = defaultdict(list)
        for row in cls.rows:
            cls.by_layer[row["layer"]].append(row)
        cls.tables_system_names, cls.tables_user_names = parse_tables_names()
        cls.tables_all_names = cls.tables_system_names | cls.tables_user_names

    def test_csv_well_formed_required_columns(self) -> None:
        self.assertTrue(CSV_PATH.is_file(), f"missing {CSV_PATH}")
        with CSV_PATH.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertIsNotNone(reader.fieldnames)
            assert reader.fieldnames is not None
            self.assertEqual(
                list(reader.fieldnames[: len(REQUIRED_COLUMNS)]),
                list(REQUIRED_COLUMNS),
                "required columns must appear first in header order",
            )
            for column in REQUIRED_COLUMNS:
                self.assertIn(column, reader.fieldnames)
            self.assertIn(COMMENT_COLUMN, reader.fieldnames)
        self.assertGreater(len(self.rows), 0, "CSV must contain data rows")

    def test_live_mqtt_turnouts_are_identity_rows(self) -> None:
        """Post-convert: live Switch N is current == proposed, not Switch 100."""
        identity = {
            row["current"]: row
            for row in self.by_layer["turnout"]
            if row["current"] == row["proposed"]
        }
        xml_turnouts = turnout_user_names_by_system()
        missing = [
            f"{system} {name}"
            for system, name in sorted(xml_turnouts.items())
            if name not in identity
        ]
        self.assertEqual(missing, [])
        switch_1 = identity.get("Switch 1")
        self.assertIsNotNone(switch_1)
        self.assertTrue(
            (switch_1 or {}).get("comment", "").startswith("Node:"),
            f"Switch 1 comment should be Device-map wiring, got {switch_1}",
        )

    def test_unique_layer_current_pairs(self) -> None:
        seen: dict[tuple[str, str], int] = {}
        duplicates: list[str] = []
        for line_number, row in enumerate(self.rows, start=2):
            key = (row["layer"], row["current"])
            if key in seen:
                duplicates.append(
                    f"line {line_number}: duplicate ({row['layer']!r}, {row['current']!r}) "
                    f"also on line {seen[key]}"
                )
            seen[key] = line_number
        self.assertEqual(duplicates, [])

    def test_proposed_unique_per_layer_except_documented_aliases(self) -> None:
        violations: list[str] = []
        for layer, rows in self.by_layer.items():
            by_proposed: dict[str, list[str]] = defaultdict(list)
            for row in rows:
                by_proposed[row["proposed"]].append(row["current"])
            for proposed, currents in sorted(by_proposed.items()):
                unique_currents = sorted(set(currents))
                if len(unique_currents) <= 1:
                    continue
                current_set = frozenset(unique_currents)
                live_hits = [
                    name for name in unique_currents if name in self.tables_user_names
                ]
                # Historical aliases share proposed with the live name; at most one live current.
                if len(live_hits) <= 1:
                    continue
                if proposed in current_set:
                    continue
                if layer == "block" and current_set in BLOCK_ALIAS_CURRENT_SETS:
                    continue
                violations.append(
                    f"{layer}: {unique_currents} -> {proposed!r} (not a documented alias set)"
                )
        self.assertEqual(violations, [])

    def test_frozen_hardware_exists_in_tables_xml(self) -> None:
        missing: list[str] = []
        for row in self.rows:
            for token in hardware_tokens(row["hardware"]):
                if not HARDWARE_TOKEN_RE.match(token):
                    continue
                if token not in self.tables_all_names:
                    missing.append(
                        f"{row['layer']} {row['current']!r}: hardware {token!r} "
                        "not found as systemName or userName in tables.xml"
                    )
        self.assertEqual(missing, [])

    def test_mast_proposed_names_match_adr_grammar(self) -> None:
        violations: list[str] = []
        for row in self.by_layer["mast"]:
            proposed = row["proposed"]
            if not MAST_PROPOSED_RE.match(proposed):
                violations.append(f"mast {row['current']!r}: proposed {proposed!r}")
        for row in self.by_layer["head"]:
            proposed = row["proposed"]
            # IH9990 is the panel's turnout-mode lamp, not a field head.
            if proposed != "Turnout FB status" and not HEAD_PROPOSED_RE.match(proposed):
                violations.append(f"head {row['current']!r}: proposed {proposed!r}")
        self.assertEqual(violations, [])

    def test_live_tables_usernames_appear_as_current(self) -> None:
        """Every live public userName must be a `current` or `proposed` in the map. The main and upper levels'
        objects stand on internal system names until they are imported (blocks IB:C3:, masts and heads on IH9
        heads; build_layout_le.py, hartlib.level_masts): their names are the device map's, not yet the map's."""
        import sys
        sys.path.insert(0, str(HART_ROOT.parents[2] / "tools/hartlib/src"))
        from hartlib import level_masts
        by_name = {(row["layer"], row["current"]) for row in self.rows} | {
            (row["layer"], row["proposed"]) for row in self.rows
        }
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

    def test_hardware_identity_baseline_if_present(self) -> None:
        if not BASELINE_PATH.is_file():
            self.skipTest(
                f"baseline not found at {BASELINE_PATH.relative_to(HART_ROOT)}; skipping"
            )
        with BASELINE_PATH.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        violations: list[str] = []
        for row in rows:
            system_name = (row.get("systemName") or "").strip()
            if not system_name.startswith(("M2T", "M2S", "IH", "MTT")):
                continue
            if system_name not in self.tables_system_names:
                violations.append(
                    f"baseline systemName {system_name!r} missing from tables.xml"
                )
        self.assertEqual(violations, [])

    def test_device_map_comments_on_identity_hardware(self) -> None:
        """MQTT occupancy/FB/head identity rows carry Device-map comments."""
        missing: list[str] = []
        for row in self.rows:
            if row["current"] != row["proposed"]:
                continue
            if row["layer"] not in {"occupancy", "fb", "head", "turnout"}:
                continue
            hardware = (row.get("hardware") or "").split()[0]
            # Staging's internal heads (IH:HART:C1:*; ADR-024) are not wired, so they carry no port comment.
            if not re.match(r"^(?:M2T|M2S|IH|MTT)\d", hardware):
                continue
            if not (row.get("comment") or "").strip():
                missing.append(f"{row['layer']} {row['current']!r}")
        self.assertEqual(missing, [])

    def test_lcc_turnout_identity_rows_cover_mtt_100_119(self) -> None:
        identities = {
            (row.get("hardware") or "").split()[0]: row
            for row in self.by_layer["turnout"]
            if row["current"] == row["proposed"]
            and (row.get("hardware") or "").startswith("MTT")
        }
        missing: list[str] = []
        for number in range(100, 120):
            hardware = f"MTT{number}"
            row = identities.get(hardware)
            if row is None:
                missing.append(hardware)
                continue
            if not row["proposed"].startswith("DCC Switch "):
                missing.append(f"{hardware} proposed {row['proposed']!r}")
        self.assertEqual(missing, [])

    def test_mast_comments_name_the_protected_switch(self) -> None:
        by_name = {
            row["current"]: row
            for row in self.by_layer["mast"]
            if row["current"] == row["proposed"]
        }
        self.assertEqual(by_name["Mast 2L"]["comment"], "Brick | Switch 1")
        self.assertEqual(by_name["Mast 67"]["comment"], "Princess")


if __name__ == "__main__":
    unittest.main()
