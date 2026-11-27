"""hartlib.tables_sections: the sections of the generated tables, AlphanumComparator order and the Store's bean
order; and the names tables_build still gives for the modules split out of it."""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hartlib import (jmri_bean, startup_logixng, tables, tables_build, tables_normal, tables_roundtrip,  # noqa: E402
                     tables_sections as ts, tables_sml)
from xml_need import need  # noqa: E402


class Order(unittest.TestCase):
    def test_digit_runs_compare_as_numbers_and_a_prefix_first(self) -> None:
        self.assertEqual(["IB2", "IB10", "IB10a", "IS:A", "IS:B2"],
                         ts.jmri_order(["IS:B2", "IB10a", "IB10", "IS:A", "IB2"]))
        self.assertLess(ts.alphanum_key("IT9"), ts.alphanum_key("IT10"))

    def test_a_block_s_names_only_pass_is_a_group_of_its_own(self) -> None:
        names_only = ET.fromstring("<block><systemName>IB1</systemName><userName>A</userName></block>")
        full = ET.fromstring("<block><systemName>IB1</systemName><permissive>no</permissive></block>")
        self.assertEqual(("block-names", "block", "bean"),
                         (ts.sort_group(names_only), ts.sort_group(full), ts.sort_group(ET.Element("sensor"))))

    def test_settings_keep_their_place_and_beans_take_store_order(self) -> None:
        root = ET.fromstring("<layout-config><turnouts class='c'><operations /><turnout><systemName>IT10</systemName>"
                             "</turnout><defaultclosedspeed /><turnout><systemName>IT9</systemName></turnout>"
                             "</turnouts></layout-config>")
        ts.jmri_sort(root)
        self.assertEqual(["operations", "IT9", "defaultclosedspeed", "IT10"],
                         [tables.system_name(e) or e.tag for e in tables.elements(need(root, "turnouts"))])
        self.assertEqual(("turnouts", "c"), ts.section_key(need(root, "turnouts")))

    def test_sub_sets_text_only_when_given(self) -> None:
        el = ET.Element("x")
        self.assertIsNone(ts.sub(el, "a", k="v").text)
        self.assertEqual("t", ts.sub(el, "b", "t").text)
        self.assertEqual({"k": "v"}, need(el, "a").attrib)


class SplitNames(unittest.TestCase):
    """tables_build gives the names its callers read there, as the very objects of the modules that hold them."""

    def test_each_name_is_its_module_s(self) -> None:
        for module, names in ((ts, ("TablesBuildError", "SECTIONS", "MASTER_SECTIONS", "BLOCKS", "jmri_sort",
                                    "sort_group", "section_key", "finish", "jmri_order")),
                              (jmri_bean, ("bean_json", "row_beans", "kept_beans")),
                              (startup_logixng, ("START_ACTIONS", "start_logixng")),
                              (tables_normal, ("PROLOG", "EPILOG", "ENVELOPE_DROPS", "normalise_store",
                                               "strip_envelope", "envelope_items")),
                              (tables_sml, ("DISCOVERED", "merge_discovered", "read_discovered", "digicon_masts",
                                            "disable_digicon", "enabled_digicon", "missing_logic")),
                              (tables_roundtrip, ("roundtrip_differences", "roundtrip_report"))):
            for name in names:
                with self.subTest(module=module.__name__, name=name):
                    self.assertIs(getattr(module, name), getattr(tables_build, name))


if __name__ == "__main__":
    unittest.main()
