from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
HART_ROOT = SCRIPTS.parent
TABLES = HART_ROOT / "output" / "tables.xml"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load_module("lcc_turnout_contract", SCRIPTS / "lcc_turnout_contract.py")
devices = contract.devices
from hartlib.device_rows import MasterRow  # noqa: E402  (on the path the contract module puts hartlib)
CSV_PATH = HART_ROOT / "data" / devices.MASTER_FILE
cleanup = load_module(
    "cleanup_uss_ctc_leftovers", SCRIPTS / "cleanup_uss_ctc_leftovers.py"
)


def master(rows: list[dict], path: Path) -> Path:
    """A devices.csv of `rows` (blank but for the columns given; a row with a level gets a test id, which
    check_rows wants) at `path`."""
    blank = dict.fromkeys(contract.devices.COLUMNS, "")
    full = [dict(blank, **r) for r in rows]
    full = [dict(r, id=r["id"] or (f"test:{r['layer']}:{r['user_name']}" if r["level"] else "")) for r in full]
    path.write_text(contract.devices.master_text(full), encoding="utf-8")
    return path


def master_row(cells: dict) -> MasterRow:
    """A row of the master as devices.load gives it, from `cells` (blank but for the columns given)."""
    return MasterRow.from_master(dict(dict.fromkeys(devices.COLUMNS, ""), **cells), 0, "a test row")


TURNOUT = dict(level="1", layer="turnout", role="turnout", id="switch:1", user_name="Switch 1", assignment="field",
               system_name="M2T408", jmri_name="M2T408", node="4", dcc="100",
               wiring="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", written_by="build_device_map.py", description="x")
ALIAS = dict(TURNOUT, role="lcc_alias", id="dcc:1", user_name="DCC Switch 1", system_name="MTT100", jmri_name="MTT100")
MQTT = """
  <turnout feedback="TWOSENSOR" sensor1="FB Switch 1 R" sensor2="FB Switch 1 N">
    <systemName>M2T408</systemName>
    <userName>Switch 1</userName>
    <comment>Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2</comment>
  </turnout>"""
TWIN = """
  <turnout feedback="TWOSENSOR" sensor1="FB Switch 1 R" sensor2="FB Switch 1 N">
    <systemName>MTT100</systemName>
    <userName>DCC Switch 1</userName>
    <comment>Node: 4 Turnout: 0 | OU: 1 Ports: 1,2</comment>
  </turnout>"""


class LccMqttTurnoutAliasContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def violations(self, xml: str, rows: list[dict]) -> list[str]:
        return contract.contract_violations(ET.fromstring(f"<layout-config>{xml}</layout-config>"),
                                            master(rows, self.tmp / devices.ONE_FILE))

    def test_live_tables_match_device_map(self) -> None:
        root = ET.parse(TABLES).getroot()
        self.assertEqual(contract.contract_violations(root, CSV_PATH), [])

    def test_a_plant_and_its_twin_hold(self) -> None:
        self.assertEqual(self.violations(MQTT + TWIN, [TURNOUT, ALIAS]), [])

    def test_a_renamed_turnout_keeps_its_alias_by_id(self) -> None:
        """naming-layers step 4: the owner renames a staging turnout in its field row; it still pairs with its alias by
        the switch number of their ids (switch:1, dcc:1), not by name."""
        plants, refused, bad = contract.field_plants(master([dict(TURNOUT, user_name="Switch Brick West"), ALIAS],
                                                            self.tmp / devices.ONE_FILE))
        self.assertEqual((refused, bad), (set(), []))
        self.assertEqual((plants["M2T408"].user, plants["M2T408"].alias), ("Switch Brick West", "MTT100"))

    def test_a_turnout_id_that_names_no_switch_stops(self) -> None:
        """The master refuses a turnout row whose id is not switch:<n> or dcc:<n> (check_rows), so no pair falls
        back to its name; pair_key refuses one that did not come through a load."""
        with self.assertRaisesRegex(devices.DevicesError, r"Switch 1 \(level 1, turnout\): id 'test:turnout:Switch 1' "
                                                          "is not switch:<switch number>"):
            contract.field_plants(master([dict(TURNOUT, id=""), ALIAS], self.tmp / devices.ONE_FILE))
        with self.assertRaisesRegex(devices.DevicesError, "id 'switch:1a' is not switch:<n> or dcc:<n>"):
            contract.pair_key(master_row(dict(TURNOUT, id="switch:1a")))
        self.assertEqual(contract.pair_key(master_row(dict(TURNOUT, level="", id=""))), ("", "Switch 1"))
        self.assertEqual(contract.pair_key(master_row(dict(ALIAS, level="", id=""))), ("", "Switch 1"))
        self.assertEqual(contract.pair_key(master_row(ALIAS)), contract.pair_key(master_row(TURNOUT)))
        self.assertEqual(contract.pair_key(master_row(TURNOUT)), ("1", "1"))

    def test_the_alias_is_the_rows_dcc_not_the_comments(self) -> None:
        """The address comes from the turnout row's dcc column; a comment that says otherwise does not move it."""
        xml = MQTT.replace("DCC: 100", "DCC: 999") + TWIN
        self.assertEqual(self.violations(xml, [TURNOUT, ALIAS]), [])
        got = self.violations(MQTT + TWIN, [dict(TURNOUT, dcc="101"), ALIAS])
        self.assertTrue(any("its alias DCC Switch 1 is MTT100, not MTT101 (its dcc)" in p for p in got), got)

    def test_missing_alias_is_a_violation(self) -> None:
        issues = self.violations(MQTT, [TURNOUT, ALIAS])
        self.assertEqual(issues, ["M2T408 (Switch 1) has no LCC alias MTT100"])

    def test_a_twin_with_the_wrong_name_or_comment(self) -> None:
        xml = MQTT + TWIN.replace("DCC Switch 1", "Switch X").replace("OU: 1 Ports: 1,2", "OU: 2")
        got = self.violations(xml, [TURNOUT, ALIAS])
        self.assertIn("MTT100 userName 'Switch X' expected 'DCC Switch 1'", got)
        self.assertIn("MTT100 comment 'Node: 4 Turnout: 0 | OU: 2' expected 'Node: 4 Turnout: 0 | OU: 1 Ports: 1,2'",
                      got)

    def test_rows_with_no_pair_are_violations(self) -> None:
        got = self.violations(MQTT + TWIN, [TURNOUT])
        self.assertTrue(any("no LCC alias row DCC Switch 1" in p for p in got), got)
        got = self.violations(MQTT + TWIN, [dict(TURNOUT, dcc=""), ALIAS])
        self.assertTrue(any("a field turnout with no dcc" in p for p in got), got)
        got = self.violations(MQTT + TWIN, [ALIAS])
        self.assertTrue(any("alias DCC Switch 1 (MTT100) has no field turnout row Switch 1" in p for p in got), got)
        self.assertTrue(any("M2T408 (Switch 1) has no field turnout row" in p for p in got), got)
        got = self.violations(TWIN, [TURNOUT, ALIAS])
        self.assertTrue(any("has no MQTT plant M2T408 in tables.xml" in p for p in got), got)

    def test_a_refused_row_is_reported_once(self) -> None:
        """A turnout row the contract refuses (no dcc, no alias, a wrong alias) is reported for that, not again as a
        missing row."""
        for rows in ([dict(TURNOUT, dcc=""), ALIAS], [TURNOUT], [dict(TURNOUT, dcc="101"), ALIAS]):
            with self.subTest(rows=len(rows)):
                got = self.violations(MQTT + TWIN, rows)
                self.assertFalse(any("has no field turnout row" in p for p in got), got)

    def test_an_unreadable_master_is_a_violation_not_a_crash(self) -> None:
        got = contract.contract_violations(ET.fromstring("<layout-config/>"), self.tmp / "missing.csv")
        self.assertEqual(len(got), 1)
        self.assertRegex(got[0], r"^missing\.csv: cannot check the LCC aliases: .*cannot read it")

    def test_a_dcc_turnout_needs_no_lcos_plant(self) -> None:
        """Every LCOS turnout is a DCC turnout, but not every DCC turnout is LCOS (owner, 2026-11-20)."""
        self.assertEqual([], self.violations('<turnout feedback="MONITORING"><systemName>MTT999</systemName></turnout>',
                                             []))

    def test_cleanup_must_not_list_or_delete_mtt(self) -> None:
        self.assertFalse(
            any(name.startswith("MTT") for name in cleanup.DELETE_SYSTEM_NAMES)
        )
        snippet = (
            '    <turnout feedback="TWOSENSOR">\n'
            "      <systemName>MTT100</systemName>\n"
            "      <userName>DCC Switch 1</userName>\n"
            "    </turnout>\n"
        )
        updated, removed = cleanup.delete_orphans(snippet)
        self.assertEqual(removed, 0)
        self.assertIn("MTT100", updated)


if __name__ == "__main__":
    unittest.main()
