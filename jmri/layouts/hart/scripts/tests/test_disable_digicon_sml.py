"""disable_digicon_sml_in_tables.py: a check over hartlib.tables_build's Digicon rule (R9c); the generator applies it
and the deploy no longer rewrites tables.xml."""
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPT = ROOT / "jmri/layouts/hart/scripts/disable_digicon_sml_in_tables.py"
NEW_TABLES = ROOT / "jmri/layouts/hart/output/tables.xml"
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import tables, tables_build as tb  # noqa: E402


def load():
    spec = importlib.util.spec_from_file_location("disable_digicon_sml_in_tables", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


SAMPLE = b"""<layout-config>
  <signalmasts>
    <signalmast class="x"><systemName>IF$shsm:basic:one-searchlight(IH432)</systemName><userName>Mast 6LB</userName></signalmast>
    <signalmast class="x"><systemName>IF$shsm:basic:one-searchlight(IH:HART:C1:6LA)</systemName><userName>Mast 6LA</userName></signalmast>
  </signalmasts>
  <signalmastlogics>
    <signalmastlogic source="Mast 6LB">
      <destinationMast destination="Mast 6LA">
        <enabled>yes</enabled>
      </destinationMast>
      <destinationMast destination="Mast 8LA">
        <enabled>no</enabled>
      </destinationMast>
    </signalmastlogic>
    <signalmastlogic source="Mast 6LA">
      <destinationMast destination="Mast 6LB">
        <enabled>yes</enabled>
      </destinationMast>
    </signalmastlogic>
  </signalmastlogics>
</layout-config>
"""


class DisableDigiconSmlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.wiring = Path(self.tmp.name) / "wiring.csv"
        self.wiring.write_text("mast_user_name\nMast 6LB\nMast 6LA\n", encoding="utf-8")
        self.panel = Path(self.tmp.name) / "tables.xml"
        self.panel.write_bytes(SAMPLE)

    def test_only_planned_masts_on_wired_heads_are_digicon(self) -> None:
        root = tables.loads(SAMPLE).root
        self.assertEqual({"Mast 6LB"}, tb.digicon_masts(root, self.wiring))   # 6LA is on an internal head

    def test_disable_flips_digicon_source_destinations_only(self) -> None:
        root = tables.loads(SAMPLE).root
        self.assertEqual([("Mast 6LB", "Mast 6LA")], tb.enabled_digicon(root, {"Mast 6LB"}))
        self.assertEqual((1, 1), tb.disable_digicon(root, {"Mast 6LB"}))
        self.assertEqual([], tb.enabled_digicon(root, {"Mast 6LB"}))
        other = tables.mast_logic_sources(root)["Mast 6LA"]
        self.assertEqual("yes", other.find("destinationMast/enabled").text)

    def test_a_destination_with_no_enabled_stops(self) -> None:
        root = tables.loads(SAMPLE.replace(b"<enabled>no</enabled>", b"")).root
        with self.assertRaises(tb.TablesBuildError):
            tb.disable_digicon(root, {"Mast 6LB"})

    def test_check_and_patch_another_file(self) -> None:
        mod = load()
        mod.WIRING = self.wiring
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(1, mod.main(["--check", "--panel", str(self.panel)]))
            self.assertEqual(0, mod.main(["--panel", str(self.panel)]))
            self.assertEqual(0, mod.main(["--check", "--panel", str(self.panel)]))
        self.assertIn("Mast 6LB -> Mast 6LA", err.getvalue())

    def test_the_generated_tables_are_never_patched(self) -> None:
        mod = load()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
            self.assertEqual(2, mod.main(["--panel", str(NEW_TABLES)]))
        self.assertIn("build_tables.py", err.getvalue())

    def test_working_tables_digicon_sml_disabled(self) -> None:
        root = tables.read(NEW_TABLES)
        self.assertEqual([], tb.enabled_digicon(root, tb.digicon_masts(root)))

    def test_deploy_ships_the_committed_bytes(self) -> None:
        """The deploy only checks the rule (it refuses an enabled destination) and never rewrites the file."""
        text = (ROOT / "tools/hosts/sync_hart_package.sh").read_text(encoding="utf-8")
        calls = [line for line in text.splitlines() if "disable_digicon_sml_in_tables.py" in line]
        self.assertTrue(calls)
        self.assertTrue(all('--check --panel "$TABLES"' in line for line in calls), calls)


if __name__ == "__main__":
    unittest.main()
