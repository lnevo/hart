"""The CATS desk bindings each level's builder gives, on the committed railroad (the sheet, tables.xml, devices.csv,
switches.csv, switch_legs.csv, main_upper_masts.csv), held to cats/panels/HART_CTC.bindings.json part by part: the
staging switches, OS blocks, destinations, half labels, blocks and masts, and the main and upper switches, blocks,
helix blocks and masts. These pin the builders' behaviour so they can be merged into one without a desk changing.
They go through build_cats_panel (the names it exports), so they hold for any module layout behind it.

Skipped when the schematic plugin is not checked out at its pinned commit (as the other desk tests are).
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_cats_panel as B  # noqa: E402

BUILT = {}


def built():
    """The committed railroad's bands, facts and bindings, built once for every test here, as generate() builds them."""
    if BUILT:
        return BUILT
    try:
        cats, sheet = B.plugin_modules(B.pd.plugin())
    except SystemExit as e:
        raise unittest.SkipTest(f"no plugin: {e.code}") from None
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

    def test_the_counts(self):
        c = built()["committed"]
        self.assertEqual((len(c["switches"]), len(c["blocks"]), len(c["masts"])), (74, 163, 69))
        self.assertEqual(sum(staging_turnout(e) for e in c["switches"].values()), 23)


class StagingSwitches(unittest.TestCase):
    def setUp(self):
        k = built()
        self.F, self.band, self.opts = k["F"], k["bands"][k["bi"]][1], k["bands"][k["bi"]][2]
        self.committed = k["committed"]
        self.os_of = B.os_blocks(self.band, self.F)

    def test_os_blocks_one_per_switch_node(self):
        nodes = {n for n, d in self.band["nodes"].items() if d["kind"] == "switch"}
        self.assertEqual(set(self.os_of), nodes)
        self.assertEqual(len(nodes), 23)
        self.assertEqual(len(set(self.os_of.values())), 23)          # never two nodes on one OS block
        legs = {leg.os_block for sw in self.F.switches.values() for leg in sw.legs}
        self.assertLessEqual(set(self.os_of.values()), legs)

    def test_switch_bindings_are_the_committed_staging_ones(self):
        got = B.switch_bindings(self.band, self.F, self.os_of)
        want = {k: e for k, e in self.committed["switches"].items() if staging_turnout(e)}
        self.assertEqual(got, want)

    def test_half_labels(self):
        got = B.switch_bindings(self.band, self.F, self.os_of)
        self.assertEqual({k: e["label"] for k, e in got.items() if "label" in e},
                         {"7/T139": "7A", "7/T33": "7B", "23/T57": "23A", "23/T126": "23B",
                          "35/T95": "35A", "35/T54": "35B"})
        for k, e in got.items():
            if "label" in e:
                sw = self.F.switches[int(k.split("/")[0])]
                leg = next(l for l in sw.legs if l.os_block == e["block"])
                self.assertEqual(B.half_label(sw, leg), e["label"])

    def test_destinations_are_the_closed_and_thrown_legs(self):
        """Each staging switch's legs B and C lead to its switch_legs.csv closed and thrown blocks, the closed one
        on the leg its binding closes the turnout for."""
        got = B.switch_bindings(self.band, self.F, self.os_of)
        by_block = {e["block"]: (k, e) for k, e in got.items()}
        dests = set()
        for n, os_name in sorted(self.os_of.items()):
            d = self.band["nodes"][n]
            sw = self.F.switches[int(d["label"])]
            leg = next(l for l in sw.legs if l.os_block == os_name)
            to = {p: B.dest(self.band, self.os_of, n, p, self.F.helix) for p in "BC"}
            with self.subTest(os=os_name):
                self.assertEqual(sorted(to.values()), sorted((leg.closed, leg.thrown)))
                _key, e = by_block[os_name]
                closed = next(p for p, r in e["routes"].items() if r["ROUTECOMMAND"]["command"] == "close")
                self.assertEqual(to[closed], leg.closed)
            dests |= set(to.values())
        # the helix tracks lead up the helix as one block each (owner, 2026-11-20)
        self.assertLessEqual({"Track Helix Outer", "Track Helix Inner"}, dests)
        self.assertFalse({"Track McKees Rocks", "Track McKeesport"} & dests)


class Helix(unittest.TestCase):
    def test_the_helix_blocks(self):
        k = built()
        self.assertEqual(k["F"].helix, {"McKees Rocks": "Track Helix Outer", "McKeesport": "Track Helix Inner"})
        self.assertEqual(B.track_block("McKeesport", k["F"].helix), "Track Helix Inner")
        self.assertEqual(B.track_block("K-2", k["F"].helix), "Track K-2")
        band = k["bands"][k["bi"]][1]
        helix = B.bdm.mast_rule.read_helix_tracks()          # helix_tracks.csv rows, as dark_bindings reads them
        found = {}
        for sid, s in band["strands"].items():
            got = B.helix_block(band, ("track", f"b{k['bi']}:{sid}"), helix)
            if got:
                found.setdefault(got, set()).add(s["name"])
        self.assertEqual(found, {"Track Helix Outer": {"McKees Rocks"}, "Track Helix Inner": {"McKeesport"}})

    def test_each_helix_block_is_bound_once_from_the_device_map(self):
        blocks = built()["committed"]["blocks"]
        for name in ("Track Helix Outer", "Track Helix Inner"):
            with self.subTest(block=name):
                bound = [e for key, e in blocks.items() if e.get("name", key) == name]
                self.assertEqual(len(bound), 1)
                self.assertEqual(bound[0]["discipline"], B.MAIN_UPPER_DISCIPLINE)
                self.assertEqual(bound[0]["occupied"]["JMRIPREFIX"], "IS")


class Blocks(unittest.TestCase):
    def setUp(self):
        k = built()
        self.k = k
        out_sw = B.switch_bindings(k["bands"][k["bi"]][1], k["F"], B.os_blocks(k["bands"][k["bi"]][1], k["F"]))
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
        dark, log, missing, joined = B.dark_bindings(k["bands"], k["cats"], self.P, k["F"], k["bi"])
        names = {key: v for key, v in self.P.names.items() if key[1].startswith(f"b{k['bi']}:") and key not in joined}
        staging = B.block_bindings(k["bands"][k["bi"]][1], k["F"], names)
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
        self.assertEqual({e["routes"]["B"]["ROUTECOMMAND"]["JMRIPREFIX"] for e in want.values()},
                         {B.LEVEL_TURNOUT_PREFIX})


class Masts(unittest.TestCase):
    def test_staging_and_main_upper_masts_are_the_committed_ones(self):
        k = built()
        staging = B.mast_bindings(k["bands"][k["bi"]][2], k["F"])
        level = B.level_mast_bindings(k["bands"], k["F"], k["bi"])
        self.assertFalse(set(staging) & set(level))
        self.assertEqual(dict(staging, **level), k["committed"]["masts"])
        self.assertEqual(len(level), 44)                          # main_upper_masts.csv's visible masts
        self.assertEqual({e["name"] for e in level.values()}, B.level_masts.visible_names())

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


if __name__ == "__main__":
    unittest.main()
