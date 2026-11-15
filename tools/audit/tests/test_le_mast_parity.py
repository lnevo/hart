"""Mast parity between the live "HART Railroad" panel and the generated "Layout (generated)" panel (staging).

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

Exceptions (owner's choice, 2026-11-15), and only these, in HELIX_ENTRANCE: on the live panel McKees Rocks and
McKeesport end at buffer stops, so their bumper masts protect nothing. The generated panel runs both tracks on
through the helix to the next level, so there is no bumper: each mast stands on the anchor at the helix entrance
(the hidden helix run carries the next level's block, so the anchor is a block boundary), facing the same block as
live. Its protected block is necessarily the helix run, where live has none, and its slot is an anchor, not a bumper.
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
}


def masts_by_name(ix) -> dict:
    out = {}
    for m in ix.masts():
        if m["mast"] in out:
            raise AssertionError(f"mast {m['mast']} bound in two slots")
        out[m["mast"]] = m
    return out


class MastParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.P, _names, _bands = T.built()
        cls.slots = B.slots_module()
        cls.root = tables.loads(cls.data).root
        cls.gen_le = tables.layout_editor(cls.root, B.PANEL_NAME)
        cls.live_le = tables.layout_editor(tables.read(paths.TABLES_XML), B.TEMPLATE_PANEL)
        cls.live = masts_by_name(cls.slots.Index(cls.live_le))
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
        self.assertEqual(set(self.gen), set(self.live))
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
        live_hidden = {}           # hidden only when every live icon of the mast is (build_layout_le's rule)
        for i in self.live_le.findall("signalmasticon"):
            was = live_hidden.get(i.get("signalmast"), "yes")
            live_hidden[i.get("signalmast")] = "yes" if was == "yes" and i.get("hidden") == "yes" else "no"
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


if __name__ == "__main__":
    unittest.main()
