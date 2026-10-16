from __future__ import annotations

import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
HART_ROOT = SCRIPTS.parent
TABLES = HART_ROOT / "output" / "tables.xml"
CSV_PATH = HART_ROOT / "data" / "public_name_map.csv"


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
le_cleanup = load_module("apply_le_cleanup", SCRIPTS / "apply_le_cleanup.py")


class LccMqttTurnoutAliasContractTest(unittest.TestCase):
    def test_lcc_comment_strips_dcc(self) -> None:
        self.assertEqual(
            contract.lcc_comment_from_mqtt(
                "Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2"
            ),
            "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2",
        )

    def test_expected_lcc_user(self) -> None:
        self.assertEqual(contract.expected_lcc_user("Switch 1"), "DCC Switch 1")
        self.assertIsNone(contract.expected_lcc_user("DCC Switch 1"))

    def test_live_tables_match_device_map(self) -> None:
        root = ET.parse(TABLES).getroot()
        self.assertEqual(contract.contract_violations(root, CSV_PATH), [])

    def test_missing_alias_is_a_violation(self) -> None:
        xml = """
        <layout-config>
          <turnout feedback="TWOSENSOR" sensor1="FB Switch 1 R" sensor2="FB Switch 1 N">
            <systemName>M2T408</systemName>
            <userName>Switch 1</userName>
            <comment>Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2</comment>
          </turnout>
        </layout-config>
        """
        root = ET.fromstring(xml)
        issues = contract.contract_violations(root, None)
        self.assertTrue(any("MTT100" in item for item in issues))

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

    def test_le_cleanup_copies_fb_without_rewriting_comments(self) -> None:
        xml = """
        <layout-config>
          <turnout feedback="TWOSENSOR" sensor1="FB Switch 1 R" sensor2="FB Switch 1 N">
            <systemName>M2T408</systemName>
            <userName>Switch 1</userName>
            <comment>Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2</comment>
          </turnout>
          <turnout feedback="DIRECT">
            <systemName>MTT100</systemName>
            <userName>DCC Switch 1</userName>
            <comment>Node: 4 Turnout: 0 | OU: 1 Ports: 1,2</comment>
          </turnout>
        </layout-config>
        """
        root = ET.fromstring(xml)
        self.assertEqual(le_cleanup.patch_mtt(root), 3)
        alias = next(
            el
            for el in root.iter("turnout")
            if (el.findtext("systemName") or "").strip() == "MTT100"
        )
        self.assertEqual(alias.get("feedback"), "TWOSENSOR")
        self.assertEqual(alias.get("sensor1"), "FB Switch 1 R")
        self.assertEqual(alias.get("sensor2"), "FB Switch 1 N")
        self.assertEqual(
            (alias.findtext("comment") or "").strip(),
            "Node: 4 Turnout: 0 | OU: 1 Ports: 1,2",
        )
        self.assertEqual((alias.findtext("userName") or "").strip(), "DCC Switch 1")


if __name__ == "__main__":
    unittest.main()
