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

BARN_TURNOUT_BLOCK = frozenset(
    {
        ("turnout", "Switch 117"),
        ("block", "OS 117 (West Yard)"),
        ("block", "OS 117b (West Yard)"),
        ("block", "Yard T6"),
        ("block", "South Yard West"),
    }
)

ENGINE_HOUSE_MAP = {
    "Yard T9": "EH-1",
    "Yard T10": "EH-2",
    "Yard T11": "EH-3",
    "Engine House 1": "EH-1",
    "Engine House 2": "EH-2",
    "Engine House 3": "EH-3",
}

SOUTH_YARD_RENAME_MAP = {
    "Yard T1": "Scale",
    "Yard T6": "Barn",
    "East Lead": "East Lead",
    "South Yard East": "East Lead",
    "Yard Track 1": "S-1",
    "Yard Track 2": "S-2",
    "Yard Track 3": "S-3",
    "Yard Track 4": "S-4",
    "Yard Track 5": "S-5",
    "South Yard 1": "S-1",
    "South Yard 2": "S-2",
    "South Yard 3": "S-3",
    "South Yard 4": "S-4",
    "South Yard 5": "S-5",
}

EAST_END_SWITCHES = ("Switch 107", "Switch 108", "Switch 109")

MAST_PROPOSED_RE = re.compile(r"^\d{3}[LR][AB]?$")
HEAD_PROPOSED_RE = re.compile(r"^\d{3}[LR][AB]?(\s+(Top|Bottom))?$")

HARDWARE_TOKEN_RE = re.compile(
    r"^(?:M2T\d+|M2S\d+|IH\d+|Block \d+-\d+)$"
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


def turnout_user_names_by_switch() -> dict[str, str]:
    root = ET.parse(TABLES_PATH).getroot()
    by_switch: dict[str, str] = {}
    for turnout in root.iter("turnout"):
        system_name = turnout.findtext("systemName")
        user_name = turnout.findtext("userName")
        if not user_name or not user_name.startswith("Switch "):
            continue
        if system_name and system_name.startswith("M2T"):
            by_switch[user_name.strip()] = user_name.strip()
    return by_switch


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
        self.assertGreater(len(self.rows), 0, "CSV must contain data rows")

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

    def test_turnouts_100_119_user_names_match_proposed(self) -> None:
        turnout_rows = {
            row["current"]: row
            for row in self.by_layer["turnout"]
            if row["current"].startswith("Switch 1")
        }
        xml_turnouts = turnout_user_names_by_switch()
        violations: list[str] = []
        for number in range(100, 120):
            switch = f"Switch {number}"
            row = turnout_rows.get(switch)
            if row is None:
                violations.append(f"CSV missing turnout row for {switch}")
                continue
            if row["proposed"] != switch:
                violations.append(
                    f"{switch}: proposed {row['proposed']!r} != {switch!r} (no turnout rename)"
                )
            xml_name = xml_turnouts.get(switch)
            if xml_name != switch:
                violations.append(
                    f"{switch}: tables.xml userName {xml_name!r} != {switch!r}"
                )
        self.assertEqual(violations, [])

    def test_engine_house_proposed_names(self) -> None:
        block_rows = {row["current"]: row for row in self.by_layer["block"]}
        violations: list[str] = []
        for current, expected in ENGINE_HOUSE_MAP.items():
            row = block_rows.get(current)
            if row is None:
                violations.append(f"missing block row for {current!r}")
                continue
            if row["proposed"] != expected:
                violations.append(
                    f"{current}: proposed {row['proposed']!r} != {expected!r}"
                )
        self.assertEqual(violations, [])

    def test_south_yard_public_name_mappings(self) -> None:
        block_rows = {row["current"]: row for row in self.by_layer["block"]}
        violations: list[str] = []
        for current, expected in SOUTH_YARD_RENAME_MAP.items():
            row = block_rows.get(current)
            if row is None:
                violations.append(f"missing block row for {current!r}")
                continue
            if row["proposed"] != expected:
                violations.append(
                    f"{current}: proposed {row['proposed']!r} != {expected!r}"
                )
        self.assertEqual(violations, [])

    def test_barn_cp_only_on_switch_117_and_os_117_rows(self) -> None:
        violations: list[str] = []
        barn_tb: set[tuple[str, str]] = set()
        for row in self.rows:
            if row["cp"] != "Barn":
                continue
            key = (row["layer"], row["current"])
            if row["layer"] in {"turnout", "block"}:
                barn_tb.add(key)
                if key not in BARN_TURNOUT_BLOCK:
                    violations.append(f"unexpected Barn cp on {row['layer']} {row['current']!r}")
            elif row["layer"] in {"mast", "head"}:
                if not row["proposed"].startswith("117"):
                    violations.append(
                        f"Barn signal {row['current']!r} proposed {row['proposed']!r} is not 117*"
                    )
            else:
                violations.append(f"unexpected Barn cp on {row['layer']} {row['current']!r}")
        for key in BARN_TURNOUT_BLOCK:
            if key not in barn_tb:
                violations.append(f"missing Barn cp on {key[0]} {key[1]!r}")
        self.assertEqual(violations, [])

    def test_switches_107_109_east_end_not_hand_throw(self) -> None:
        turnout_rows = {row["current"]: row for row in self.by_layer["turnout"]}
        violations: list[str] = []
        for switch in EAST_END_SWITCHES:
            row = turnout_rows.get(switch)
            if row is None:
                violations.append(f"missing turnout row for {switch}")
                continue
            if row["cp"] != "East End":
                violations.append(f"{switch}: cp {row['cp']!r} != 'East End'")
            notes = row.get("notes", "")
            if "hand-throw" in notes.lower():
                violations.append(f"{switch}: notes must not say hand-throw ({notes!r})")
        self.assertEqual(violations, [])

    def test_mast_proposed_names_match_adr_grammar(self) -> None:
        violations: list[str] = []
        for row in self.by_layer["mast"]:
            proposed = row["proposed"]
            if not MAST_PROPOSED_RE.match(proposed):
                violations.append(f"mast {row['current']!r}: proposed {proposed!r}")
        for row in self.by_layer["head"]:
            proposed = row["proposed"]
            if not HEAD_PROPOSED_RE.match(proposed):
                violations.append(f"head {row['current']!r}: proposed {proposed!r}")
        self.assertEqual(violations, [])

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
            if not system_name.startswith(("M2T", "M2S", "IH")):
                continue
            if system_name not in self.tables_system_names:
                violations.append(
                    f"baseline systemName {system_name!r} missing from tables.xml"
                )
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
