from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def load_module():
    path = SCRIPTS / "ensure_dispatcher_roster_profiles.py"
    spec = importlib.util.spec_from_file_location("ensure_dispatcher_roster_profiles", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mod = load_module()

ROSTER_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<roster-config>
  <roster>
    <locomotive id="2091" fileName="20910.xml" dccAddress="2091" />
    <locomotive id="1827" fileName="18270.xml" dccAddress="1827" />
  </roster>
</roster-config>
"""

LOCO_WITHOUT = """<?xml version="1.0" encoding="UTF-8"?>
<locomotive-config>
  <locomotive id="1827" fileName="18270.xml">
    <decoder model="test" />
    <values>
      <decoderDef />
    </values>
  </locomotive>
</locomotive-config>
"""

LOCO_WITH = """<?xml version="1.0" encoding="UTF-8"?>
<locomotive-config>
  <locomotive id="2091" fileName="20910.xml">
    <speedprofile>
      <speeds>
        <speed>
          <step>1000</step>
          <forward>123.0</forward>
          <reverse>123.0</reverse>
        </speed>
      </speeds>
    </speedprofile>
    <values>
      <decoderDef />
    </values>
  </locomotive>
</locomotive-config>
"""


class EnsureDispatcherRosterProfilesTest(unittest.TestCase):
    def test_adds_profile_before_values_and_leaves_existing(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            roster_dir = base / "roster"
            roster_dir.mkdir()
            (base / "roster.xml").write_text(ROSTER_INDEX, encoding="utf-8")
            without = roster_dir / "18270.xml"
            with_profile = roster_dir / "20910.xml"
            without.write_text(LOCO_WITHOUT, encoding="utf-8")
            with_profile.write_text(LOCO_WITH, encoding="utf-8")

            self.assertEqual(mod.ensure_profile(without), "added")
            self.assertEqual(mod.ensure_profile(with_profile), "has-profile")
            self.assertEqual(mod.ensure_profile(without), "has-profile")

            added = without.read_text(encoding="utf-8")
            kept = with_profile.read_text(encoding="utf-8")
            self.assertIn("<speedprofile>", added)
            self.assertIn("<step>1000</step>", added)
            self.assertIn("<forward>400.0</forward>", added)
            self.assertLess(added.find("<speedprofile>"), added.find("<values>"))
            self.assertIn("<forward>123.0</forward>", kept)
            self.assertNotIn("<forward>400.0</forward>", kept)

    def test_lists_live_files_from_roster_xml(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            roster_dir = base / "roster"
            roster_dir.mkdir()
            roster_xml = base / "roster.xml"
            roster_xml.write_text(ROSTER_INDEX, encoding="utf-8")
            files = mod.live_loco_files(roster_xml, roster_dir)
            self.assertEqual(
                [(ident, path.name) for ident, path in files],
                [("2091", "20910.xml"), ("1827", "18270.xml")],
            )


if __name__ == "__main__":
    unittest.main()
