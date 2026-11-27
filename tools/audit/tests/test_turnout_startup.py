"""The main and upper virtual turnouts' startup positions: build_device_map.startup_thrown picks the switches whose main
route runs through the diverging leg (written as the turnout rows' start, naming-layers step 9),
hartlib.tables_build.start_actions and hartlib.startup_logixng.start_logixng write an ActionTurnout per turnout into
the startup LogixNG (naming-layers step 11), and hartlib.level_devices reads them back and refuses anything else."""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/schematic"))
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
from hartlib import devices  # noqa: E402
from hartlib import level_devices as L  # noqa: E402
from hartlib import startup_logixng, tables_sections, tables_build as tb  # noqa: E402

BLOCKS = ["107-109", "OS225a"]
SENSORS = [L.SENSOR_PREFIX + b for b in BLOCKS]


def tables_root() -> ET.Element:
    root = ET.Element("layout-config")
    for tag, cls in (tables_sections.LOGIXNGS, tables_sections.CONDITIONALNGS, tables_sections.DIGITAL_ACTIONS):
        ET.SubElement(root, tag, {"class": cls})
    return root


def row(layer: str, name: str, start: str) -> dict:
    return {**dict.fromkeys(devices.COLUMNS, ""), "level": "2", "layer": layer, "user_name": name,
            "assignment": "virtual", "jmri_name": name, "start": start}


def actions(turnouts: dict[str, str]) -> list[ET.Element]:
    """The startup actions of the two block sensors (inactive) and `turnouts` ({turnout: start})."""
    return tb.start_actions([row("occupancy", s, "inactive") for s in SENSORS]
                            + [row("turnout", t, start) for t, start in turnouts.items()])


class StartupActions(unittest.TestCase):
    def test_round_trip(self):
        root = tables_root()
        startup_logixng.start_logixng(root, actions({L.TURNOUT_PREFIX + "109": "closed", L.TURNOUT_PREFIX + "227": "thrown"}))
        self.assertEqual(L.turnout_states(root), {L.TURNOUT_PREFIX + "109": "Closed", L.TURNOUT_PREFIX + "227": "Thrown"})
        self.assertEqual(L.clear_sensors(root), sorted(SENSORS))       # the turnout actions do not break the reader

    def test_a_state_other_than_closed_or_thrown_stops_the_build(self):
        with self.assertRaisesRegex(tb.TablesBuildError, "toggle"):
            actions({L.TURNOUT_PREFIX + "109": "toggle"})

    def test_a_field_row_with_a_start_stops_the_build(self):
        """Only a virtual bean is set when the tables load: a field device reports its own state."""
        with self.assertRaisesRegex(tb.TablesBuildError, "only a virtual detector or turnout"):
            tb.start_actions([dict(row("turnout", "M2T408", "closed"), assignment="field")])

    def test_the_frame_stops_on_a_template_with_no_logixng_section_or_its_names(self):
        root = ET.Element("layout-config")
        with self.assertRaisesRegex(tb.TablesBuildError, "no LogixNGs, LogixNGConditionalNGs"):
            startup_logixng.start_logixng(root, actions({}))
        root = tables_root()
        startup_logixng.start_logixng(root, actions({}))
        with self.assertRaisesRegex(tb.TablesBuildError, "holds the startup LogixNG's names"):
            startup_logixng.start_logixng(root, actions({}))

    def test_a_toggle_or_a_field_turnout_is_refused_on_read(self):
        for turnout, state in ((L.TURNOUT_PREFIX + "109", "Toggle"), ("MT408", "Closed")):
            root = tables_root()
            startup_logixng.start_logixng(root, actions({L.TURNOUT_PREFIX + "109": "closed"}))
            act = next(a for a in root.find("LogixNGDigitalActions") if a.tag == "ActionTurnout")
            act.find("namedBean/name").text = turnout
            act.find("state/enum").text = state
            with self.subTest(turnout=turnout, state=state):
                with self.assertRaises(ValueError):
                    L.turnout_states(root)
                with self.assertRaises(ValueError):
                    L.clear_sensors(root)


class StartupThrown(unittest.TestCase):
    def test_227_and_229_line_the_peninsula_loop(self):
        import build_device_map as bdm
        try:
            bands, _joined, _runs, _corners = bdm.solve()
        except Exception as exc:        # the schematic-maps plugin is not checked out here
            self.skipTest(f"no schematic: {exc}")
        self.assertEqual(bdm.startup_thrown(bands), {"227", "229"})


if __name__ == "__main__":
    unittest.main()
