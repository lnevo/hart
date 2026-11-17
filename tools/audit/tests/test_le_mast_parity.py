"""Mast parity between the hand-drawn "HART Railroad" panel, as its masts are frozen in
jmri/layouts/hart/data/schematic/staging_le/masts.csv, and the generated "Layout (generated)" panel (staging).

Signal Mast Logic discovery, the Dispatcher System and Entry/Exit never read a mast icon: they read the slot a mast
is bound in and resolve its facing block (where the train stands when it reads the mast) and protected blocks (what
it guards). Both panels sit in one tables file and JMRI looks a mast up on whichever panel it finds first, so every
staging mast must resolve to the same blocks, from the same kind of slot, on both panels.

The rule, as JMRI 5.16 applies it (LayoutBlockManager.getFacingBlockByBeanByPanel and
getProtectingBlocksByBeanByPanel, LayoutEditorTools.isAtWestEndOfAnchor, LayoutTurnout.getProtectedBlocks; the
jmri-sml-nx skill's "Anchors: which slot", "End bumpers: which slot" and "Turnouts and crossings"), is implemented
once in the schematic-maps plugin's slots.py and read here from the XML of each panel:
- anchor or end bumper: JMRI compares the far ends of the point's two tracks (a bumper: the far end and the bumper);
  a gap more than twice as wide as tall is horizontal (west is left), more than twice as tall as wide is vertical
  (west is up), otherwise horizontal. An east bound mast faces the west track and protects the east track; a west
  bound mast the reverse. A bumper mast protects nothing.
- turnout leg X: faces the block of the track on X and protects the turnout's (leg) block, or, when that track is
  in the turnout's own block, the blocks beyond (crossovers pair A with C and B with D by type).

These checks read the all-levels trial and the three-level cut-over candidate (--as-live, owner 2026-11-16). The
staging-only candidate (--levels staging --as-live) ends both helix tracks at end bumpers as live, so there every
mast matches exactly, with no exception (test_le_cutover.py).

With B.JOIN_HELIX off (owner, 2026-11-16, after the Phase 4 rehearsal) the three-level panels draw the helix tracks
unjoined, so every staging mast matches the live panel exactly there too, Masts 38RA and 40RA on their bumpers.
With it on, and only then, HELIX_ENTRANCE lists the exceptions (owner's choice, 2026-11-15, option 1): on the live
panel McKees Rocks and McKeesport end at buffer stops, so their bumper masts protect nothing; the joined panel runs
both tracks on through the helix, so each mast stands on the anchor at the helix entrance, facing the same block
as live and protecting the helix run, an anchor slot, not a bumper.
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_build_layout_le as T  # noqa: E402  the trial is built once for both modules

B = T.B
tables, paths = T.tables, T.paths


# mast: why its protected block and slot kind differ from the live panel's
HELIX_ENTRANCE = {
    "Mast 38RA": "live buffer stop of McKeesport; generated: anchor at the helix entrance, protecting the helix run",
    "Mast 40RA": "live buffer stop of McKees Rocks; generated: anchor at the helix entrance, protecting the helix run",
} if B.JOIN_HELIX else {}


def masts_by_name(ix) -> dict:
    out = {}
    for m in ix.masts():
        if m["mast"] in out:
            raise AssertionError(f"mast {m['mast']} bound in two slots")
        out[m["mast"]] = m
    return out


class MastParity(unittest.TestCase):
    PANEL = B.PANEL_NAME

    @classmethod
    def built(cls):
        return T.built()

    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.P, _names, _bands = cls.built()
        cls.slots = B.slots_module()
        cls.root = tables.loads(cls.data).root
        cls.gen_le = tables.layout_editor(cls.root, cls.PANEL)
        cls.frozen = {m["mast"]: m for m in B.le_inputs.load_masts()}
        cls.live = {n: dict(mast=n, kind=m["kind"], ident=m["ident"], slot=m["slot"], facing=m["facing"],
                            protects=m["protects"], **({"turnout": m["turnout"]} if m["kind"] == "turnout" else {}))
                    for n, m in cls.frozen.items()}
        cls.gen_ix = cls.slots.Index(cls.gen_le)
        cls.gen = masts_by_name(cls.gen_ix)
        cls.hidden = {s.get("ident"): s.get("blockname") for s in cls.gen_le.findall("tracksegment")
                      if s.get("hidden") == "yes"}

    def test_live_panel_has_its_masts(self) -> None:
        self.assertEqual(len(self.live), 49)                # wiki/DISPATCHER_LAYOUT_HOOPS.md: 49 masts
        self.assertTrue(all(m["facing"] for m in self.live.values()))

    def test_every_live_mast_resolves_the_same_on_the_generated_panel(self) -> None:
        for name, live in sorted(self.live.items()):
            if name in HELIX_ENTRANCE:
                continue
            with self.subTest(mast=name):
                gen = self.gen.get(name)
                self.assertIsNotNone(gen, f"{name} is not on the generated panel")
                self.assertEqual((gen["kind"], gen["facing"], gen["protects"]),
                                 (live["kind"], live["facing"], live["protects"]),
                                 f"{name}: live {live['kind']} {live['ident']} {live['slot']}, generated "
                                 f"{gen['kind']} {gen['ident']} {gen['slot']}")
                if live["kind"] == "turnout":            # the same switch, not only the same blocks
                    self.assertEqual(gen["turnout"], live["turnout"], name)

    def test_every_mast_is_placed_once(self) -> None:
        # staging's live masts and the main and upper control-point masts (main_upper_masts.csv)
        level = {r["mast"] for r in B.read_level_masts()}
        self.assertEqual(set(self.gen), set(self.live) | level)
        self.assertFalse(set(self.live) & level)
        self.assertEqual(self.P.unplaced, [])

    def test_helix_entrance_exceptions(self) -> None:
        self.assertEqual({m for _t, m, _w in self.P.moved}, set(HELIX_ENTRANCE))
        for name in HELIX_ENTRANCE:
            with self.subTest(mast=name):
                live, gen = self.live[name], self.gen[name]
                self.assertEqual((live["kind"], live["protects"]), ("end bumper", []))      # a buffer stop live
                self.assertEqual(gen["facing"], live["facing"])                              # the same track
                self.assertEqual(gen["kind"], "anchor")
                p = self.gen_ix.points[gen["ident"]]
                conns = [p.get("connect1name"), p.get("connect2name")]
                helix = [c for c in conns if c in self.hidden]
                self.assertEqual(len(helix), 1, "the anchor at the helix entrance, where the hidden run starts")
                self.assertEqual(gen["protects"], [self.hidden[helix[0]]])                   # the helix run
                self.assertNotEqual(gen["protects"], [live["facing"]])

    def test_icons_beside_the_track_on_the_right_of_the_train(self) -> None:
        icons = {}
        for icon in self.gen_le.findall("signalmasticon"):
            self.assertNotIn(icon.get("signalmast"), icons, "two icons for one mast")
            icons[icon.get("signalmast")] = icon
        self.assertEqual(set(icons), set(self.gen))
        # hidden only when every icon of the mast on the hand-drawn panel was (le_inputs.live_icons_hidden)
        live_hidden = {n: "yes" if m["hidden"] else "no" for n, m in self.frozen.items()}
        size = {m["mast"]: m["box"][2:] for m in self.P.masts}
        for name, m in sorted(self.gen.items()):
            with self.subTest(mast=name):
                icon = icons[name]
                self.assertEqual(icon.get("hidden"), live_hidden.get(name, "no"))
                p, d = self.gen_ix.travel(m["kind"], m["ident"], m["slot"])
                bw, bh = size[name]
                c = (float(icon.get("x")) + bw / 2, float(icon.get("y")) + bh / 2)
                v = (c[0] - p[0], c[1] - p[1])
                right = (-d[1], d[0])                   # the train's right hand, y growing down
                across = v[0] * right[0] + v[1] * right[1]
                along = v[0] * d[0] + v[1] * d[1]
                self.assertGreater(across, 4, "on the right-hand side of the train")
                self.assertLessEqual(across, 20, "close to the rail")
                self.assertLess(along, 0, "before the boundary, where the train reads it")
                deg = math.degrees(math.atan2(d[0], -d[1])) % 360
                gap = abs((float(icon.get("degrees")) - deg + 180) % 360 - 180)
                self.assertLessEqual(gap, 3.5, "turned to the direction of travel")


class CandidateMastParity(MastParity):
    """The same checks on the three-level cut-over candidate, whose panel is "HART Railroad"."""
    PANEL = "HART Railroad"

    @classmethod
    def built(cls):
        import test_le_cutover
        return test_le_cutover.three_levels()


if __name__ == "__main__":
    unittest.main()
