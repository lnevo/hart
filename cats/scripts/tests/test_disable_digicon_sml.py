from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "cats/scripts/disable_digicon_sml_in_tables.py"
NEW_TABLES = ROOT / "tables/new_tables.xml"


def load():
    spec = importlib.util.spec_from_file_location("disable_digicon_sml_in_tables", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


SAMPLE = """
<signalmastlogics>
  <signalmastlogic source="Mast 6LB">
    <destinationMast destination="Mast 6LA">
      <enabled>yes</enabled>
    </destinationMast>
    <destinationMast destination="Mast 8LA">
      <enabled>no</enabled>
    </destinationMast>
  </signalmastlogic>
  <signalmastlogic source="Yard dummy">
    <destinationMast destination="Mast 6LB">
      <enabled>yes</enabled>
    </destinationMast>
  </signalmastlogic>
</signalmastlogics>
"""


class DisableDigiconSmlTest(unittest.TestCase):
    def test_lists_enabled_digicon_source_dests_only(self) -> None:
        mod = load()
        pairs = mod.enabled_digicon_pairs(SAMPLE, {"Mast 6LB", "Mast 6LA", "Mast 8LA"})
        self.assertEqual(pairs, [("Mast 6LB", "Mast 6LA")])

    def test_disable_flips_digicon_source_dests(self) -> None:
        mod = load()
        out, flipped, already = mod.disable_digicon_destinations(
            SAMPLE, {"Mast 6LB", "Mast 6LA", "Mast 8LA"}
        )
        self.assertEqual(flipped, 1)
        self.assertEqual(already, 1)
        self.assertIn("<enabled>no</enabled>", out)
        self.assertIn('source="Yard dummy"', out)
        yard = out[out.index('source="Yard dummy"') :]
        self.assertIn("<enabled>yes</enabled>", yard)

    def test_working_new_tables_digicon_sml_disabled(self) -> None:
        mod = load()
        pairs = mod.enabled_digicon_pairs(
            NEW_TABLES.read_text(encoding="utf-8"),
            mod.digicon_mast_names(),
        )
        self.assertEqual(pairs, [])

    def test_deploy_fixes_shipped_tables_instead_of_refusing(self) -> None:
        text = (ROOT / "cats/scripts/sync_hart_package.sh").read_text(encoding="utf-8")
        self.assertIn('--panel "$TABLES" --no-sync', text)
        self.assertNotIn('--check --panel "$TABLES"', text)


if __name__ == "__main__":
    unittest.main()
