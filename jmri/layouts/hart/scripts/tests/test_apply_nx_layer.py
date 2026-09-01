from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


MINIMAL = """\
<?xml version="1.0" encoding="UTF-8"?>
<layout-config>
  <sensors class="jmri.managers.configurexml.InternalSensorManagerXml">
    <sensor inverted="false">
      <systemName>ISNX:100L</systemName>
      <userName>NX Mast 2L</userName>
      <comment>Entry/Exit at mast Mast 2L; Brick east main westbound; lever 4 Left. Full interlock. CATS CTC and USS Logic off while NX is in use.</comment>
    </sensor>
  </sensors>
  <turnouts class="jmri.jmrix.openlcb.configurexml.OlcbTurnoutManagerXml">
  </turnouts>
  <entryexitpairs class="jmri.jmrit.entryexit.configurexml.EntryExitPairsXml">
    <abssignalmode>yes</abssignalmode>
    <layoutPanel name="HART Railroad">
      <source type="sensor" item="NX Mast 2L">
        <destination type="sensor" item="NX Mast 6LB" nxType="signalmastlogic" uniqueid="IN:ee93974c-2a81-46c8-b68c-ac13b097a4bb" />
      </source>
    </layoutPanel>
  </entryexitpairs>
  <LayoutEditor class="jmri.jmrit.display.layoutEditor.configurexml.LayoutEditorXml" name="HART Railroad">
    <signalmasticon signalmast="Mast 2L" x="382" y="242" degrees="0" />
    <layoutturnout ident="TOL3" type="LH_TURNOUT">
      <signalAMast>Mast 2L</signalAMast>
    </layoutturnout>
  </LayoutEditor>
  <LayoutEditor class="jmri.jmrit.display.layoutEditor.configurexml.LayoutEditorXml" name="Dispatcher System">
  </LayoutEditor>
</layout-config>
"""


class FrozenIsnx(unittest.TestCase):
    def test_contract_uses_ctc_numbers_not_mast_user_names(self) -> None:
        contract = _load("nx_contract")
        self.assertEqual(contract.nx_system_name("Mast 2L"), "ISNX:100L")
        self.assertEqual(contract.nx_system_name("Mast 2035"), "ISNX:120L")
        self.assertEqual(contract.nx_user_name("Mast 2L"), "NX Mast 2L")
        self.assertNotIn("ISNX:Mast 2L", contract.ISNX_SYSTEM.values())
        self.assertEqual(len(contract.ISNX_SYSTEM), 23)

    def test_apply_does_not_mint_isnx_mast_user_names(self) -> None:
        apply_nx = _load("apply_nx_layer")
        out, counts = apply_nx.apply_text(MINIMAL, mode="sml")
        self.assertNotIn("ISNX:Mast 2L", out)
        self.assertIn("<systemName>ISNX:100L</systemName>", out)
        self.assertEqual(out.count("<systemName>ISNX:"), 23)
        self.assertIn("SML mode: throws the path", out)
        self.assertNotIn("Full interlock. CATS CTC", out)
        self.assertIn('<sensorA>NX Mast 2L</sensorA>', out)
        self.assertEqual(counts["sensors"], 22)
        self.assertEqual(counts["comments"], 1)

    def test_layer_masts_match_frozen_map(self) -> None:
        apply_nx = _load("apply_nx_layer")
        contract = _load("nx_contract")
        self.assertEqual(set(apply_nx.CTC_MASTS), set(contract.ISNX_SYSTEM))
        self.assertEqual(contract.nx_system_name("Mast 24RA"), "ISNX:111RA")
        self.assertEqual(contract.nx_system_name("Mast 32R"), "ISNX:110R")
        self.assertEqual(contract.nx_system_name("Mast 34L"), "ISNX:112L")
        self.assertEqual(contract.nx_system_name("Mast 36RA"), "ISNX:113RA")
        self.assertEqual(contract.nx_system_name("Mast 40LB"), "ISNX:115LB")


if __name__ == "__main__":
    unittest.main()
