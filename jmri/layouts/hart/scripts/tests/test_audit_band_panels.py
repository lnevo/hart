"""audit_panel_contracts: the band panels (hartlib.tables.BAND_PANEL_NAMES, 2026-11-22) are all in the deployment
tables or none, and the Layout Editor count follows them."""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_panel_contracts as apc  # noqa: E402

tables = apc.tables
BANDS = list(tables.BAND_PANEL_NAMES.values())


def root_with(*names):
    root = ET.Element("layout-config")
    for name in ("HART Railroad", *names):
        ET.SubElement(root, "LayoutEditor", name=name)
    return root


class BandPanelsIn(unittest.TestCase):
    def test_all_three(self):
        self.assertTrue(apc.band_panels_in(root_with(*BANDS)))

    def test_none(self):
        self.assertFalse(apc.band_panels_in(root_with()))

    def test_some_but_not_all_names_the_missing(self):
        with self.assertRaisesRegex(ValueError, f"band panels missing: {BANDS[2]}"):
            apc.band_panels_in(root_with(*BANDS[:2]))


class ExpectedBundle(unittest.TestCase):
    def test_the_count_is_the_main_panel_its_bands_and_an_unparked_dispatcher(self):
        parked = {"uss", "dispatcher", "nx"}
        self.assertEqual(apc.expected_bundle(parked), (0, 0, 4))
        self.assertEqual(apc.expected_bundle(parked, band_panels=False), (0, 0, 1))
        self.assertEqual(apc.expected_bundle({"nx"}), (1, 1, 5))


class DeploymentNeedsTheBands(unittest.TestCase):
    def audit(self, root, **kw):
        audit = apc.Audit("deployment", Path("tables.xml"))
        apc.audit_generated_dispatcher(root, audit, generated=True, **kw)
        return [e for e in audit.errors if "band panels" in e or "LayoutEditor=" in e]

    def test_deployment_tables_without_the_bands_fail(self):
        errors = self.audit(root_with())
        self.assertTrue(any("are missing: build_tables.py adds them" in e for e in errors), errors)

    def test_deployment_tables_with_the_bands_pass_the_count(self):
        self.assertEqual(self.audit(root_with(*BANDS)), [])

    def test_the_layout_editor_build_alone_holds_none(self):
        self.assertEqual(self.audit(root_with(), band_panels=False), [])
        errors = self.audit(root_with(*BANDS), band_panels=False)
        self.assertTrue(any("made alone" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
