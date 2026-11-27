"""The CATS desk bindings each level's builder gives, on the committed railroad (the sheet, tables.xml, devices.csv,
switches.csv, masts.csv), held to cats/panels/HART_CTC.bindings.json part by part: the
staging switches, OS blocks, destinations, half labels, blocks and masts, and the main and upper switches, blocks,
helix blocks and masts. These pin the builders' behaviour so they can be merged into one without a desk changing.
They go through build_cats_panel (the names it exports), so they hold for any module layout behind it.

The expected values come from the committed bindings and the source files, not from today's counts, so a correct
rebuild after a layout edit still passes. Skipped when the schematic plugin is not checked out; a plugin at another
commit than the pinned one fails.
"""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_cats_panel as B  # noqa: E402
from hartlib import devices, level_devices  # noqa: E402

BUILT = {}
PLUGIN = B.pd.REPO / "external/model-railroad-skills/plugins/schematic-maps"     # where publish_draft.plugin looks


def built():
    """The committed railroad's bands, facts and bindings, built once for every test here, as generate() builds them."""
    if BUILT:
        return BUILT
    if not os.environ.get("SCHEMATIC_PLUGIN") and not (PLUGIN / "bin/schematic").exists():
        raise unittest.SkipTest(f"no schematic plugin at {PLUGIN.relative_to(B.pd.REPO)}")
    try:
        plugin = B.pd.plugin()
    except B.pd.PluginMissing as e:     # there, but not at its pinned commit: a failure, with the plugin's message
        raise AssertionError(f"schematic plugin: {e}") from e
    cats, sheet = B.plugin_modules(plugin)
    F = B.load_facts()
    s = B.pd.solved_sheet(sheet)
    bands = B.name_loop_halves(s.bands, F.device)
    o = B.desk_options(cats, s.opts, bands)
    bi = B.bound_index(bands)
    B.level_signals(bands, F, bi)
    with contextlib.redirect_stdout(io.StringIO()):
        got = B.bindings(bands, cats, F, o, s.opts)
    committed = json.loads(B.BINDINGS.read_text(encoding="utf-8"))
    BUILT.update(cats=cats, page=s.opts, F=F, bands=bands, o=o, bi=bi, got=got, committed=committed)
    return BUILT


def staging_turnout(e):
    """True for a switch binding that commands a staging M2T turnout (main and upper ones are internal, IT)."""
    return e["routes"]["B"]["ROUTECOMMAND"]["JMRIPREFIX"] == "M2T"


class Whole(unittest.TestCase):
    def test_the_bindings_are_the_committed_ones(self):
        k = built()
        self.assertEqual(json.dumps(k["got"], indent=1, sort_keys=True) + "\n",
                         B.BINDINGS.read_text(encoding="utf-8"))

    def test_the_counts_follow_the_sources(self):
        """One staging switch binding per staging row of switches.csv, the main and upper ones the internal turnouts of
        tables.xml, one mast per drawn staging mast and visible main or upper masts.csv row."""
        k = built()
        c, F = k["committed"], k["F"]
        self.assertEqual(sum(staging_turnout(e) for e in c["switches"].values()),
                         sum(len(sw.legs) for sw in F.switches.values()))
        level = {B.bdm.base(key) for key, e in c["switches"].items() if not staging_turnout(e)}
        self.assertEqual(level, {u.removeprefix("Switch ") for u, sn in F.turnouts.items()
                                 if sn.startswith(level_devices.TURNOUT_PREFIX)})
        staging_masts = [sg for sg in k["bands"][k["bi"]][2].get("signals") or () if sg["kind"] != "virtual"]
        self.assertEqual(len(c["masts"]), len(staging_masts) + len(B.level_masts.visible_names(levels=(2, 3))))


class StagingSwitches(unittest.TestCase):
    def setUp(self):
        k = built()
        self.F, self.band, self.opts = k["F"], k["bands"][k["bi"]][1], k["bands"][k["bi"]][2]
        self.committed = k["committed"]
        self.stored = B.staging_names(self.band, B.pd.DATA)
        self.os_of = B.os_blocks(self.band, self.F, self.stored)

    def test_os_blocks_one_per_switch_node(self):
        nodes = {n for n, d in self.band["nodes"].items() if d["kind"] == "switch"}
        self.assertEqual(set(self.os_of), nodes)
        self.assertEqual(len(set(self.os_of.values())), len(nodes))  # never two nodes on one OS block
        legs = {leg.os_block for sw in self.F.switches.values() for leg in sw.legs}
        self.assertEqual(set(self.os_of.values()), legs)              # every staging row of switches.csv drawn once

    def test_switch_bindings_are_the_committed_staging_ones(self):
        got = B.switch_bindings(self.band, self.F, self.os_of, self.stored)
        want = {k: e for k, e in self.committed["switches"].items() if staging_turnout(e)}
        self.assertEqual(got, want)

    def test_half_labels(self):
        """A switch with several staging rows of switches.csv is drawn as halves, labelled its number and A, B, ... one per
        row; a switch with one row has no label."""
        got = B.switch_bindings(self.band, self.F, self.os_of, self.stored)
        by_number = {}
        for key, e in got.items():
            number = int(key.split("/")[0])
            sw = self.F.switches[number]
            self.assertEqual("label" in e, len(sw.legs) > 1, key)
            if "label" in e:
                by_number.setdefault(number, set()).add(e["label"])
                leg = next(l for l in sw.legs if l.os_block == e["block"])
                self.assertEqual(B.half_label(sw, leg, self.F.half_letters), e["label"])
        self.assertTrue(by_number)
        for number, labels in by_number.items():
            self.assertEqual(labels, {f"{number}{c}" for c in "ABCD"[:len(self.F.switches[number].legs)]})

    def test_destinations_are_the_closed_and_thrown_legs(self):
        """Each staging switch's legs B and C lead to its switches.csv closed and thrown blocks, the closed one
        on the leg its binding closes the turnout for."""
        got = B.switch_bindings(self.band, self.F, self.os_of, self.stored)
        by_block = {e["block"]: (k, e) for k, e in got.items()}
        dests = set()
        for n, os_name in sorted(self.os_of.items()):
            d = self.band["nodes"][n]
            sw = self.F.switches[int(d["label"])]
            leg = next(l for l in sw.legs if l.os_block == os_name)
            to = {p: B.dest(self.band, self.os_of, n, p, self.F.helix, self.stored) for p in "BC"}
            with self.subTest(os=os_name):
                self.assertEqual(sorted(to.values()), sorted((leg.closed, leg.thrown)))
                _key, e = by_block[os_name]
                closed = next(p for p, r in e["routes"].items() if r["ROUTECOMMAND"]["command"] == "close")
                self.assertEqual(to[closed], leg.closed)
            dests |= set(to.values())
        # the helix tracks lead up the helix as one block each
        self.assertLessEqual(set(self.F.helix.values()), dests)
        self.assertEqual(set(self.F.helix.values()), {"Track " + plan for plan in self.F.helix})    # the ordinary rule


class Helix(unittest.TestCase):
    def test_the_helix_blocks(self):
        """Each helix track is its block on staging: by track_block, and by helix_block on the
        staging band's strands of that plan name; any other track is Track <name>."""
        k = built()
        helix = B.bdm.plan_bands.read_helix_tracks()          # by plan name, as dark_bindings reads them
        self.assertEqual(set(helix), {"Helix Outer", "Helix Inner"})
        self.assertEqual(k["F"].helix, {plan: h["block"] for plan, h in helix.items()})
        for plan, h in helix.items():
            self.assertEqual(B.track_block(plan, k["F"].helix), h["block"])
        self.assertEqual(B.track_block("K-2", k["F"].helix), "Track K-2")
        band = k["bands"][k["bi"]][1]
        stored = B.staging_names(band, B.pd.DATA)
        found = {}
        for sid, s in band["strands"].items():
            got = B.helix_block(("track", f"b{k['bi']}:{sid}"), helix, stored)
            if got:
                found.setdefault(got, set()).add(s["name"])
        self.assertEqual(found, {h["block"]: {plan} for plan, h in helix.items()})
        # the name store's names, by strand ID, not the drawing's
        drawn = {sid: s["name"] for sid, s in band["strands"].items() if s["name"]}
        self.assertEqual({sid: n for sid, n in stored.items() if sid in drawn}, drawn)
        key = lambda sid: ("track", f"b{k['bi']}:{sid}")         # noqa: E731
        drawn_helix = next(sid for sid, n in drawn.items() if n in helix)
        plain = next(sid for sid, s in band["strands"].items() if not s["name"])
        # a strand drawn with a helix name but stored as another track (or not at all) is no helix block
        self.assertIsNone(B.helix_block(key(drawn_helix), helix, {**stored, drawn_helix: "K-2"}))
        self.assertIsNone(B.helix_block(key(drawn_helix), helix, {}))
        # a strand drawn with no name that the store names a helix track is that helix block
        self.assertEqual(B.helix_block(key(plain), helix, {plain: "Helix Outer"}), helix["Helix Outer"]["block"])

    def test_each_helix_block_is_bound_once_from_the_device_map(self):
        blocks = built()["committed"]["blocks"]
        for name in built()["F"].helix.values():
            with self.subTest(block=name):
                bound = [e for key, e in blocks.items() if e.get("name", key) == name]
                self.assertEqual(len(bound), 1)
                self.assertEqual(bound[0]["discipline"], B.MAIN_UPPER_DISCIPLINE)
                self.assertEqual(bound[0]["occupied"]["JMRIPREFIX"], "IS")


class Blocks(unittest.TestCase):
    def setUp(self):
        k = built()
        self.k = k
        band = k["bands"][k["bi"]][1]
        self.stored = B.staging_names(band, B.pd.DATA)
        out_sw = B.switch_bindings(band, k["F"], B.os_blocks(band, k["F"], self.stored), self.stored)
        named = {key: {"block": v["block"]} for key, v in out_sw.items()}
        level_sw = self.level_switches()
        named.update({key: {"corners": v["corners"]} for key, v in level_sw.items() if "corners" in v})
        o = k["o"]
        self.P = k["cats"].panel(k["bands"], scale=o["scale"], helix_blocks=o["helix_blocks"],
                                 band_gap=o["band_gap"], title_gap=o["title_gap"], bindings={"switches": named})

    def level_switches(self):
        k = self.k
        return B.level_switch_bindings(k["bands"], k["F"], k["bi"],
                                       B.bdm.dx_corners(k["bands"], B.cats_le(k["cats"]), k["page"]))

    def test_staging_and_main_upper_blocks_are_the_committed_ones(self):
        k = self.k
        dark, log, missing, joined = B.dark_bindings(k["bands"], k["cats"], self.P, k["F"], k["bi"], self.stored)
        names = {key: v for key, v in self.P.names.items() if key[1].startswith(f"b{k['bi']}:") and key not in joined}
        staging = B.block_bindings(k["bands"][k["bi"]][1], k["F"], names, self.stored)
        self.assertFalse(set(staging) & set(dark))
        self.assertEqual(dict(staging, **dark), k["committed"]["blocks"])
        self.assertEqual(missing, k["committed"]["_main_upper_not_on_desk"])
        # the staging blocks report M2S detectors with the staging disciplines; main and upper their virtual sensors
        self.assertEqual({e["occupied"]["JMRIPREFIX"] for e in staging.values() if "occupied" in e}, {"M2S"})
        self.assertEqual({e["discipline"] for e in dark.values()}, {B.MAIN_UPPER_DISCIPLINE})
        self.assertEqual({e["occupied"]["JMRIPREFIX"] for e in dark.values() if "occupied" in e}, {"IS"})
        # the staging pieces of the helix blocks are joined to the main and upper block
        self.assertTrue(joined)
        self.assertTrue(all(key[1].startswith(f"b{k['bi']}:") for key in joined))

    def test_main_upper_switches_are_the_committed_ones(self):
        want = {key: e for key, e in self.k["committed"]["switches"].items() if not staging_turnout(e)}
        self.assertEqual(self.level_switches(), want)
        self.assertEqual({e["routes"]["B"]["ROUTECOMMAND"]["JMRIPREFIX"] for e in want.values()}, {"IT"})

    def test_a_switch_takes_the_turnout_tables_xml_holds_for_it(self):
        """A main or upper switch binds whatever turnout its row gives tables.xml (a swap to a physical turnout is
        one row edit, ADR-028), split into the desk's JMRIPREFIX and DECADDR."""
        self.assertEqual(("IT", ":HART:C3:107"), B.split_system_name("IT:HART:C3:107"))
        self.assertEqual(("M2T", "3308"), B.split_system_name("M2T3308"))
        self.assertEqual(("MT", "T100"), B.split_system_name("MTT100"))
        with self.assertRaisesRegex(B.CatsPanelError, "not a JMRI system name"):
            B.split_system_name("Switch 107")


class Masts(unittest.TestCase):
    def test_staging_and_main_upper_masts_are_the_committed_ones(self):
        k = built()
        staging = B.mast_bindings(k["bands"][k["bi"]][2], k["F"])
        level = B.level_mast_bindings(k["bands"], k["F"], k["bi"])
        self.assertFalse(set(staging) & set(level))
        self.assertEqual(dict(staging, **level), k["committed"]["masts"])
        self.assertEqual({e["name"] for e in level.values()}, B.level_masts.visible_names(levels=(2, 3)))

    def test_intermediates_stand_on_their_own_loop_half(self):
        """The APB intermediates (rows with no switch) stand at a turnback, on an edge of their loop half's own."""
        k = built()
        rows = {r["mast"]: r for r in k["F"].level_masts if not r["switch"]
                and not B.level_masts.is_level_virtual(r["system_name"])}
        placed = {}
        for _bi, _band, opts in B.level_bands(k["bands"], k["bi"]):
            for sg in opts.get("signals") or ():
                name = opts.get("mast_prefix", "") + sg["mast"]
                if name in rows:
                    placed[name] = sg
        self.assertEqual(set(placed), set(rows))
        self.assertTrue(rows)
        for name, sg in placed.items():
            with self.subTest(mast=name):
                self.assertEqual(sg["toward"], "")
                self.assertEqual(sg["dir"], rows[name]["dir"])
                self.assertEqual(sg["heads"], len(rows[name]["heads"]))


class LoopHalvesByID(unittest.TestCase):
    """Naming-layers step 13: a balloon loop half on the desk takes its block's name by ID through the one reader
    (hartlib.drawing_keys over the master its Facts.device was read from), so an owner's name in the field file
    reaches it; a master whose keys do not read stops naming the file."""

    def test_an_owners_name_reaches_the_loop_half(self):
        import csv
        import shutil
        import tempfile
        from types import SimpleNamespace
        from hartlib import devices
        k = built()
        halves = {s["name"] for _t, band, _o in k["bands"] for s in band["strands"].values() if s.get("loop_half")}
        self.assertIn("107 Loop 1", halves)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            here = devices.Files.here()
            for src in (here.master, here.dictionary, here.field):
                shutil.copy(src, data / src.name)
            field = devices.field_path(data)
            rows = list(csv.DictReader(io.StringIO(field.read_text(encoding="utf-8"))))
            row = dict.fromkeys(rows[0], "")
            row.update(level="2", layer="block", id="block:107B-107C#1", user_name="Track Balloon East")
            field.write_text(devices.master_text(rows + [row]), encoding="utf-8")
            device = SimpleNamespace(path=devices.master_path(data))
            bands = B.name_loop_halves(B.pd.solved_sheet(B.plugin_modules(B.pd.plugin())[1]).bands, device)
            named = {s["name"] for _t, band, _o in bands for s in band["strands"].values() if s.get("loop_half")}
            self.assertIn("Balloon East", named)
            self.assertNotIn("107 Loop 1", named)
            cp = sys.modules["cats_panel"]
            self.assertEqual(cp.part_blocks(device), cp.part_blocks())
            self.assertEqual(cp.part_blocks(B.DeviceMap()), {})         # a map made in memory holds no part
            with self.assertRaisesRegex(B.CatsPanelError, "made in memory"):
                cp.drawn_keys(B.DeviceMap())
            # read once per state of the master's files: the desk build asks for every block
            from unittest import mock
            fresh = SimpleNamespace(path=devices.master_path(data))
            cp._DRAWN_KEYS.clear()
            with mock.patch.object(cp.drawing_keys, "read", wraps=cp.drawing_keys.read) as read:
                self.assertIs(cp.drawn_keys(fresh), cp.drawn_keys(fresh))
                cp.block_names(fresh)
            self.assertEqual(read.call_count, 1)
        from unittest import mock
        bad = cp.drawing_keys.DrawingKeyError("Track 107 Loop 2 (level 2, block) has no trial_name")
        with mock.patch.object(cp.drawing_keys, "read", side_effect=bad), \
                self.assertRaisesRegex(B.CatsPanelError, r"devices_generated\.csv: Track 107 Loop 2 .* has no trial_name"):
            B.name_loop_halves(k["bands"])


class TestDeskErrors(unittest.TestCase):
    """The desk modules raise CatsPanelError; only build_cats_panel.main turns it into an exit."""

    def test_main_exits_with_the_error_message(self):
        import contextlib
        import io
        from unittest import mock
        bad = B.CatsPanelError("switch 107 is drawn twice on main and upper")
        for argv in (["--check"], []):
            err = io.StringIO()
            with mock.patch.object(B.pd, "plugin", return_value=Path("plugin")), \
                    mock.patch.object(B.pd.paths, "exit_if_overridden"), \
                    mock.patch.object(B, "generate", side_effect=bad), contextlib.redirect_stderr(err):
                self.assertEqual(B.main(argv), 1, argv)
            self.assertEqual(err.getvalue(), "switch 107 is drawn twice on main and upper\n")

    def test_a_missing_plugin_stops_a_build_and_skips_a_check(self):
        import contextlib
        import io
        from unittest import mock
        gone = B.pd.PluginMissing("schematic-maps plugin not found")
        for argv, env, status in ((["--check"], {}, 0), (["--check"], {"SCHEMATIC_REQUIRED": "1"}, 1), ([], {}, 1)):
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(B.pd, "plugin", side_effect=gone), \
                    mock.patch.object(B.pd.paths, "exit_if_overridden"), \
                    mock.patch.dict(B.os.environ, env), mock.patch.object(B, "generate") as generate, \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                if "SCHEMATIC_REQUIRED" not in env:
                    B.os.environ.pop("SCHEMATIC_REQUIRED", None)
                self.assertEqual(B.main(argv), status, (argv, env))
            generate.assert_not_called()
            if argv:
                self.assertIn("SKIPPED CATS panel check: schematic-maps plugin not found", out.getvalue())
            else:
                self.assertEqual(err.getvalue(), "schematic-maps plugin not found\n")

    def test_compare_writes_only_without_check(self):
        import contextlib
        import io
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            live, fresh = Path(tmp) / "live.xml", Path(tmp) / "fresh.xml"
            live.write_text("old\n", encoding="utf-8")
            fresh.write_text("new\n", encoding="utf-8")
            with mock.patch.object(B.pd, "REPO", Path(tmp)), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(B.compare({live: fresh}, check=True), 1)
                self.assertEqual(live.read_text(encoding="utf-8"), "old\n")
                self.assertIn("live.xml is stale", out.getvalue())
                self.assertEqual(B.compare({live: fresh}, check=False), 0)
                self.assertEqual(live.read_text(encoding="utf-8"), "new\n")
                self.assertEqual(B.compare({live: fresh}, check=True), 0)
                self.assertIn("live.xml is current", out.getvalue())

    def test_the_cause_is_kept(self):
        with self.assertRaises(B.CatsPanelError) as caught:
            sys.modules["cats_panel"].turnout_routes("M2T", "1", "Switch 1", "A", "B")
        self.assertIsNone(caught.exception.__cause__)       # a check of its own, no cause to keep
        from hartlib.errors import HartlibError
        self.assertIsInstance(caught.exception, HartlibError)

    def test_a_rewritten_master_is_read_again(self):
        import tempfile
        cp = sys.modules["cats_panel"]
        with tempfile.TemporaryDirectory() as tmp:
            field = Path(tmp) / devices.FIELD_FILE
            field.write_text("a\n", encoding="utf-8")
            before = cp._master_state(field)
            self.assertEqual(before, cp._master_state(field))
            field.write_text("a,b\n", encoding="utf-8")
            self.assertNotEqual(before, cp._master_state(field))

    def test_same_size_and_time_new_content_is_read_again_and_only_the_latest_is_kept(self):
        import os
        import tempfile
        from types import SimpleNamespace
        from unittest import mock
        cp = sys.modules["cats_panel"]
        with tempfile.TemporaryDirectory() as tmp:
            field = Path(tmp) / devices.FIELD_FILE
            field.write_text("aa\n", encoding="utf-8")
            st = field.stat()
            before = cp._master_state(field)
            field.write_text("bb\n", encoding="utf-8")               # the same size
            os.utime(field, ns=(st.st_atime_ns, st.st_mtime_ns))     # and the same change time
            self.assertNotEqual(before, cp._master_state(field))
            cp._DRAWN_KEYS.clear()
            master = SimpleNamespace(path=field)
            with mock.patch.object(cp.drawing_keys, "read", side_effect=lambda *_a: object()) as read:
                first = cp.drawn_keys(master)
                self.assertIs(cp.drawn_keys(master), first)
                field.write_text("cc\n", encoding="utf-8")
                os.utime(field, ns=(st.st_atime_ns, st.st_mtime_ns))
                self.assertIsNot(cp.drawn_keys(master), first)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(list(cp._DRAWN_KEYS), [field.resolve()])   # one entry per master: the latest read


class DressBoxes(unittest.TestCase):
    """cats_panel_dress's label boxes: two labels clash when they overlap or come within LABEL_GAP_PX side to side,
    and a SECTION with no whole-number cell stops the build."""

    def test_near_counts_the_gap_side_to_side_only(self):
        import cats_panel_dress as dress
        a = dress.Box(0, 0, 10, 10)
        self.assertTrue(a.near(dress.Box(15, 0, 20, 10)))           # 5 px apart: inside the 6 px gap
        self.assertFalse(a.near(dress.Box(16, 0, 20, 10)))          # 6 px apart: clear
        self.assertFalse(a.near(dress.Box(0, 10, 10, 20)))          # touching above and below: clear
        self.assertTrue(dress.Box(15, 0, 20, 10).near(a))

    def test_a_section_without_a_cell_stops(self):
        import xml.etree.ElementTree as ET
        import cats_panel_dress as dress
        self.assertEqual(dress._cell(ET.Element("SECTION", X="3", Y="4")), (3, 4))
        with self.assertRaisesRegex(B.CatsPanelError, "X '3', Y None: not a cell"):
            dress._cell(ET.Element("SECTION", X="3"))


if __name__ == "__main__":
    unittest.main()
