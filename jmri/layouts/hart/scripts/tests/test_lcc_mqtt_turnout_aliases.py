from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tools/hartlib/src"))
from hartlib.devices import MASTER_FILE  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1]
HART_ROOT = SCRIPTS.parent
TABLES = HART_ROOT / "output" / "tables.xml"
CSV_PATH = HART_ROOT / "data" / MASTER_FILE


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load_module("lcc_turnout_contract", SCRIPTS / "lcc_turnout_contract.py")
cleanup = load_module(
    "cleanup_uss_ctc_leftovers", SCRIPTS / "cleanup_uss_ctc_leftovers.py"
)


def master(rows: list[dict], path: Path) -> Path:
    """A devices.csv of `rows` (blank but for the columns given) at `path`."""
    blank = dict.fromkeys(contract.devices.COLUMNS, "")
    path.write_text(contract.devices.master_text([dict(blank, **r) for r in rows]), encoding="utf-8")
    return path


TURNOUT = dict(level="1", layer="turnout", role="turnout", user_name="Switch 1", assignment="field",
               system_name="M2T408", jmri_name="M2T408", node="4", dcc="100",
               wiring="Node: 4 Turnout: 0 | OU: 1 Ports: 1,2", written_by="build_device_map.py", description="x")
ALIAS = dict(TURNOUT, role="lcc_alias", user_name="DCC Switch 1", system_name="MTT100", jmri_name="MTT100")
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
                                            master(rows, self.tmp / MASTER_FILE))

    def test_live_tables_match_device_map(self) -> None:
        root = ET.parse(TABLES).getroot()
        self.assertEqual(contract.contract_violations(root, CSV_PATH), [])

    def test_a_plant_and_its_twin_hold(self) -> None:
        self.assertEqual(self.violations(MQTT + TWIN, [TURNOUT, ALIAS]), [])

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
