"""hartlib.coordinator: the signal_coordinator.py script and its sibling modules, read from SIBLING_MODULES."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import coordinator  # noqa: E402


class Coordinator(unittest.TestCase):
    def script(self, body: str, modules=("sml_a", "sml_b")) -> Path:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        tmp = Path(holder.name)
        for name in modules:
            (tmp / f"{name}.py").write_text("X = 1\n", encoding="utf-8")
        path = tmp / "signal_coordinator.py"
        path.write_text("import jmri\n" + body + "x.await(1)\n", encoding="utf-8")
        return path

    def test_the_real_script(self) -> None:
        names = coordinator.sibling_modules()
        self.assertEqual(names[0], "sml_beans")              # everything else imports it
        got = coordinator.files()
        self.assertEqual(got[0], coordinator.SCRIPT)
        self.assertEqual([p.stem for p in got[1:]], list(names))
        self.assertIn("class DigiconMqttSml(", coordinator.source())
        self.assertIn("def _parse_claim(", coordinator.source())

    def test_reads_the_tuple_in_order(self) -> None:
        path = self.script('SIBLING_MODULES = (\n    "sml_b",\n    "sml_a",\n)\n')
        self.assertEqual(coordinator.sibling_modules(path), ("sml_b", "sml_a"))
        self.assertEqual([p.name for p in coordinator.files(path)], ["signal_coordinator.py", "sml_b.py", "sml_a.py"])

    def test_no_tuple(self) -> None:
        path = self.script("NOTHING = 1\n")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "found 0"):
            coordinator.sibling_modules(path)

    def test_two_tuples(self) -> None:
        path = self.script('SIBLING_MODULES = (\n    "sml_a",\n)\nSIBLING_MODULES = (\n    "sml_b",\n)\n')
        with self.assertRaisesRegex(coordinator.CoordinatorError, "found 2"):
            coordinator.sibling_modules(path)

    def test_not_literal(self) -> None:
        path = self.script('SIBLING_MODULES = (\n    NAME,\n)\n')
        with self.assertRaisesRegex(coordinator.CoordinatorError, "not a literal tuple"):
            coordinator.sibling_modules(path)

    def test_empty(self) -> None:
        path = self.script("SIBLING_MODULES = (\n)\n")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "non-empty tuple"):
            coordinator.sibling_modules(path)

    def test_bad_names(self) -> None:
        path = self.script('SIBLING_MODULES = (\n    "sml_a",\n    "../sml_b",\n    "sml_b.py",\n)\n')
        with self.assertRaisesRegex(coordinator.CoordinatorError, r"not module names: \['\.\./sml_b', 'sml_b\.py'\]"):
            coordinator.sibling_modules(path)

    def test_duplicate(self) -> None:
        path = self.script('SIBLING_MODULES = (\n    "sml_a",\n    "sml_a",\n)\n')
        with self.assertRaisesRegex(coordinator.CoordinatorError, r"\['sml_a'\] more than once"):
            coordinator.sibling_modules(path)

    def test_missing_module_file(self) -> None:
        path = self.script('SIBLING_MODULES = (\n    "sml_a",\n    "sml_c",\n)\n')
        with self.assertRaisesRegex(coordinator.CoordinatorError, r"no \.py beside it: \['sml_c'\]"):
            coordinator.sibling_modules(path)

    def test_unreadable_script(self) -> None:
        with self.assertRaisesRegex(coordinator.CoordinatorError, "cannot read"):
            coordinator.sibling_modules(Path(tempfile.gettempdir()) / "no-such-dir" / "signal_coordinator.py")

    def test_the_real_panel_status(self) -> None:
        names = coordinator.panel_status_parts()
        self.assertEqual(names, coordinator.sibling_modules(coordinator.PANEL_STATUS))
        got = coordinator.files(coordinator.PANEL_STATUS)
        self.assertEqual(got[0], coordinator.PANEL_STATUS)
        self.assertEqual([p.stem for p in got[1:]], list(names))
        self.assertTrue(all(n.startswith("panel_status_") for n in names), names)

    def test_panel_status_reads_parts_not_sibling_modules(self) -> None:
        path = self.script('SIBLING_MODULES = (\n    "sml_a",\n)\nPARTS = (\n    "sml_b",\n)\n')
        ps = path.with_name("panel_status.py")
        path.rename(ps)
        self.assertEqual(coordinator.sibling_modules(ps), ("sml_b",))
        ps.write_text('SIBLING_MODULES = (\n    "sml_a",\n)\n', encoding="utf-8")
        with self.assertRaisesRegex(coordinator.CoordinatorError, "one PARTS = .* found 0"):
            coordinator.sibling_modules(ps)

    def test_a_script_without_parts(self) -> None:
        path = self.script('SIBLING_MODULES = (\n    "sml_a",\n)\n')
        other = path.with_name("mimic_relay.py")
        path.rename(other)
        with self.assertRaisesRegex(coordinator.CoordinatorError, "not a script with parts"):
            coordinator.sibling_modules(other)


if __name__ == "__main__":
    unittest.main()
