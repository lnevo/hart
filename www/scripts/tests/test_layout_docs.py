"""The layout documentation page matches its template, block_lengths.csv (one row per detector), the device
master's names and DCC addresses and the station names; drawing D2 states the same section count, plans P3 and P4 the
same lengths and the plans the live switch numbers; a rename in the field file renames the track or the switch on the
page, and a rename in the stations file the station (and stops on a drawing's station label until it is edited);
the siding's car count is in 50 ft cars at the plan's scale; the hand-edited drawings carry no SOQ wording."""
import csv
import io
import re
import shutil
import sys
import tempfile
import tokenize
import unittest
from dataclasses import replace
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import build_layout_docs as ld  # noqa: E402

devices = ld.devices


def staging_row(layer: str, user_name: str, role: str, **cells: str) -> ld.DeviceRow:
    """A staging row of the device master, as master_rows holds it."""
    return ld.DeviceRow(level=1, layer=layer, user_name=user_name, role=role, **cells)


class LayoutDocs(unittest.TestCase):
    def test_outputs_are_current(self):
        for path, text in ld.outputs().items():
            self.assertTrue(path.exists() and path.read_text() == text,
                            f"{path} is stale: run python3 www/scripts/build_layout_docs.py")

    def test_page_reads_nothing_from_the_soq(self):
        # The SOQ is submitted and frozen; the page is maintained on its own (owner, 2026-11-22).
        page = ld.PAGE.read_text()
        self.assertNotIn("docs/ap/electrical", page)
        src = (SCRIPTS / "build_layout_docs.py").read_text()
        strings = [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.STRING]
        self.assertFalse([s for s in strings[1:] if "ap/electrical" in s or "build_soq" in s])   # [0] is the docstring
        for rel in set(re.findall(r'\.\./(assets/behind/layout-docs/[\w./-]+)', page)):
            self.assertTrue((ld.PORTAL / rel).is_file(), rel)

    def test_drawings_carry_no_soq_wording(self):
        ld.check_drawings()

    def test_every_section_has_a_label(self):
        master = ld.master_rows()
        for s in ld.detected_sections(master=master):
            ld.label(s, master)

    def test_every_label_is_a_live_block(self):
        # a label for a block the plan no longer has would hide a renumbered switch
        master = ld.master_rows()
        self.assertFalse([bid for bid in ld.LABELS if (ld.LEVEL, bid) not in master])

    def test_parts_fold_into_their_detector(self):
        def length(bid, sensor, plan, measured=None):
            return ld.block_lengths.Block(2, "1", bid, bid, sensor, plan, "")
        timed = {"os:1": ld.block_lengths.Measured(2, "os:1", 22.6, "loop1 laps", "2026-11-08", "")}
        lengths = [length("os:1", "Block 4-2", 9.2, 22.6), length("block:1B-3A:1/2", "Block 4-2", 5.0),
                   length("os:9", "Block 13-8", 9.2), length("block:9A-11C", "Block 13-8", 10.3),
                   length("block:109-111", "BS Switch 109", 5.4)]
        master = {("1", "os:1"): staging_row("block", "OS Switch 1", "os"),
                  ("1", "block:1B-3A:1/2"): staging_row("block", "Track 1-3 at 1", "part", part_of="OS Switch 1"),
                  ("1", "os:9"): staging_row("block", "OS Switch 9", "os"),
                  ("1", "block:9A-11C"): staging_row("block", "Track 9-11", "part", part_of="OS Switch 9")}
        got = ld.detected_sections({r.id: r for r in lengths}, master, {"OS Switch 1": timed["os:1"]})
        self.assertEqual([(s["id"], s["name"], s["inches"], s["estimate"]) for s in got],
                         [("os:1", "OS Switch 1", 22.6, False), ("os:9", "OS Switch 9", 19.5, True)])
        master[("1", "block:9A-11C")] = replace(master[("1", "block:9A-11C")], part_of="OS Switch 1")   # wrong block
        with self.assertRaises(ld.LayoutDocsError):
            ld.detected_sections({r.id: r for r in lengths}, master, {"OS Switch 1": timed["os:1"]})

    def test_plans_label_the_live_switches(self):
        master = ld.master_rows()
        ld.check_switch_labels(master)
        key = (ld.LEVEL, "switch:5")
        with self.assertRaises(ld.LayoutDocsError):
            ld.check_switch_labels({**master, key: replace(master[key], user_name="Switch 6")})

    def test_only_switch_labels_count(self):
        svg = ('<text x="1" font-weight="bold" fill="#5f6e7a">5</text><text class="lb">Sw 3</text>'
               '<text font-size="9">100</text><text font-weight="bold" fill="#5f6e7a">WEST</text>')
        self.assertEqual(ld.drawn_switches(svg), ["3", "5"])         # a plain number (a dimension) is no label
    def test_the_dcc_address_is_the_turnouts(self):
        # "DCC Switch N" follows switch number N, not DCC address N: the page states both, from the turnout's row
        row = ld.master_rows()[(ld.LEVEL, "switch:3")]
        self.assertIn(f"{row.user_name} (DCC address {row.dcc}) set normal", ld.PAGE.read_text())

    def test_the_station_at_a_switch_is_the_smallest_holding_it(self):
        st = ld.railroad.Station
        places = [st(2, 1, "Brick", ("1", "3"), "", "BK"), st(3, 1, "West Yard", ("3",), "", "BK"),
                  st(4, 2, "Upper", ("3",), "", "UP")]
        self.assertEqual(ld.station_at(places, "switch:3"), "West Yard")
        self.assertEqual(ld.station_at(places, "switch:1"), "Brick")
        with self.assertRaises(ld.LayoutDocsError):
            ld.station_at(places, "switch:5")
        with self.assertRaises(ld.LayoutDocsError):
            ld.station_at(places + [st(5, 1, "Other", ("3",), "", "OT")], "switch:3")

    def test_the_siding_counts_50_ft_cars_at_the_plans_scale(self):
        self.assertAlmostEqual(ld.car_inches(87.1), 55 * 12 / 87.1)
        self.assertAlmostEqual(ld.car_inches(87.1) - 7.58, 0, places=2)    # 6.9 in of body plus the couplers
        siding = next(s for s in ld.detected_sections() if s["id"] == ld.SIDING)
        cars = str(round(float(f"{siding['inches']:.0f}") / ld.car_inches()))
        self.assertEqual(ld.facts(ld.detected_sections())["SIDING_CARS"], cars)
        self.assertIn(f"about {cars} cars of 50 ft", ld.PAGE.read_text())

    def test_a_missing_scale_stops_by_name(self):
        with mock.patch.object(ld.layer_files, "merged_section", return_value={}):
            with self.assertRaisesRegex(ld.LayoutDocsError, "staging scale_ratio"):
                ld.car_inches()

    def test_station_names_in_drawings_are_labels(self):
        master = ld.master_rows()
        places = ld.railroad.read_stations(ld.railroad.Sources.under().stations)
        ld.check_station_labels(places, master)                               # the drawings today
        with tempfile.TemporaryDirectory() as tmp:
            svg = Path(tmp) / "P9.svg"
            svg.write_text('<svg><text x="1">Plane</text></svg>')
            with self.assertRaises(ld.LayoutDocsError):                              # a typed name, untagged
                ld.check_station_labels(places, master, [svg])
            svg.write_text('<svg><text x="1" data-station="switch:5">Plane</text><text>siding</text></svg>')
            ld.check_station_labels(places, master, [svg])
            svg.write_text('<svg><text data-station="switch:5">Barn</text></svg>')
            with self.assertRaises(ld.LayoutDocsError):                              # the wrong station for the switch
                ld.check_station_labels(places, master, [svg])
            svg.write_text('<svg><text data-station="switch:5"><tspan x="1">Plane</tspan></text></svg>')
            ld.check_station_labels(places, master, [svg])                   # Inkscape puts the text in a tspan
            svg.write_text('<svg><text data-station="switch:5"><tspan x="1">Barn</tspan></text></svg>')
            with self.assertRaises(ld.LayoutDocsError):
                ld.check_station_labels(places, master, [svg])
            for typed in ('<text>PLANE</text>', '<text><tspan>Plane</tspan><tspan>West</tspan></text>',
                          '<text data-station="switch:5">Plane</text><text>plane</text>'):
                svg.write_text(f'<svg>{typed}</svg>')
                with self.assertRaises(ld.LayoutDocsError, msg=typed):               # untagged, in any case
                    ld.check_station_labels(places, master, [svg])
            yard = ld.railroad.Station(9, 1, "Yard", ("15",), "", "YD")
            svg.write_text('<svg><text>Yard lead</text><desc>The yard of five tracks</desc></svg>')
            ld.check_station_labels(places + [yard], master, [svg])          # a word in a longer label is no name

    def test_d2_must_state_the_live_count(self):
        ld.check_d2(len(ld.detected_sections()))
        with self.assertRaises(ld.LayoutDocsError):
            ld.check_d2(len(ld.detected_sections()) + 1)

    def test_plans_must_state_the_live_lengths(self):
        fact = ld.facts(ld.detected_sections())
        ld.check_plans(fact)
        with self.assertRaises(ld.LayoutDocsError):
            ld.check_plans({**fact, "SIDING_IN": str(int(fact["SIDING_IN"]) + 1)})

    def facts_of(self, os_ids, estimate=False):
        rows = [{"id": i, "inches": 100.0, "estimate": estimate} for i in (ld.RS1, ld.SIDING, *ld.YARD)]
        return ld.facts(rows + [{"id": i, "inches": 9.0, "estimate": True} for i in os_ids])

    def test_crossovers_are_in_switch_number_order(self):
        master = {(ld.LEVEL, f"switch:{n}"): staging_row("turnout", f"Switch {u}", "turnout")
                  for n, u in ((7, 107), (23, 9), (35, 35))}
        rows = [{"id": i, "inches": 100.0, "estimate": False} for i in (ld.RS1, ld.SIDING, *ld.YARD)]
        rows += [{"id": i, "inches": 9.0, "estimate": True} for i in ("os:7:A-5B", "os:23:A-1A", "os:35:A-33A")]
        self.assertEqual(ld.facts(rows, master)["CROSSOVERS"], "crossovers at Switches 9, 35 and 107")

    def test_crossovers_come_from_the_os_halves(self):
        self.assertEqual(self.facts_of(("os:35:A-33A", "os:7:A-5B", "os:23:A-1A", "os:23:A-31B", "os:3"))["CROSSOVERS"],
                         "crossovers at Switches 7, 23 and 35")
        self.assertEqual(self.facts_of(("os:7:A-5B", "os:7:A-13C"))["CROSSOVERS"], "a crossover at Switch 7")

    def test_an_estimated_length_is_said_as_about(self):
        self.assertEqual(self.facts_of(("os:7:A-5B",))["YARD_IN"], "100 to 100")
        self.assertEqual(self.facts_of(("os:7:A-5B",), estimate=True)["YARD_IN"], "about 100 to 100")


class RenameReachesThePage(unittest.TestCase):
    """A copy of the device master whose field file renames a staging track and an OS block, as the owner would;
    nothing else changes (block_lengths.csv keeps its labels, as before the length-labels step runs)."""
    RENAMES = {("1", "block:17C-29C"): "Track Renamed Yard Two", ("1", "os:19"): "OS Renamed Nineteen",
               ("1", "switch:5"): "Switch 105"}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        here = devices.Files.here()
        for src in (here.master, here.dictionary, here.field):
            shutil.copy(src, Path(cls.tmp.name) / src.name)
        cls.files = devices.Files.under(Path(cls.tmp.name))
        rows = list(csv.DictReader(io.StringIO(cls.files.field.read_text(encoding="utf-8"))))
        hit = 0
        for r in rows:
            if (r["level"], r["id"]) in cls.RENAMES:
                r["user_name"] = cls.RENAMES[(r["level"], r["id"])]
                hit += 1
        assert hit == len(cls.RENAMES), hit
        cls.files.field.write_text(devices.master_text(rows), encoding="utf-8")
        try:                                                      # the plans unedited: the renamed switch stops
            ld.outputs(cls.files)
            cls.stopped = ""
        except ld.LayoutDocsError as exc:
            cls.stopped = str(exc)
        cls.plans = []                                            # the plans with Switch 5 relabelled, as the owner would
        for svg in ld.PLANS:
            copy = Path(cls.tmp.name) / svg.name
            copy.write_text(re.sub(r"(<text\b[^>]*>)(Sw )?5<", r"\g<1>\g<2>105<", svg.read_text()))
            cls.plans.append(copy)
        cls.page = ld.outputs(cls.files, plans=cls.plans)[ld.PAGE]
        cls.live = ld.outputs()[ld.PAGE]                      # the same build on the real device master
        master = ld.master_rows()
        cls.old = {k: ld.bare(master[k].user_name) for k in cls.RENAMES}
        cls.new = {k: ld.bare(v) for k, v in cls.RENAMES.items()}
        cls.yard = [cls.new.get(("1", bid)) or ld.bare(master[("1", bid)].user_name) for bid in ld.YARD]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_renamed_track_is_on_the_page(self):
        track = ("1", "block:17C-29C")
        self.assertIn(f"<td>Yard track Y2</td><td>{self.new[track]}</td>", self.page)     # the section list
        self.assertIn("South Yard " + ", ".join(self.yard), self.page)                    # the overview's label table
        self.assertNotIn(f"<td>Yard track Y2</td><td>{self.old[track]}</td>", self.page)

    def test_the_renamed_os_block_keeps_its_parts(self):
        os19 = ("1", "os:19")
        self.assertIn(f"<td>Turnout 19</td><td>{self.new[os19]}</td>", self.page)
        self.assertNotIn(f"<td>{self.old[os19]}</td>", self.page)

    def test_the_renamed_switch_is_on_the_page(self):
        self.assertIn("The siding beside the main line, Switch 105 to Switch 7", self.page)     # the label table
        self.assertIn("<td>Turnout 105</td>", self.page)                                       # the section list
        self.assertNotIn("Switch 5 ", self.page)

    def test_unedited_plans_stop_the_build(self):
        self.assertIn("labels switches", self.stopped)

    def test_nothing_else_changes(self):
        page = self.page.replace("Turnout 105", "Turnout 5")
        for key, name in self.new.items():
            page = page.replace(name, self.old[key])
        self.assertEqual(page, self.live)


class StationRenameReachesThePage(unittest.TestCase):
    """A copy of the stations file with two stations renamed, as the owner would; nothing else changes."""
    RENAMES = {"Plane": "Renamed Plane", "South Yard": "Renamed South Yard"}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        src = ld.railroad.Sources.under().stations
        copy = Path(cls.tmp.name) / src.name
        with src.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fields, rows = reader.fieldnames, list(reader)
        assert {r["station"] for r in rows} >= set(cls.RENAMES)
        for r in rows:
            r["station"] = cls.RENAMES.get(r["station"], r["station"])
        with copy.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fields)
            w.writeheader()
            w.writerows(rows)
        cls.copy = copy
        cls.page = ld.outputs(stations=copy)[ld.PAGE]
        cls.live = ld.outputs()[ld.PAGE]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_renamed_stations_are_on_the_page(self):
        self.assertRegex(self.page, r"<td>[^<]*, at Renamed Plane</td>")                     # the passing siding
        self.assertIn("<td>Renamed South Yard ", self.page)                                   # the yard tracks

    def test_a_renamed_station_stops_on_a_drawing_label(self):
        # a drawing labelling the station at Switch 5 holds the old name: the build stops until it is edited
        with tempfile.TemporaryDirectory() as tmp:
            label = '<text x="1" data-station="switch:5">{}</text>'
            plans = []
            for svg in ld.PLANS:
                copy = Path(tmp) / svg.name
                copy.write_text(svg.read_text().replace("</svg>", label.format("Plane") + "</svg>"))
                plans.append(copy)
            ld.outputs(drawings=plans)                                       # the live names: it builds
            with self.assertRaisesRegex(ld.LayoutDocsError, "Renamed Plane"):
                ld.outputs(stations=self.copy, drawings=plans)
            plans[0].write_text(plans[0].read_text().replace(label.format("Plane"), label.format("Renamed Plane")))
            with self.assertRaisesRegex(ld.LayoutDocsError, "Renamed Plane"):         # one drawing still has the old name
                ld.outputs(stations=self.copy, drawings=plans)
            for p in plans:
                p.write_text(p.read_text().replace(label.format("Plane"), label.format("Renamed Plane")))
            self.assertEqual(ld.outputs(stations=self.copy, drawings=plans)[ld.PAGE], self.page)

    def test_nothing_else_changes(self):
        page = self.page
        for old, new in self.RENAMES.items():
            page = page.replace(new, old)
        self.assertEqual(page, self.live)


class MainExitTest(unittest.TestCase):
    def test_main_exits_with_the_error_and_writes_nothing(self) -> None:
        with mock.patch.object(ld, "outputs", side_effect=ld.LayoutDocsError("build_layout_docs: stop")), \
                mock.patch.object(sys, "argv", ["build_layout_docs.py"]), self.assertRaises(SystemExit) as cm:
            ld.main()
        self.assertEqual(cm.exception.code, "build_layout_docs: stop")


if __name__ == "__main__":
    unittest.main()
