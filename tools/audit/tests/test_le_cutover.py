"""build_layout_le.py --levels staging --as-live: the cut-over candidate, the "HART Railroad" panel replaced by the
generated staging panel (Phases 1 and 2, owner approved 2026-11-15), built from the frozen inputs (Phase 3b).

The candidate must be a drop-in: the same tables but the one panel, the same idents, leg letters and slots, every
mast and Entry/Exit sensor resolving as frozen from the hand-drawn panel, every frozen icon and caption carried once
and clear of the generated switch numbers, track names, station captions and block contents icons (which win over
the hand-drawn ones, owner 2026-11-15), the audits passing on it. The comparisons read the frozen files
(jmri/layouts/hart/data/schematic/staging_le/), not the panel in tables.xml, so they hold after the cut-over too,
when that panel is the generated one; and the candidate is the same whether the tables hold the hand-drawn panel,
a generated one or none.
"""
from __future__ import annotations

import contextlib
import copy
import functools
import io
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_build_layout_le as T  # noqa: E402  loads the builder and the audit once

B, AUDIT = T.B, T.AUDIT


def page_prefs() -> dict:
    """The page's preferences (main_upper.preferences.json, the last input's), as the build reads them."""
    return B.schematic()[1]


def stretch() -> tuple:
    """(factor, tolerance) of the page's le_stretch, read by the plugin."""
    return B.plugin()[1].le_prefs.stretch(page_prefs())
tables, paths = T.tables, T.paths
LIVE = "HART Railroad"
SIZE_ATTRS = {"panelwidth", "panelheight", "windowwidth", "windowheight", "x", "y"}
STATUS = {"sensoricon": {"Bridge HBLOOP", "SML Mode", "Track Power"}, "signalheadicon": {"IH9990"}}


@functools.lru_cache(maxsize=None)
def cutover():
    """(candidate bytes, Panel, names, bands), built once for every test that needs it."""
    with contextlib.redirect_stdout(io.StringIO()):
        return B.build(T.hand(), levels="staging", as_live=True, approved=None)     # the fingerprint: its own test


def without_panel(root: ET.Element) -> bytes:
    root = copy.deepcopy(root)
    le = tables.layout_editor(root, LIVE)
    idx = list(root).index(le)
    if idx:
        root[idx - 1].tail = le.tail
    root.remove(le)
    return ET.tostring(root)


I = B.le_inputs


def sensor_slots(le) -> dict:
    return I.live_sensor_slots(le)


def frozen_items():
    """The frozen overlay items' elements, in order."""
    return [ET.fromstring(it["xml"]) for it in I.load().overlay["items"]]


def frozen_blocks(inputs) -> set:
    out = {b for c in inputs.chains for b in c["blocks"]}
    for t in inputs.turnouts:
        out |= {t[a] for a in ("blockname", "blockbname", "blockcname", "blockdname") if t.get(a)}
    return out


def without_live_panel(data: bytes) -> bytes:
    doc = tables.loads(data)
    le = tables.layout_editor(doc.root, LIVE)
    idx = list(doc.root).index(le)
    doc.root[idx - 1].tail = le.tail
    doc.root.remove(le)
    return doc.tobytes()


class Cutover(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.P, cls.names, cls.bands = cutover()
        cls.root = tables.loads(cls.data).root
        cls.live = tables.read(T.hand())
        cls.le = tables.layout_editor(cls.root, LIVE)
        cls.inputs = I.load()
        cls.slots = B.slots_module()

    # ---- Phase 1: the same tables but the panel
    def test_only_the_panel_changes(self) -> None:
        self.assertEqual(without_panel(self.root), without_panel(self.live))
        self.assertEqual([le.get("name") for le in tables.layout_editors(self.root)],
                         [le.get("name") for le in tables.layout_editors(self.live)])
        self.assertEqual(list(self.root).index(self.le), list(self.live).index(tables.layout_editor(self.live, LIVE)))

    def test_live_panel_attributes_fit_sizing(self) -> None:
        got = {k: v for k, v in self.le.attrib.items() if k not in SIZE_ATTRS | {"scrollable"}}
        want = {k: v for k, v in self.inputs.attrs.items() if k not in SIZE_ATTRS | {"scrollable"}}
        self.assertEqual(got, want)
        # larger than its window, so it scrolls both ways (the frozen attribute, for a panel that fits, is "none")
        self.assertEqual((self.le.get("editable"), self.le.get("scrollable")), ("no", "both"))
        self.assertEqual(self.inputs.attrs["scrollable"], "none")
        w, h = int(self.le.get("panelwidth")), int(self.le.get("panelheight"))
        # the window is the panel and its frame, at most FIT; the stretched panel (le_stretch) is wider than it
        self.assertEqual((int(self.le.get("windowwidth")), int(self.le.get("windowheight"))),
                         (min(w + 18, B.FIT[0]), min(h + 60, B.FIT[1])))
        self.assertEqual(self.P.scale, (self.P.staging_fit[0] * stretch()[0], self.P.staging_fit[1]))
        self.assertTrue(0.7 < self.P.staging_fit[0] < 0.9, self.P.staging_fit)     # staging's own fit to FIT

    def test_no_placeholders_in_staging_mode(self) -> None:
        self.assertFalse([t for t in tables.turnouts(self.root) if tables.system_name(t).startswith(B.TURNOUT_SYS)])
        self.assertFalse([b for b in tables.blocks(self.root) if tables.system_name(b).startswith(B.BLOCK_SYS)])
        live_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live)}
        self.assertLessEqual(T.used_blocks(self.le), live_lb)
        self.assertEqual(T.used_blocks(self.le), frozen_blocks(self.inputs))
        self.assertEqual({s.get("hidden") for s in self.le.findall("tracksegment")}, {"no"})     # no helix joins

    def test_levels_are_checked(self) -> None:
        with self.assertRaisesRegex(B.BuildError, "levels must be"):
            B.build(levels="main")
        with self.assertRaisesRegex(B.BuildError, "frozen from the staging cut-over build"):
            B.build(levels="all", as_live=True, freeze_from=self.le)

    # ---- Phase 1: idents, leg letters, masts, sensors
    def test_live_idents_and_leg_letters_are_kept(self) -> None:
        gen_t = {t.get("ident"): t for t in self.le.findall("layoutturnout")}
        for t in self.inputs.turnouts:
            with self.subTest(turnout=t["ident"]):
                g = gen_t[t["ident"]]
                if t["ident"] in B.swapped_idents():        # Switch 13: Barn on leg C (owner, 2026-11-16)
                    self.assertEqual(B.turnout_facts(self.le)[t["ident"]],
                                     B.swap_legs(self.inputs.turnout_facts()[t["ident"]]))
                    continue
                for a in ("turnoutname", "type", "blockname", "blockbname", "blockcname", "blockdname"):
                    self.assertEqual(g.get(a), t.get(a), a)
                if "XOVER" not in t["type"]:
                    self.assertEqual(g.get("continuing"), t.get("continuing"))
        self.assertEqual(len(self.inputs.turnouts), 20)
        live = {i: B.swap_legs(f) if i in B.swapped_idents() else f for i, f in self.inputs.turnout_facts().items()}
        self.assertEqual(B.turnout_facts(self.le), {**B.turnout_facts(self.le), **live})
        self.assertEqual(B.swapped_idents(), {"TO1"})
        gen_s = {s.get("ident"): s.get("blockname") for s in self.le.findall("tracksegment")}
        gen_p = {p.get("ident"): p for p in self.le.findall("positionablepoint")}
        want = [(b["ident"], "ANCHOR", b["blocks"]) for b in self.inputs.boundaries] + \
            [(i, "END_BUMPER", [b]) for b, i in self.inputs.ends.items()]
        for ident, typ, blocks in want:          # boundaries and bumpers keep theirs
            with self.subTest(point=ident):
                g = gen_p[ident]
                self.assertEqual(g.get("type"), typ)
                self.assertEqual(sorted(gen_s[c] for c in (g.get("connect1name"), g.get("connect2name")) if c),
                                 blocks)
        self.assertEqual(len(want), 17 + 7)                 # 17 boundary anchors, 7 end bumpers
        frozen_segs = set(self.inputs.segments.values())
        reused = [i for i in self.P.idents_given.values() if i in frozen_segs]
        self.assertGreater(len(reused), 0)                   # one-segment blocks keep their segment ident
        _sheet, le_mod, _core = B.plugin()
        unfindable = {i for i in frozen_segs if le_mod.jmri_kind(i) != "segment"}       # F46-W-0
        self.assertTrue(unfindable)
        self.assertFalse(unfindable & set(gen_s))            # JMRI cannot find it by name: not carried over
        self.assertTrue(any(line.startswith("live segment idents JMRI does not find as segments, so not reused: ")
                            for line in self.P.log))
        self.assertEqual(len(self.P.idents_given), 20 + 17 + 7 + len(reused))

    def test_every_mast_resolves_exactly_as_live(self) -> None:
        live = {}
        for m in self.inputs.masts:
            slot = m["slot"]
            if m["kind"] == "turnout" and m["ident"] in B.swapped_idents() and slot in "BC":
                slot = "BC".replace(slot, "")              # moves with its leg (Mast 14R to Switch 13's leg C)
            live[m["mast"]] = dict(mast=m["mast"], kind=m["kind"], ident=m["ident"], slot=slot,
                                   facing=m["facing"], protects=m["protects"],
                                   **({"turnout": m["turnout"]} if m["kind"] == "turnout" else {}))
        gen = {m["mast"]: m for m in self.slots.Index(self.le).masts()}
        self.assertEqual(len(live), 49)
        self.assertEqual(set(gen), set(live))
        self.assertEqual(self.P.moved, [])                  # no helix-entrance exception in staging mode
        self.assertEqual(self.P.unplaced, [])
        for name, m in sorted(live.items()):
            with self.subTest(mast=name):
                self.assertEqual(gen[name], m)              # kind, ident, slot, blocks, turnout

    def test_entry_exit_sensors_and_pairs(self) -> None:
        live_slots = {(r["ident"], r["slot"]): r["sensor"] for r in self.inputs.sensors}
        gen_slots = sensor_slots(self.le)
        self.assertEqual(gen_slots, live_slots)                             # same ident and slot each
        self.assertEqual(self.P.sensors_bound, len(live_slots))
        gen_ix = self.slots.Index(self.le)
        for r in self.inputs.sensors:
            self.assertEqual(gen_ix.blocks(r["kind"], r["ident"], r["slot"]), (r["facing"], r["protects"]),
                             r["sensor"])
        # the NX sensor beans: the frozen set, each bound once; no NX sensor icon and no yard ladder button on the
        # panel (owner, 2026-11-16): the pairs resolve from the bound sensors alone
        nx_beans = {tables.user_name(s) for s in self.root.iter("sensor")
                    if tables.user_name(s).startswith("NX Mast ")}
        self.assertEqual(set(live_slots.values()), nx_beans)
        self.assertFalse([i for i in self.le.iter("sensoricon") if (i.get("sensor") or "").startswith("NX ")])
        self.assertFalse([i for i in self.le.iter("turnouticon") if (i.get("turnout") or "").startswith("IT:HART:YL:")])
        self.assertFalse([el for el in frozen_items() if B.overlay_mod().left_out(el)])
        dropped = self.inputs.overlay["dropped"]
        self.assertEqual(set(dropped["nx_icons"]), nx_beans)                 # recorded as dropped, as every drop
        self.assertEqual(len(dropped["ladder_buttons"]), 10)
        self.assertEqual(self.P.overlay["dropped"]["nx_icons"], 23)
        # every Entry/Exit pair's source and destination is bound on the candidate's panel
        bound = set(gen_slots.values())
        masts = {m["mast"] for m in gen_ix.masts()}
        pairs = 0
        for lp in self.root.find("entryexitpairs").findall("layoutPanel"):
            self.assertEqual(lp.get("name"), LIVE)
            for src in lp.findall("source"):
                for el in [src, *src.findall("destination")]:
                    pairs += el is not src
                    with self.subTest(item=el.get("item")):
                        self.assertIn(el.get("type"), ("sensor", "signalMast"))
                        self.assertIn(el.get("item"), bound if el.get("type") == "sensor" else masts)
        self.assertEqual(pairs, AUDIT.EXPECTED_NX_PAIRS)

    def test_audit_passes_strict_on_the_candidate(self) -> None:
        boundaries = AUDIT.load_boundaries(AUDIT.BOUNDARIES)        # the live contract, unchanged
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables_cutover.xml"
            path.write_bytes(self.data)
            audit = AUDIT.audit_source("deployment", path, boundaries, {b.mast for b in boundaries},
                                       generated=True)
            drift = AUDIT.report_drift([audit])
            with contextlib.redirect_stdout(io.StringIO()):
                cli = AUDIT.main(["--strict", "--tables", str(path), "--generated"])
        self.assertEqual(audit.errors, [])
        # Before its Stage 1 the candidate still carries the hand-drawn panel's SML and Dispatcher graph: the audit
        # warns about exactly those two, so --strict refuses it until Stage 1 has run (Phase 5 runs it first).
        self.assertEqual(len(audit.warnings), 2, audit.warnings)
        self.assertTrue(all("run Stage 1" in w for w in audit.warnings), audit.warnings)
        self.assertEqual(drift, [])
        self.assertEqual(audit.facts["panel"], LIVE)
        self.assertEqual(cli, 1)

    # ---- Phase 3: the scripts that run on tables.xml
    def test_the_candidate_carries_one_generated_panel_marker(self) -> None:
        self.assertTrue(tables.generated_panel(self.le))
        self.assertFalse([el for el in frozen_items() if el.get("text") == tables.GENERATED_PANEL_MARKER])
        self.assertEqual(1, sum(lb.get("text") == tables.GENERATED_PANEL_MARKER
                                for lb in self.root.iter("positionablelabel")))

    def test_polish_reconcile_and_audit_leave_the_candidate_as_built(self) -> None:
        polish = T._load("polish_hart_layout_editor", paths.LAYOUT_SCRIPTS / "polish_hart_layout_editor.py")
        stations = T._load("reconcile_dispatcher_stations", paths.LAYOUT_SCRIPTS / "reconcile_dispatcher_stations.py")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(self.data)
            with contextlib.redirect_stdout(io.StringIO()):
                for fn in (polish.apply_visual_standard, polish.apply_overlap_cleanup,
                           polish.apply_block_labels_only):
                    self.assertEqual(fn(path, check=True)[1], [], fn.__name__)
                    fn(path, check=False, reference=path)
                self.assertEqual(stations.main(["--panel", str(path), "--check", "--no-sync"]), 0)
                self.assertEqual(AUDIT.main(["--tables", str(path)]), 0)   # found by its marker; --strict waits for Stage 1
            self.assertEqual(path.read_bytes(), self.data)

    def test_layout_facts_pass_on_the_candidate(self) -> None:
        facts = T._load("check_layout_facts", T.ROOT / "tools/audit/check_layout_facts.py")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables_cutover.xml"
            path.write_bytes(self.data)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(facts.main(["--tables", str(path)]), 0, err.getvalue())

    # ---- Phase 2: the overlay
    def test_every_live_overlay_item_once_and_clear(self) -> None:
        ov = T._load("le_overlay", T.ROOT / "tools/schematic/le_overlay.py")
        _sheet, le_mod, _core = B.plugin()
        system = tables.mast_system_names(self.root)
        size = {m: tables.mast_icon_size(s)[0] for m, s in system.items()}
        widths = {b["block"]: float(b["box"][2]) for b in self.P.bcis}     # as the plugin placed them
        self.assertEqual(ov.check(self.le, self.inputs.overlay, le_mod, self.slots, size,
                                  B.LE_LABELS["switch_prefix"], widths, self.P.overlay["added"]), [])
        live_items = frozen_items()
        self.assertEqual(Counter(el.tag for el in live_items), Counter(
            sensoricon=80, positionablelabel=10, signalheadicon=1))
        # the two crossover halves the hand-drawn panel drew no lamp for get one (le_overlay.half_lamps)
        self.assertEqual(sorted(it.el.get("sensor") for it in self.P.overlay["added"]),
                         ["BS Switch 23b", "BS Switch 7b"])
        self.assertEqual(len(self.P.overlay["records"]), len(live_items) + 2)
        self.assertTrue(ov.check(self.le, self.inputs.overlay, le_mod, self.slots, size,
                                 B.LE_LABELS["switch_prefix"], widths))       # not without them
        strip = Counter(ov.strip(el) for el in live_items)
        got = Counter(ov.strip(el) for el in self.le if el.tag in ov.OVERLAY_TAGS)
        self.assertEqual(strip - got, Counter())             # each live item there, attributes as live

    def test_what_panel_status_and_signal_coordinator_look_up(self) -> None:
        for tag, names in STATUS.items():
            attr = "sensor" if tag == "sensoricon" else "signalhead"
            got = Counter(i.get(attr) for i in self.le.findall(tag) if i.get(attr) in names)
            self.assertEqual(set(got), names)
            self.assertEqual(set(got.values()), {1})
        texts = {lb.get("text") for lb in self.le.findall("positionablelabel")}
        self.assertLessEqual({"LCOS", "Turnouts", "Signals", "Track Power", "HART RAILROAD"}, texts)
        self.assertNotIn("Neville Island", texts)              # the title, renamed (le_overlay.CAPTIONS)
        dropped = self.inputs.overlay["dropped"]["block_contents"]
        self.assertEqual(len(dropped), 55)
        bcis = Counter(i.get("blockcontents") for i in self.le.findall("BlockContentsIcon"))
        self.assertEqual({b: bcis[b] for b in dropped}, {b: 1 for b in dropped},
                         "one generated block contents icon for each block the hand-drawn panel showed")
        status = [r for r in self.P.overlay["records"] if r["anchor"] == "group status"]
        self.assertEqual(len(status), 8)
        moves = {(r["new"][0] - r["live"][0], r["new"][1] - r["live"][1]) for r in status}
        self.assertEqual(len(moves), 1, "the status cluster moves as one block")

    def test_generated_labels_win(self) -> None:
        texts = Counter(lb.get("text") for lb in self.le.findall("positionablelabel"))
        prefix = B.LE_LABELS["switch_prefix"]
        for n in self.inputs.overlay["dropped"]["switch_numbers"]:
            self.assertEqual(texts[prefix + n], 1, f"switch {n}: the generated number only")
        self.assertIn("S-R", texts)
        self.assertNotIn("Track S-R", texts)
        lower = Counter(t.lower() for t in texts if t)
        for caption in ("Brick", "South Yard", "Princess"):
            with self.subTest(caption=caption):
                self.assertIn(caption, self.inputs.overlay["dropped"]["captions"])
                self.assertGreaterEqual(lower[caption.lower()], 1)         # the generated one
                self.assertNotIn(caption, texts)                           # not the hand-drawn one

    def test_overlay_report_is_printed(self) -> None:
        lines = B.overlay_lines(self.P.overlay)
        self.assertTrue(lines[0].startswith(f"{len(self.P.overlay['records'])} live items carried"))
        self.assertIn("left to the generator: 55 block contents, 20 switch numbers", lines[1])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                B, "build", return_value=(self.data, self.P, self.names, self.bands)):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                B.main(["--levels", "staging", "--as-live", "--out", str(Path(tmp) / "c.xml")])
        self.assertIn("  overlay: placed around the generated", out.getvalue())
        self.assertIn("panel 'HART Railroad'", out.getvalue())

    def test_each_option_set_has_its_own_trial_file(self) -> None:
        self.assertEqual(B.default_out("all", False), B.TRIAL)
        self.assertEqual(B.default_out("staging", False), B.TRIAL_STAGING)
        self.assertEqual(B.default_out("staging", True), B.CUTOVER_STAGING)
        self.assertEqual(B.default_out("all", True), B.CUTOVER)
        self.assertEqual(len({B.TRIAL, B.TRIAL_STAGING, B.CUTOVER, B.CUTOVER_STAGING}), 4)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(B, "TRIAL_STAGING", Path(tmp) / "s.xml"), \
                mock.patch.object(B, "TRIAL", Path(tmp) / "a.xml"), \
                mock.patch.object(B, "build", return_value=(self.data, self.P, self.names, self.bands)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["--levels", "staging"]), 0)
                self.assertEqual(B.main(["--levels", "staging", "--check"]), 0)
                self.assertEqual(B.main(["--check"]), 1)          # the all-levels trial is another file
            self.assertTrue((Path(tmp) / "s.xml").exists())
            self.assertFalse((Path(tmp) / "a.xml").exists())

    def test_approve_staging_options_and_the_staging_file_beside_the_candidate(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            for argv in (["--approve-staging", "--levels", "staging"], ["--approve-staging", "--as-live"],
                         ["--approve-staging", "--check"]):
                self.assertEqual(B.main(argv), 1, argv)
        P = mock.Mock(staging_data=b"staging", log=[], mast_notes=[], moved=[], overlay=None, staging_same=["x"],
                      gaps=[10, 20], scale=(1.0, 1.0))
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(B, "build", return_value=(self.data, P, {}, [])), \
                mock.patch.object(B.tables, "loads") as loads, mock.patch.object(B, "plugin") as plug:
            le_mod = mock.Mock()
            le_mod.summary.return_value = "s"
            plug.return_value = (None, le_mod, None)
            out = Path(tmp) / "c.xml"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["--as-live", "--out", str(out)]), 0)
            self.assertEqual([c.kwargs.get("path") for c in loads.call_args_list], [out, Path(tmp) / "c_staging.xml"])
            self.assertEqual(loads.call_args_list[1].args[0], b"staging")

    def test_check_mode_and_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                B, "build", return_value=(self.data, self.P, self.names, self.bands)) as built:
            out = Path(tmp) / "c.xml"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["--levels", "staging", "--as-live", "--out", str(out)]), 0)
                self.assertEqual(B.main(["--levels", "staging", "--as-live", "--check", "--out", str(out)]), 0)
            # on the cut-over tables the command builds on the last hand-drawn tables (template_tables)
            built.assert_called_with(levels="staging", as_live=True, live_path=B.template_tables())
        self.assertEqual(B.CUTOVER.parent, B.TRIAL.parent)                 # gitignored trial folder


@functools.lru_cache(maxsize=None)
def three_levels():
    """(candidate bytes, Panel, names, bands) of the three-level candidate (--levels all --as-live), built once."""
    with contextlib.redirect_stdout(io.StringIO()):
        return B.build(T.hand(), levels="all", as_live=True, approved=None)


class ThreeLevels(unittest.TestCase):
    """--levels all --as-live: the staging candidate held unchanged (the build's guard), with main and upper drawn
    below it at staging's grid, on internal turnouts and blocks under the device map's names (owner, 2026-11-16)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.P, cls.names, cls.bands = three_levels()
        cls.base = cutover()
        cls.root = tables.loads(cls.data).root
        cls.le = tables.layout_editor(cls.root, LIVE)
        cls.device = B.device_names()
        # the Dispatcher System's station buttons are parked out of the candidate (hartlib.parked): read them with it
        # put back from the parked part the build split off
        cls.stations = cls.le
        if "dispatcher" in B.PARKED:
            cls.stations = tables.layout_editor(B.parked.restore(cls.root, cls.P.parked_doc, {"dispatcher"}), LIVE)

    def test_staging_is_the_staging_candidate_joined_at_the_helix(self) -> None:
        # JOIN_HELIX on (owner, 2026-11-17, the helix-join release): staging as in its candidate but for the two
        # helix joins, the only difference the guard accepts (the helix bumpers become anchors, their tracks run on)
        self.assertTrue(B.JOIN_HELIX)
        self.assertEqual(self.P.staging_same, [
            "end bumper EB72 -> anchor AGE1 (hidden join TG224 to Track 135-H2, Mast 38RA)",
            "end bumper EB71 -> anchor AGE2 (hidden join TG225 to Track 135-H1, Mast 40RA)",
            "track segment TG6 connect2name EB71 -> AGE2",
            "track segment TG32 connect2name EB72 -> AGE1"])
        self.assertTrue([j for (b, j) in self.P.join_ends if b == 0])           # the helix joins reach staging
        self.assertEqual(self.P.scale, self.base[1].scale)
        self.assertEqual(self.P.staging_data, self.base[0])

    def test_the_guard_stops_on_any_other_change(self) -> None:
        def el(root, tag, **attrs):
            le = tables.layout_editor(root, LIVE)
            return next(e for e in le.iter(tag) if all(e.get(k) == v for k, v in attrs.items()))
        edits = {
            "a staging label moved": lambda r: el(r, "positionablelabel", text="STAGING LEVEL").set("x", "61"),
            "a staging bean changed": lambda r: next(t for t in tables.turnouts(r)
                                                     if tables.user_name(t) == "Switch 1").set("inverted", "true"),
            "a helix track's segment": lambda r: el(r, "tracksegment", ident="TG6").set("blockname", "Track X"),
            "a helix join moved": lambda r: el(r, "positionablepoint", ident="AGE2").set("x", "1600.0"),
            "a helix join's mast": lambda r: el(r, "positionablepoint", ident="AGE1").set(
                "westboundsignalmast", "Mast 38RA"),
            "a helix mast icon moved": lambda r: el(r, "signalmasticon", signalmast="Mast 38RA").set("x", "1"),
            "a staging BCI moved": lambda r: el(r, "BlockContentsIcon", blockcontents="Track K-1").set("y", "1"),
        }
        for what, edit in edits.items():
            with self.subTest(changed=what):
                doc = tables.loads(self.data)
                edit(doc.root)
                with self.assertRaisesRegex(B.BuildError, "staging guard"):
                    B.check_staging_unchanged(self.base, doc.tobytes(), self.P, LIVE)

    def test_the_staging_candidate_is_the_approved_panel(self) -> None:
        # Fails after a staging change on purpose until the owner approves the new panel in PanelPro and
        # build_layout_le.py --approve-staging records it (intended: the merge waits for that).
        B.check_approved(tables.layout_editor(tables.loads(self.base[0]).root, LIVE), B.APPROVED)

    def test_staging_is_checked_against_the_approved_panel(self) -> None:
        # The committed fingerprint is the owner's (refreshed by --approve-staging after an approval in PanelPro);
        # a staging change on purpose (STRETCH) is built with --review until then, so the tests check the mechanism
        # against a fingerprint of the candidate as built, and that the committed one is a fingerprint.
        self.assertEqual(B.read_approved(B.APPROVED)[-1][1], "panel")
        le = tables.layout_editor(tables.loads(self.base[0]).root, LIVE)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.sha256"
            B.write_approved(le, path, date="2026-11-16")
            B.check_approved(le, path)
            moved = copy.deepcopy(le)
            next(e for e in moved.iter("positionablelabel") if e.get("text") == "STAGING LEVEL").set("x", "61")
            with self.assertRaisesRegex(B.BuildError, r"element \d+ is positionablelabel STAGING LEVEL, approved "
                                                      r"positionablelabel STAGING LEVEL \(changed\)"):
                B.check_approved(moved, path)
            fewer = copy.deepcopy(le)
            fewer.remove(fewer[-1])
            with self.assertRaisesRegex(B.BuildError, "not the one the owner approved"):
                B.check_approved(fewer, path)
            # the build itself refuses a staging panel that is not the approved one, unless asked to (--review)
            with mock.patch.object(B, "check_approved", side_effect=B.BuildError("not approved")) as check, \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(B.BuildError, "not approved"):
                    B.build(T.hand(), levels="staging", as_live=True, approved=path)
                self.assertEqual(B.main(["--review", "--levels", "staging"]), 1)     # --review needs --as-live
            self.assertEqual(check.call_args.args[1], path)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.sha256"
            B.write_approved(moved, path, date="2026-11-16")
            self.assertIn("approved by the owner in PanelPro on 2026-11-16", path.read_text())
            B.check_approved(moved, path)
            with self.assertRaisesRegex(B.BuildError, "not the one the owner approved"):
                B.check_approved(le, path)
            path.write_text("# note\nnot a hash\n")
            with self.assertRaisesRegex(B.BuildError, "line 2: not"):
                B.check_approved(le, path)
            with self.assertRaisesRegex(B.BuildError, "--approve-staging"):
                B.check_approved(le, Path(tmp) / "none")

    def test_the_panel_has_the_windows_shape(self) -> None:
        w, h = int(self.le.get("panelwidth")), int(self.le.get("panelheight"))
        want = (B.FIT[0] - 18) / (B.FIT[1] - 60)
        self.assertLessEqual(abs(w / h / want - 1), stretch()[1])
        self.assertEqual((self.le.get("windowwidth"), self.le.get("windowheight")), tuple(map(str, B.FIT)))
        with self.assertRaisesRegex(B.plugin()[2].SchematicError, r"set le_stretch's factor to about 1\.\d+"):
            B.plugin()[1].check_stretch((1984, 1505), B.FIT, page_prefs())

    def test_no_compass_rose_and_the_plain_backdrop(self) -> None:
        urls = [el.find("icon").get("url") for el in self.le.iter("positionablelabel") if el.find("icon") is not None]
        self.assertEqual([u for u in urls if "hart_panel" in u], ["preference:resources/misc/hart_panel_bg_plain.jpg"])
        self.assertTrue((T.ROOT / "jmri/resources/misc/hart_panel_bg_plain.jpg").exists())
        ov = B.overlay_mod()
        # frozen once, at --freeze (plain_backdrop): a frozen file still holding the picture with the rose stops
        bad = copy.deepcopy(B.le_inputs.load().overlay)
        item = next(it for it in bad["items"] if "hart_panel_bg_plain" in it["xml"])
        item["xml"] = item["xml"].replace("hart_panel_bg_plain.jpg", "hart_panel_bg.jpg")
        with self.assertRaisesRegex(ov.OverlayError, "compass rose in it"):
            ov.validate(bad)
        items = ov.frozen_items(B.le_inputs.load().overlay)
        with self.assertRaisesRegex(ov.OverlayError, "backdrop pictures, not one"):
            ov.plain_backdrop([it for it in items if not it.backdrop])
        with self.assertRaisesRegex(ov.OverlayError, "not the misc/hart_panel_bg.jpg"):
            ov.plain_backdrop(items)                        # its backdrop is the plain picture already

    def test_the_status_cluster_stands_between_staging_and_main(self) -> None:
        def box(el):
            return int(el.get("x")), int(el.get("y"))
        rows = {}
        for el in self.le:
            name = el.get("text") if el.tag == "positionablelabel" else (el.get("sensor") or el.get("signalhead"))
            if el.get("level") == "10" and name in (B.overlay_mod().STATUS_LABELS | B.overlay_mod().STATUS_SENSORS
                                                     | B.overlay_mod().STATUS_HEADS):
                rows.setdefault(el.tag == "positionablelabel", []).append(el)
        captions, lamps = rows[True], rows[False]
        self.assertEqual((len(captions), len(lamps)), (4, 4))
        jt = B.importlib.import_module("schematic.jmri_text")
        rights = {box(c)[0] + jt.width(c.get("text"), 12) for c in captions}
        self.assertEqual(len(rights), 1)                    # right-justified ...
        self.assertTrue(all(c.get("justification") == "right" for c in captions))
        self.assertEqual({box(l)[0] for l in lamps}, {rights.pop() + B.overlay_mod().STATUS_GAP})   # lamps right
        right = max(box(l)[0] + 21 for l in lamps)          # the lamps' right edge: by the panel's right edge
        width = int(tables.layout_editor(tables.loads(self.base[0]).root, LIVE).get("panelwidth"))
        self.assertLessEqual(right, width - B.overlay_mod().EDGE)
        self.assertGreater(right, width - B.overlay_mod().EDGE - 80)
        staging_low = self.P.band_boxes[0][3]
        main_title = next(lb for lb in self.P.labels if lb["text"] == "MAIN LEVEL")
        for el in captions + lamps:
            self.assertGreater(box(el)[1], staging_low - 40)                          # in the gap ...
            self.assertLess(box(el)[1] + 20, main_title["box"][1])                    # ... above the main level
        items = B.overlay_mod().frozen_items(B.le_inputs.load().overlay)
        lone = [it for it in items if not (it.group == "status" and it.el.tag == "positionablelabel" and
                                           it.text == "LCOS")]
        with self.assertRaisesRegex(B.overlay_mod().OverlayError, "a lamp with no caption"):
            B.overlay_mod().arrange_status(lone)

    def test_the_gaps_between_levels_are_as_small_as_is_clean(self) -> None:
        self.assertEqual(len(self.P.gaps), 2)
        boxes = self.P.band_boxes
        for i, gap in enumerate(self.P.gaps):
            self.assertAlmostEqual(boxes[i + 1][1] - boxes[i][3], gap)
        titles = [lb for lb in self.P.labels if lb.get("kind") == "title"][1:]
        extent = B.plugin()[1].extent
        lows = [max(extent(self.P, 0)[3], self.base[1].overlay["bottom"]), extent(self.P, 1)[3]]
        for title, low in zip(titles, lows):
            self.assertAlmostEqual(title["box"][1] - low, page_prefs()["le_title_clear"], delta=1.0)

    def test_owner_layout_rules_of_2026_11_16(self) -> None:
        import math
        angles = [a for _t, _b, o in B.schematic()[0] for a in (o.get("le_crossover_angle") or {}).values()]
        self.assertEqual(set(angles), {45})
        # every crossover at its level's angle, or as near as its track allows (the plugin logs those)
        limited = {re.search(r"switch (\d+)", line).group(1) for line in self.P.log if "no room for" in line
                   and "crossover" in line}
        for t in self.le.findall("layoutturnout"):
            if "XOVER" not in t.get("type"):
                continue
            p = {L: (float(t.get("x" + L.lower())), float(t.get("y" + L.lower()))) for L in "ABCD"}
            if t.get("type") == "DOUBLE_XOVER":     # JMRI draws from 5/8 of the way from A to A-B's middle
                am = [p["A"][k] + 5 / 8 * ((p["A"][k] + p["B"][k]) / 2 - p["A"][k]) for k in (0, 1)]
                dx, dy = float(t.get("xcen")) - am[0], float(t.get("ycen")) - am[1]
            else:
                dx = (p["D"][0] + p["C"][0] - p["A"][0] - p["B"][0]) / 2
                dy = (p["D"][1] + p["C"][1] - p["A"][1] - p["B"][1]) / 2
            angle = math.degrees(math.atan2(abs(dy), abs(dx)))
            number = re.sub(r"\D", "", t.get("turnoutname") or "")
            with self.subTest(crossover=t.get("turnoutname")):
                if number in limited:
                    self.assertGreater(angle, min(angles) - 0.5)
                else:
                    # whole pixels (JMRI rebuilds the points exactly): within half a degree of its level's angle
                    self.assertTrue(any(abs(angle - a) <= 0.5 for a in angles), angle)
        # South Yard's names on one centre x
        jt = B.importlib.import_module("schematic.jmri_text")
        centres = {round(int(el.get("x")) + jt.width(el.get("text"), int(el.get("size")), False) / 2)
                   for el in self.le.iter("positionablelabel") if el.get("text") in B.NAME_COLUMNS[0]}
        self.assertLessEqual(max(centres) - min(centres), 1, centres)
        # the engine house's buttons step alike
        xs = [int(next(el for el in self.stations.iter("sensoricon")
                       if el.get("sensor") == f"MoveToTrack_EH-{n}_stored").get("x")) for n in (1, 2, 3)]
        self.assertEqual(xs[2] - xs[1], xs[1] - xs[0])
        # West Yard's W-2 follows W-1 one row down at the engine house's step (staging's le_labels extra_follow)
        button = lambda n: next(el for el in self.stations.iter("sensoricon")      # noqa: E731
                                if el.get("sensor") == f"MoveToTrack_{n}_stored")
        w1, w2 = button("W-1"), button("W-2")
        rows = (int(w2.get("y")) - int(w1.get("y"))) / (int(button("EH-2").get("y")) - int(button("EH-1").get("y")))
        self.assertAlmostEqual(int(w2.get("x")) - int(w1.get("x")), rows * (xs[1] - xs[0]), delta=1)
        self.assertLess(int(w2.get("x")), int(w1.get("x")))
        # the title caption renamed at freeze, centred where the old one stood, and a frozen old one stops
        ov = B.overlay_mod()
        el = ET.fromstring('<positionablelabel x="877" y="48" text="Neville Island" size="28" style="1"/>')
        self.assertTrue(ov.recaption(el))
        old_w, new_w = (ov.text_box(t, 28, True, "t")[0] for t in ("Neville Island", "HART RAILROAD"))
        self.assertEqual(el.get("text"), "HART RAILROAD")
        self.assertAlmostEqual(int(el.get("x")) + new_w / 2, 877 + old_w / 2, delta=0.5)
        bad = copy.deepcopy(B.le_inputs.load().overlay)
        item = next(it for it in bad["items"] if 'text="HART RAILROAD"' in it["xml"])
        item["xml"] = item["xml"].replace('text="HART RAILROAD"', 'text="Neville Island"')
        with self.assertRaisesRegex(ov.OverlayError, "re-freeze"):
            ov.validate(bad)
        # each OS lamp of a plain switch centred in its control circle
        seg_block = {b.findtext("occupancysensor").strip(): b.findtext("userName") for b in self.root.iter("block")
                     if b.find("occupancysensor") is not None}
        own = {t.get("blockname"): t for t in self.le.findall("layoutturnout") if "XOVER" not in t.get("type")}
        lamps = [el for el in self.le.iter("sensoricon") if el.get("level") == "10"
                 and seg_block.get(el.get("sensor")) in own]
        self.assertGreaterEqual(len(lamps), 15)
        for el in lamps:
            t = own[seg_block[el.get("sensor")]]
            self.assertLessEqual(math.dist((int(el.get("x")) + 5, int(el.get("y")) + 5),
                                           (float(t.get("xcen")), float(t.get("ycen")))), 1.0, el.get("sensor"))
        self.assertEqual(set(self.base[1].extra_x), {"Track EH-3", "Track W-2"})    # stepped by the plugin

    def test_owner_layout_rules_of_2026_11_16_second_round(self) -> None:
        import math
        xo = {t.get("turnoutname"): t for t in self.le.findall("layoutturnout") if "XOVER" in t.get("type")}
        pt = lambda t, L: (float(t.get("x" + L)), float(t.get("y" + L)))      # noqa: E731
        # 101 and 103 (one three-way switch): each two plain turnouts on its one name, their throats on the shared
        # track two legs and Track 101-103's least length apart, each diagonal at 45 degrees
        plain = defaultdict(list)
        for t in self.le.findall("layoutturnout"):
            if t.get("turnoutname") in ("Switch 101", "Switch 103"):
                plain[t.get("turnoutname")].append(t)
        self.assertEqual({k: sorted(t.get("type") for t in v) for k, v in plain.items()},
                         {"Switch 101": ["RH_TURNOUT", "RH_TURNOUT"], "Switch 103": ["LH_TURNOUT", "LH_TURNOUT"]})
        middle = {k: next(t for t in v if t.get("ycen") == "800.0") for k, v in plain.items()}
        throats = abs(float(middle["Switch 103"].get("xcen")) - float(middle["Switch 101"].get("xcen")))
        self.assertLessEqual(throats, 37)
        for k, v in plain.items():
            (x0, y0), (x1, y1) = sorted((float(t.get("xcen")), float(t.get("ycen"))) for t in v)
            self.assertAlmostEqual(abs(y1 - y0), abs(x1 - x0), delta=0.5, msg=k)
        self.assertNotIn("101-103", {el.get("text") for el in self.le.iter("positionablelabel")})
        limited = {re.search(r"switch (\d+)", line).group(1) for line in self.P.log if "no room for" in line
                   and "crossover" in line}
        self.assertFalse(limited & {"225", "241"})
        # SW-101 once, below its lower turnout
        labels = [el for el in self.le.iter("positionablelabel") if el.get("text") == "SW-101"]
        self.assertEqual(len(labels), 1)
        self.assertGreaterEqual(int(labels[0].get("y")), max(float(t.get("ycen")) for t in plain["Switch 101"]))
        # every half of a single crossover shows its own OS lamp, in the middle of its half's two leg ends (the
        # throat, where the diagonal leaves its track), as 35's two were; the hand-drawn panel had none for 7b, 23b
        seg_block = {b.findtext("occupancysensor").strip(): b.findtext("userName") for b in self.root.iter("block")
                     if b.find("occupancysensor") is not None}
        lamp_of = {seg_block.get(el.get("sensor")): el for el in self.le.iter("sensoricon") if el.get("level") == "10"}
        for name in ("Switch 7", "Switch 23", "Switch 35"):
            t = xo[name]
            for legs, attr in (("ab", "blockname"), ("cd", "blockcname")):
                el = lamp_of.get(t.get(attr))
                self.assertIsNotNone(el, (name, t.get(attr)))
                half = [pt(t, L) for L in legs]
                mid = ((half[0][0] + half[1][0]) / 2, half[0][1])
                self.assertLessEqual(math.dist((int(el.get("x")) + 5, int(el.get("y")) + 5), mid), 1.0, t.get(attr))
        ov = B.overlay_mod()
        ov.check_half_lamps(self.le, {v: k for k, v in seg_block.items()})
        bare = copy.deepcopy(self.le)
        bare.remove(next(el for el in bare.iter("sensoricon") if el.get("sensor") == "BS Switch 7b"))
        with self.assertRaisesRegex(ov.OverlayError, r"Switch 7: lamps for \['OS Switch 7'\] but none"):
            ov.check_half_lamps(bare, {v: k for k, v in seg_block.items()})
        # staging from Plane to East End drawn two columns west (staging's le_shift), and Track 235-241's straight
        # at 241 longer (main_upper's le_longer_straights): on the Layout Editor bands only, applied by the plugin
        raw = B.schematic()[0]
        drawn = B.plugin()[1].drawn_bands(raw, page_prefs())
        shift = raw[0][2]["le_shift"]["Staging"]
        self.assertEqual([(e["from"], e["to"], e["columns"]) for e in shift], [("5", "33", -2)])
        moved = {n for n in raw[0][1]["x"] if drawn[0][1]["x"][n] != raw[0][1]["x"][n]}
        self.assertTrue(moved)
        self.assertEqual({drawn[0][1]["x"][n] - raw[0][1]["x"][n] for n in moved}, {-2})
        changed = [(i, sid) for i, ((_t, b0, _o), (_u, b1, _p)) in enumerate(zip(raw, drawn))
                   for sid in b0["need"] if b0["need"][sid] != b1["need"][sid]]
        self.assertEqual(len(changed), 1)
        i, sid = changed[0]
        self.assertAlmostEqual(raw[i][1]["need"][sid][0] - drawn[i][1]["need"][sid][0],
                               page_prefs()["le_longer_straights"]["Upper"][0]["columns"])

    def test_station_buttons_show_no_track_word(self) -> None:
        if "dispatcher" in B.PARKED:        # parked: none on the candidate, all 12 in its parked part
            self.assertFalse([el for el in self.le.iter("sensoricon") if (el.get("sensor") or "").startswith("Move")])
        buttons = [el for el in self.stations.iter("sensoricon") if (el.get("sensor") or "").startswith("MoveTo")]
        self.assertEqual(len(buttons), 12)
        for el in buttons:
            for e in [el] + [c for c in el if c.tag.endswith("Text")]:
                self.assertFalse((e.get("text") or "").startswith("Track "), el.get("sensor"))
        self.assertIn("EH-1", {el.get("text") for el in buttons})
        self.assertIn("MoveToTrack_EH-1_stored", {el.get("sensor") for el in buttons})      # the names keep it
        stations = T._load("reconcile_dispatcher_stations", paths.LAYOUT_SCRIPTS / "reconcile_dispatcher_stations.py")
        self.assertEqual(stations.station_display("Track EH-1", generated=True), "EH-1")
        self.assertEqual(stations.station_display("Track EH-1"), "Track EH-1")            # the hand-drawn panel
        self.assertEqual(stations.station_display("Track East Lead", generated=True), "East End")
        ov = B.overlay_mod()
        bad = copy.deepcopy(B.le_inputs.load().overlay)
        item = next(it for it in bad["items"] if "MoveToTrack_EH-1" in it["xml"])
        item["xml"] = item["xml"].replace('text="EH-1"', 'text="Track EH-1"')
        with self.assertRaisesRegex(ov.OverlayError, 'station button shows "Track " before its track'):
            ov.validate(bad)
        ok = copy.deepcopy(B.le_inputs.load().overlay)                # "Track Power" is no station button
        self.assertTrue(any('text="Track Power"' in it["xml"] for it in ok["items"]))
        ov.validate(ok)
        live = tables.layout_editor(tables.read(T.hand()), LIVE)  # freeze reads a copy: the panel unchanged
        before = ET.tostring(live)
        shown = [it.el.get("text") for it in ov.shown_items(live) if ov.is_station_button(it.el)]
        self.assertIn("EH-1", shown)
        self.assertEqual(ET.tostring(live), before)

    def test_main_and_upper_objects_are_internal_with_device_map_names(self) -> None:
        added_t = [t for t in tables.turnouts(self.root) if B.is_level_bean(t)]
        added_lb = [b for b in tables.layout_blocks(self.root) if B.is_level_bean(b)]
        added_b = {tables.user_name(b) for b in tables.blocks(self.root) if B.is_level_bean(b)}
        self.assertEqual(len(added_t), 41)
        self.assertTrue(all(tables.system_name(t).startswith("IT:HART:C3:") for t in added_t))
        self.assertEqual({tables.user_name(t) for t in added_t}, {v for k, v in self.device.items()
                                                                   if k.startswith("Switch ")})
        self.assertEqual({tables.user_name(b) for b in added_lb}, {v for k, v in self.device.items()
                                                                    if not k.startswith("Switch ")})
        self.assertEqual(added_b, {tables.user_name(b) for b in added_lb})
        self.assertEqual(len(added_lb), 125)          # the 107 Loop's two halves and 225's four corners
        self.assertTrue(all(tables.system_name(b).startswith("IB:C3:") for b in tables.blocks(self.root)
                            if B.is_level_bean(b)))

    def test_main_and_upper_masts_and_no_sensors(self) -> None:
        """Main and upper: their 41 control-point masts (main_upper_masts.csv), each in the slot JMRI resolves to its
        facing track and protected OS block (108LA and 108LB on Switch 107's normal and diverging legs, facing the 107
        Loop's two halves; 226RA and 226RB each protecting its own corner of double crossover 225), on virtual heads
        and masts signal_coordinator.py never enrols; no sensors."""
        level = {t["ident"] for t in self.P.turnouts if t["band"]} | {k for k, p in self.P.points.items() if p["band"]}
        rows = {r["mast"]: r for r in B.read_level_masts()}
        on_level = [m for m in self.P.masts if m["ident"] in level]
        self.assertEqual({m["mast"] for m in on_level}, set(rows))
        ix = B.slots_module().Index(self.le)
        turnouts = {self.P.name(t["ident"]): t for t in self.P.turnouts}
        for m in on_level:
            ident = self.P.name(m["ident"])
            f, pr = ix.blocks(m["kind"], ident, m["slot"])
            self.assertEqual((f, pr), (rows[m["mast"]]["facing"], [rows[m["mast"]]["protects"]]), m["mast"])
            if rows[m["mast"]]["leg"]:
                normal = "B" if turnouts[ident]["continuing"] == "2" else "C"
                self.assertEqual(m["slot"] == normal, rows[m["mast"]]["leg"] == "normal", m["mast"])
        slot = {m["mast"]: (self.P.name(m["ident"]), m["slot"]) for m in on_level}
        normal = "B" if turnouts[slot["Mast 108LA"][0]]["continuing"] == "2" else "C"
        self.assertEqual((slot["Mast 108LA"][1], slot["Mast 108LB"][1]), (normal, "BC".replace(normal, "")))
        self.assertEqual({m: (rows[m]["facing"], rows[m]["protects"]) for m in ("Mast 226RA", "Mast 226RB")},
                         {"Mast 226RA": ("Track 223-225 1", "OS Switch 225a"),
                          "Mast 226RB": ("Track 223-225 2", "OS Switch 225d")})
        self.assertEqual(B.lcos_named([r["system_name"] for r in rows.values()]
                                      + [h for r in rows.values() for h, _u in r["heads"]]), [])
        self.assertEqual(B.lcos_named(["IH3332", "IF$shsm:basic:one-low(IH3332)", "IH:HART:C3:108LA"]),
                         ["IF$shsm:basic:one-low(IH3332)", "IH3332"])
        heads = [h for h in self.root.find("signalheads") if B.is_level_bean(h)]
        masts = [m for m in self.root.find("signalmasts") if B.is_level_bean(m)]
        self.assertEqual((len(heads), len(masts)), (53, 41))
        self.assertEqual({m.findtext("userName") for m in masts}, set(rows))
        written = {self.P.name(i) for i in level}
        for el in self.le:
            if el.get("ident") in written:
                self.assertFalse([k for k in el.attrib if k.endswith("boundsensor")], el.get("ident"))
                self.assertIsNone(el.find("sensorA"))

    def test_helix_masts_stand_at_the_helix_joins(self) -> None:
        # joined (JOIN_HELIX): Masts 38RA and 40RA stand at the helix-entrance anchors, protecting the helix run
        ix = B.slots_module().Index(self.le)
        got = {m["mast"]: (self.P.name(m["ident"]), m["slot"], ix.blocks(m["kind"], self.P.name(m["ident"]), m["slot"]))
               for m in self.P.masts if m["mast"] in ("Mast 38RA", "Mast 40RA")}
        self.assertEqual(got["Mast 38RA"], ("AGE1", "east", ("Track McKeesport", ["Track 135-H2"])))
        self.assertEqual(got["Mast 40RA"], ("AGE2", "east", ("Track McKees Rocks", ["Track 135-H1"])))
        self.assertEqual([m for _band, m, _why in self.P.moved], ["Mast 38RA", "Mast 40RA"])   # the plugin logs both

    def test_one_block_contents_icon_per_block_on_every_level(self) -> None:
        icons = Counter(el.get("blockcontents") for el in self.le.iter("BlockContentsIcon"))
        # every block but those B.OPTIONAL_READOUTS lets go when no clean spot is left (logged)
        left_out = {b for v in B.OPTIONAL_READOUTS.values() for b in v} - set(icons)
        skipped = {re.search(r"block contents of (.+?): no clean spot", m).group(1) for m in self.P.bcis_skipped}
        self.assertEqual(skipped, left_out)
        self.assertEqual(len(skipped), len(self.P.bcis_skipped))
        self.assertEqual(set(icons) | left_out, T.used_blocks(self.le))
        self.assertEqual(set(icons.values()), {1})
        staging = {b["block"] for b in self.base[1].bcis}
        self.assertEqual(len(staging), 57)
        size = {el.get("blockcontents"): el.get("size") for el in self.le.iter("BlockContentsIcon")}
        self.assertEqual({size[b] for b in staging}, {"13"})
        self.assertEqual({size[b] for b in set(size) - staging}, {str(B.LEVEL_LE_LABELS["block_contents_size"])})

    def test_switch_numbers_and_track_names(self) -> None:
        labels = [el for el in self.le.iter("positionablelabel") if el.get("text")]
        numbers = {el.get("text"): el.get("size") for el in labels if el.get("text").startswith("SW-")}
        # a single crossover reads by its number; the helix-top 129 and 135 keep a half on each level
        self.assertLessEqual({"SW-101", "SW-225", "SW-245", "SW-129A", "SW-129B", "SW-135A", "SW-135B"}, set(numbers))
        self.assertNotIn("SW-101A", numbers)
        self.assertEqual(set(numbers.values()), {"13"})
        names = {lb["text"] for lb in self.P.labels if lb.get("kind") == "name" and lb["band"]}
        tracks = {v.removeprefix("Track ") for v in self.device.values() if v.startswith("Track ")}
        self.assertTrue(names)
        self.assertLessEqual(names - {"McKees Rocks", "McKeesport"}, tracks)    # the helix tracks keep their names
        self.assertEqual(len(self.P.names_skipped), len([x for x in self.P.log if "names_last: left out" in x]))

    def test_window_fits_the_display_and_the_panel_scrolls(self) -> None:
        w, h = int(self.le.get("panelwidth")), int(self.le.get("panelheight"))
        self.assertGreater(h, B.FIT[1])
        self.assertLessEqual(int(self.le.get("windowwidth")), B.FIT[0])
        self.assertLessEqual(int(self.le.get("windowheight")), B.FIT[1])
        self.assertEqual(self.le.get("scrollable"), "both")        # larger than its window: it scrolls both ways
        self.assertGreaterEqual(w, self.P.size[0])

    def test_audit_polish_reconcile_and_facts_on_the_candidate(self) -> None:
        polish = T._load("polish_hart_layout_editor", paths.LAYOUT_SCRIPTS / "polish_hart_layout_editor.py")
        stations = T._load("reconcile_dispatcher_stations", paths.LAYOUT_SCRIPTS / "reconcile_dispatcher_stations.py")
        facts = T._load("check_layout_facts", T.ROOT / "tools/audit/check_layout_facts.py")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(self.data)
            with contextlib.redirect_stdout(io.StringIO()):
                for fn in (polish.apply_visual_standard, polish.apply_overlap_cleanup,
                           polish.apply_block_labels_only):
                    self.assertEqual(fn(path, check=True)[1], [], fn.__name__)
                    fn(path, check=False, reference=path)
                self.assertEqual(stations.main(["--panel", str(path), "--check", "--no-sync"]), 0)
                self.assertEqual(AUDIT.main(["--tables", str(path)]), 0)   # --strict waits for Stage 1
                self.assertEqual(facts.main(["--tables", str(path)]), 0)
            self.assertEqual(path.read_bytes(), self.data)


class Rebuilt(unittest.TestCase):
    """Phase 3b: the candidate is built from the frozen files and the schematic alone. Built from tables with no
    "HART Railroad" panel, or from the candidate itself (after the cut-over tables.xml holds the generated panel), it
    is the same file byte for byte."""

    def build_from(self, data: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(data)
            with contextlib.redirect_stdout(io.StringIO()):
                return B.build(path, levels="staging", as_live=True, approved=None)[0]

    def test_without_the_hand_drawn_panel(self) -> None:
        data = cutover()[0]
        bare = without_live_panel(T.hand().read_bytes())
        self.assertIsNone(tables.layout_editor(tables.loads(bare).root, LIVE))
        self.assertEqual(self.build_from(bare), data)

    def test_after_the_cut_over(self) -> None:
        data = cutover()[0]
        self.assertEqual(self.build_from(data), data)
        # the cut-over tables hold the main and upper objects too: refused, and the command builds on the last
        # hand-drawn tables from git instead (template_tables)
        three = three_levels()[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(three)
            with contextlib.redirect_stdout(io.StringIO()), \
                    self.assertRaisesRegex(B.BuildError, "already holds the main and upper objects"):
                B.build(path, levels="staging", as_live=True, approved=None)
            with mock.patch.object(B.paths, "TABLES_XML", path), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(B.template_tables(), T.hand())
            self.assertIn("building on the last hand-drawn tables", out.getvalue())


def two_block_panel(sensor="", turnout_type="RH_TURNOUT", ident="A1") -> ET.Element:
    """EB1 -[W]- A1 -[E]- TO1 (legs B and C to bumpers), an Entry/Exit sensor in A1's east slot."""
    east = f' eastboundsensor="{sensor}"' if sensor else ""
    return ET.fromstring(
        '<LayoutEditor>'
        f'<layoutturnout ident="TO1" type="{turnout_type}" turnoutname="T1" blockname="OS" continuing="2" '
        'xcen="200" ycen="0" xb="220" yb="0" xc="220" yc="10" ver="1" connectaname="T2" connectbname="T3" '
        'connectcname="T4"/>'
        '<tracksegment ident="T1" blockname="W" connect1name="EB1" type1="POS_POINT" '
        f'connect2name="{ident}" type2="POS_POINT"/>'
        f'<tracksegment ident="T2" blockname="E" connect1name="{ident}" type1="POS_POINT" connect2name="TO1" '
        'type2="TURNOUT_A"/>'
        '<tracksegment ident="T3" blockname="B" connect1name="TO1" type1="TURNOUT_B" connect2name="EB2" '
        'type2="POS_POINT"/>'
        '<tracksegment ident="T4" blockname="C" connect1name="TO1" type1="TURNOUT_C" connect2name="EB3" '
        'type2="POS_POINT"/>'
        '<positionablepoint ident="EB1" type="END_BUMPER" x="0" y="0" connect1name="T1"/>'
        f'<positionablepoint ident="{ident}" type="ANCHOR" x="100" y="0" connect1name="T1" connect2name="T2"'
        f'{east}/>'
        '<positionablepoint ident="EB2" type="END_BUMPER" x="300" y="0" connect1name="T3"/>'
        '<positionablepoint ident="EB3" type="END_BUMPER" x="300" y="60" connect1name="T4"/>'
        '</LayoutEditor>')


class BuilderErrors(unittest.TestCase):
    """The cut-over helpers stop with BuildError, naming what is at fault."""

    def test_idents_read_off_the_live_panel(self) -> None:
        got = I.staging_idents(two_block_panel(), {"n1": "TO1"})
        self.assertEqual(got["turnouts"], {"n1": "TO1"})
        self.assertEqual(got["boundaries"], [{"blocks": ["E", "W"], "ident": "A1"}])
        self.assertEqual(got["ends"], {"W": "EB1", "B": "EB2", "C": "EB3"})
        self.assertEqual(got["segments"], {"W": "T1", "E": "T2", "B": "T3", "C": "T4"})
        le = two_block_panel()
        le.find("positionablepoint[@ident='EB3']").set("connect1name", "T3")     # two bumpers end block B
        with self.assertRaisesRegex(I.InputsError, "two bumpers"):
            I.staging_idents(le, {})

    def test_live_points_off_the_track_stop(self) -> None:
        le = two_block_panel()
        le.find("positionablepoint[@ident='EB3']").attrib.pop("connect1name")      # a bumper on nothing
        with self.assertRaisesRegex(I.InputsError, "END_BUMPER EB3 connects to no track"):
            I.staging_idents(le, {})
        le = two_block_panel()
        le.find("tracksegment[@ident='T4']").attrib.pop("blockname")
        with self.assertRaisesRegex(I.InputsError, "EB3 meets a track segment with no block"):
            I.staging_idents(le, {})
        le = two_block_panel()
        le.find("positionablepoint[@ident='A1']").set("connect2name", "T99")
        with self.assertRaisesRegex(I.InputsError, "ANCHOR A1 connects to"):
            I.staging_idents(le, {})

    def test_freeze_options(self) -> None:
        for argv, why in ((["--freeze", "--levels", "all"], "--freeze takes only"),
                          (["--freeze", "--levels", "staging"], "--freeze takes only"),
                          (["--freeze-to", "/nowhere"], "--freeze-to goes with --freeze")):
            with self.subTest(argv=argv), contextlib.redirect_stdout(io.StringIO()) as out, \
                    mock.patch.object(B, "freeze") as frozen, mock.patch.object(B, "build") as built:
                self.assertEqual(B.main(argv), 1)
            self.assertIn(why, out.getvalue())
            frozen.assert_not_called()
            built.assert_not_called()

    def test_freeze_failures_are_errors_not_tracebacks(self) -> None:
        T.hand()                        # freeze reads the hand-drawn tables from git: skip without them
        B.plugin()
        layers = B.importlib.import_module("schematic.layers")
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(layers, "load", side_effect=ValueError("bad JSON")), \
                mock.patch.dict(os.environ, {"SCHEMATIC_CACHE": ""}), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(B.main(["--freeze", "--freeze-to", str(Path(tmp) / "f")]), 1)
        self.assertIn("ERROR: cannot read the staging plan overrides", out.getvalue())
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(B.main(["--freeze", "--tables", str(Path(tmp) / "none.xml"),
                                     "--freeze-to", str(Path(tmp) / "f")]), 1)
        self.assertIn("ERROR: cannot read", out.getvalue())

    def test_freeze_replaces_the_folder_only_after_the_rebuild_matches(self) -> None:
        overlay = I.load().overlay

        def fake_build(_path, levels, as_live, inputs, freeze_from=None, approved=None):      # the two builds, without drawing
            if freeze_from is not None:
                inputs.overlay = overlay
                return (b"from the panel",)
            return (rebuilt,)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "staging_le"
            folder.mkdir()
            (folder / "kept.txt").write_text("the committed files")
            rebuilt = b"something else"
            with mock.patch.object(B, "build", side_effect=fake_build), \
                    self.assertRaisesRegex(B.BuildError, "do not rebuild"):
                B.freeze(T.hand(), folder)
            self.assertEqual([p.name for p in folder.iterdir()], ["kept.txt"])     # untouched
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["staging_le"])   # nothing left beside
            rebuilt = b"from the panel"
            with mock.patch.object(B, "build", side_effect=fake_build):
                written = B.freeze(T.hand(), folder)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), sorted(p.name for p in I.FOLDER.iterdir()))
            self.assertEqual(sorted(written), sorted(folder / p.name for p in I.FOLDER.iterdir()))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["staging_le"])
            for p in I.FOLDER.iterdir():
                if p.name != "panel.json":                  # its note names today's date: compare the rest
                    self.assertEqual((folder / p.name).read_text().split("\n", 1)[1],
                                     p.read_text().split("\n", 1)[1], p.name)

    def test_freezing_refuses_a_generated_panel(self) -> None:
        doc = tables.load(T.hand())
        tables.layout_editor(doc.root, LIVE).insert(1, tables.generated_marker_label())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(doc.tobytes())
            with self.assertRaisesRegex(B.BuildError, "generated one"):
                B.freeze(path, Path(tmp) / "out")
            self.assertFalse((Path(tmp) / "out").exists())
            with self.assertRaisesRegex(I.InputsError, "generated one"):
                I.from_live(doc.root, tables.layout_editor(doc.root, LIVE), B.slots_module(), {}, "", "")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(B.main(["--freeze", "--check"]), 1)
            self.assertIn("--freeze takes only", out.getvalue())

    def test_the_checkout_tables_are_refused_whatever_hart_tables_says(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(B.paths, "TABLES_XML", Path(tmp) / "c.xml"):
            self.assertTrue(B.live_target(paths.REPO_TABLES_XML))
            self.assertTrue(B.live_target(Path(tmp) / "c.xml"))
            self.assertFalse(B.live_target(Path(tmp) / "other.xml"))

    def test_generated_audit_needs_a_candidate(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(AUDIT.main(["--generated"]), 2)
        self.assertIn("--tables", out.getvalue())

    def test_leg_b_reads_the_live_leg(self) -> None:
        le = two_block_panel()
        chains = I.live_chains(le)
        lts = {t.get("ident"): t for t in le.findall("layoutturnout")}
        self.assertEqual(B.live_leg_first(chains, lts, "TO1", "B"), "B")
        self.assertEqual(B.live_leg_first(chains, lts, "TO1", "A"), "E")
        with self.assertRaisesRegex(B.BuildError, "reaches no track"):
            B.live_leg_first(chains, lts, "TO1", "D")

    def test_sensors_go_back_in_their_live_slot_or_stop(self) -> None:
        live = two_block_panel("NX 1")
        slots = B.slots_module()
        self.assertEqual(I.live_sensor_slots(live), {("A1", "east"): "NX 1"})
        rows = I.live_sensors(live, slots)
        self.assertEqual(rows, [dict(sensor="NX 1", kind="anchor", ident="A1", slot="east", facing="W",
                                     protects=["E"])])
        gen = two_block_panel()
        self.assertEqual(B.bind_sensors(gen, rows), 1)
        self.assertEqual(gen.find("positionablepoint[@ident='A1']").get("eastboundsensor"), "NX 1")
        with self.assertRaisesRegex(B.BuildError, "not on the new panel"):
            B.bind_sensors(two_block_panel(ident="A9"), rows)
        flipped = two_block_panel()
        for s in flipped.findall("tracksegment"):
            s.set("blockname", {"W": "E", "E": "W"}.get(s.get("blockname"), s.get("blockname")))
        with self.assertRaisesRegex(B.BuildError, "faces"):
            B.bind_sensors(flipped, rows)

    def test_turnouts_must_keep_their_live_facts(self) -> None:
        le = two_block_panel()
        frozen = I.Inputs(panel_name="P", attrs={}, drawing_options=None,
                          turnouts=[{k: v for k, v in le.find("layoutturnout").attrib.items()
                                     if k in I.TURNOUT_COLUMNS}],
                          chains=I.live_chains(le), boundaries=[], ends={}, segments={}, sensors=[], masts=[])
        self.assertEqual(frozen.turnout_facts(), B.turnout_facts(le))     # the frozen facts read as the panel's
        B.check_live_turnouts(two_block_panel(), frozen, swapped=set())
        with self.assertRaisesRegex(B.BuildError, "type: live RH_TURNOUT, new LH_TURNOUT"):
            B.check_live_turnouts(two_block_panel(turnout_type="LH_TURNOUT"), frozen, swapped=set())
        gen = two_block_panel()
        t = gen.find("layoutturnout")
        t.set("connectbname", "T4")
        t.set("connectcname", "T3")
        with self.assertRaisesRegex(B.BuildError, "legs"):
            B.check_live_turnouts(gen, frozen, swapped=set())
        # a LEGS_SWAPPED turnout must have them swapped, its hand and continuing route with them
        swapped = two_block_panel(turnout_type="LH_TURNOUT")
        t = swapped.find("layoutturnout")
        t.set("connectbname", "T4")
        t.set("connectcname", "T3")
        t.set("continuing", "4")
        B.check_live_turnouts(swapped, frozen, swapped={"TO1"})
        with self.assertRaisesRegex(B.BuildError, "type: live LH_TURNOUT, new RH_TURNOUT"):
            B.check_live_turnouts(two_block_panel(), frozen, swapped={"TO1"})


class FrozenFiles(unittest.TestCase):
    """le_inputs.load checks every frozen file's shape and stops naming the file, line and field."""

    def broken(self, name: str, edit) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "f"
            folder.mkdir()
            for f in I.FOLDER.iterdir():
                (folder / f.name).write_bytes(f.read_bytes())
            p = folder / name
            p.write_text(edit(p.read_text(encoding="utf-8")), encoding="utf-8")
            with self.assertRaises(I.InputsError) as e:
                I.load(folder)
        return str(e.exception)

    def test_the_committed_files_load(self) -> None:
        got = I.load()
        self.assertEqual((len(got.turnouts), len(got.chains), len(got.boundaries), len(got.ends), len(got.segments),
                          len(got.sensors), len(got.masts), len(got.overlay["items"])),
                         (20, 35, 17, 7, 26, 23, 49, 91))
        self.assertEqual(got.panel_name, LIVE)
        for f in sorted(I.FOLDER.iterdir()):
            with self.subTest(file=f.name):
                head = f.read_text(encoding="utf-8")[:300]
                self.assertIn("Edit here, not in the panel", head)

    def test_bad_files_stop_with_the_place(self) -> None:
        cases = [
            ("turnouts.csv", lambda t: t.split("\n", 1)[1], "provenance note"),
            ("turnouts.csv", lambda t: t.replace("ident,turnoutname", "id,turnoutname"), "columns"),
            ("turnouts.csv", lambda t: t.replace(",LH_TURNOUT,", ",ODD_TURNOUT,", 1), "line 3: type"),
            ("tracks.csv", lambda t: t.replace("TOL3,", "NOPE,", 1), "no such turnout leg"),
            # a leg is one whole letter: never blank or several (a substring test would let these through)
            ("tracks.csv", lambda t: t.replace("TOL3,A,TO111,A,", "TOL3,,TO111,A,", 1), "leg ''"),
            ("tracks.csv", lambda t: t.replace("TOL3,A,TO111,A,", "TOL3,AB,TO111,A,", 1), "leg 'AB'"),
            ("tracks.csv", lambda t: t.replace("TOL3,A,TO111,A,", "TOL3,A,TO111,,", 1), "leg ''"),
            ("tracks.csv", lambda t: t.replace("TOL3,A,TO111,A,", "TOL3,A,TO111,BCD,", 1), "leg 'BCD'"),
            ("sensors.csv", lambda t: t.replace(",turnout,TO111,A,", ",turnout,TO111,,", 1), "slot ''"),
            ("sensors.csv", lambda t: t.replace(",turnout,TO111,A,", ",turnout,TO111,AB,", 1), "slot 'AB'"),
            ("masts.csv", lambda t: t.replace(",turnout,TO111,A,", ",turnout,TO111,,", 1), "slot ''"),
            ("masts.csv", lambda t: t.replace(",turnout,TO111,A,", ",turnout,TO111,BC,", 1), "slot 'BC'"),
            ("masts.csv", lambda t: t.replace(",2L,1,1;23,", ",2L,1,;23,", 1), "must be 'toward;far'"),
            ("idents.csv", lambda t: t.replace("boundary,", "pillar,", 1), "kind 'pillar'"),
            ("sensors.csv", lambda t: t.replace(",anchor,", ",signal,", 1), "kind 'signal'"),
            ("masts.csv", lambda t: t.replace(",no,12,", ",maybe,12,", 1), "hidden 'maybe'"),
            ("masts.csv", lambda t: t.replace(",12,17,", ",12,x,", 1), "icon_h 'x'"),
            ("panel.json", lambda t: t.replace('"name": "HART Railroad"', '"name": "Other"', 1), "differs"),
            ("overlay.json", lambda t: t.replace('"kind": "frame"', '"kind": "nowhere"', 1), "anchor kind"),
            ("overlay.json", lambda t: t.replace('sensoricon', 'memoryicon'), "memoryicon"),
            ("overlay.json", lambda t: "[]", "not an object"),
            ("overlay.json", lambda t: t.replace('"dropped"', '"stations"', 1), "fields"),
            ("overlay.json", lambda t: t.replace('"switch_numbers": [', '"switch_numbers": [\n   "1",', 1),
             "dropped switch_numbers"),
            ("overlay.json", lambda t: "\n".join(ln.replace("sensoricon", "BlockContentsIcon")
                                                 if 'sensor=\\"BS Main East\\"' in ln else ln
                                                 for ln in t.split("\n")),
             "gives one per block"),
        ]
        for name, edit, why in cases:
            with self.subTest(file=name, why=why):
                self.assertIn(why, self.broken(name, edit))
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(I.InputsError, "cannot read"):
            I.load(Path(tmp))                               # no frozen files at all


class OverlayErrors(unittest.TestCase):
    """The overlay stops with its own error, naming the item, on what it cannot carry."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ov = T._load("le_overlay", T.ROOT / "tools/schematic/le_overlay.py")
        with contextlib.redirect_stdout(io.StringIO()):
            _sheet, cls.le_mod, _core = B.plugin()      # the plugin's font sizes (schematic.jmri_text) on the path
        cls.slots = B.slots_module()

    LAMP = ('<sensoricon sensor="BS W" x="{x}" y="{y}" level="10"><active url="program:resources/icons/'
            'smallschematics/tracksegments/circuit-empty.gif"/></sensoricon>')
    MARKER = ('<sensoricon sensor="MoveToTrack_{b}_stored" x="{x}" y="{y}" level="12" text="{b}" size="10" '
              'style="1"><active url="program:resources/icons/markers/loco-red.gif"/></sensoricon>')

    def panel(self, *extra: str) -> ET.Element:
        """two_block_panel (blocks W, E, OS, B, C along y = 0 and 60) as a written panel, with `extra` items."""
        le = two_block_panel()
        le.set("panelwidth", "400")
        le.set("panelheight", "200")
        for x in extra:
            le.append(ET.fromstring(x))
        return le

    def frozen(self, *items: tuple) -> dict:
        """A frozen overlay of (xml, group, anchor) items."""
        return {"frame": [0.0, 0.0, 300.0, 60.0], "dropped": {k: [] for k in self.ov.DROPPED}, "unchained": [],
                "items": [dict(index=i, xml=x, group=g, anchor=a) for i, (x, g, a) in enumerate(items)]}

    def test_text_is_sized_as_jmri_draws_it(self) -> None:
        ov = self.ov
        jt = B.importlib.import_module("schematic.jmri_text")
        label = ov.Item(ET.fromstring('<positionablelabel text="Industries" x="1" y="2" size="16" style="1"/>'), 0)
        self.assertEqual(label.size, (jt.width("Industries", 16, True), jt.height(16, True)))
        marker = ov.Item(ET.fromstring(self.MARKER.format(b="EH-2", x=0, y=0)), 0)
        self.assertEqual(marker.size, (max(60, jt.width("EH-2", 10, True)), max(20, jt.height(10, True))))  # fits
        bci = ET.fromstring('<BlockContentsIcon blockcontents="W" x="3" y="4" size="13" style="0"/>')
        (kind, name, r), = ov.generated([bci])
        self.assertEqual((kind, name, r.w), ("block contents", "W", jt.width(ov.bci_text(), 13)))
        hidden = ET.fromstring('<positionablelabel text="marker" hidden="yes" x="2" y="2" size="9"/>')
        self.assertEqual(ov.generated([hidden]), [])        # not drawn on the running panel
        with self.assertRaisesRegex(ov.OverlayError, "font size 40"):
            ov.Item(ET.fromstring('<positionablelabel text="A" x="1" y="2" size="40"/>'), 0).size

    def test_hand_drawn_labels_the_generator_gives_are_dropped(self) -> None:
        ov = self.ov
        live = ov.Track(self.panel(), self.le_mod, self.slots, "hand-drawn panel")
        gen = ov.generated([ET.fromstring(f'<positionablelabel text="{t}" x="0" y="0" size="10"/>')
                            for t in ("BRICK", "SW-1")])
        items = [ov.Item(ET.fromstring(x), i) for i, x in enumerate((
            '<BlockContentsIcon blockcontents="W" x="3" y="4" size="13"/>',
            '<positionablelabel text="SW-1" x="1" y="2" size="13"/>',
            '<positionablelabel text="SW-35A" x="1" y="2" size="13"/>',     # a lettered number
            '<positionablelabel text="E" x="1" y="2" size="10"/>',          # names block E
            '<positionablelabel text="Brick" x="1" y="2" size="16"/>',
            '<positionablelabel text="116" x="1" y="2" size="13"/>',        # an equipment label, no prefix
            '<positionablelabel text="Industries" x="1" y="2" size="16"/>',
            '<positionablelabel x="0" y="0" level="1"><icon url="program:misc/hart_panel_bg.jpg"/>'
            '</positionablelabel>',
            '<sensoricon sensor="NX Mast 2L" x="1" y="2" level="11"><active url="program:resources/icons/USS/sensor/'
            'green-on.gif"/></sensoricon>',
            '<turnouticon turnout="IT:HART:YL:L1" x="1" y="2" level="10"><closed url="program:resources/icons/'
            'buttons/triangle_x.gif"/></turnouticon>'))]
        # an unblocked segment gives Track.pieces the block "": a label with no text is no track name
        live.pieces[""] = [((0, 0), (1, 0))]
        kept, dropped = ov.split_generated(items, live, gen, "SW-")
        self.assertEqual([it.text for it in kept], ["116", "Industries", None])
        self.assertTrue(kept[-1].backdrop)
        self.assertEqual(dropped, dict(block_contents=["W"], switch_numbers=["1", "35A"], track_names=["E"],
                                       captions=["Brick"], nx_icons=["NX Mast 2L"], ladder_buttons=["IT:HART:YL:L1"]))
        self.assertIsNone(ov.switch_number("SW-1", ""))           # no prefix: nothing is a switch label
        self.assertIsNone(ov.switch_number("SW-1x", "SW-"))
        dropped["switch_numbers"] = ["1"]
        with self.assertRaisesRegex(ov.OverlayError, r"lacks .*track name E, caption 'Brick'"):
            ov.given(dict(dropped, captions=["Brick"]), gen[1:], "carry", "SW-")
        with self.assertRaisesRegex(ov.OverlayError, "lacks .*switch number 1,"):
            ov.given(dropped, gen, "carry")                 # the plugin writes "SW-1": no prefix, no match
        with self.assertRaisesRegex(ov.OverlayError, "block contents icon of OS"):
            ov.given(dict(dropped, block_contents=["W", "OS"], track_names=[]),
                     gen + ov.generated([ET.fromstring('<BlockContentsIcon blockcontents="W" x="3" y="4" '
                                                       'size="13"/>')]), "carry", "SW-")
        notes = ov.given(dict(dropped, track_names=[]), gen, "carry", "SW-")     # no BCI at all: noted, not hidden
        self.assertIn("no block contents icon", notes[0])
        with self.assertRaisesRegex(ov.OverlayError, "re-freeze.*'Brick'"):
            ov.repeats([items[4]], gen)

    def test_a_carried_switch_number_stops(self) -> None:
        ov = self.ov
        frozen = copy.deepcopy(I.load().overlay)
        item = next(it for it in frozen["items"] if 'text="Industries"' in it["xml"])
        item["xml"] = item["xml"].replace('text="Industries"', 'text="SW-3"')
        ov.validate(frozen)                                  # no prefix (le_inputs.load): read as a caption
        with self.assertRaisesRegex(ov.OverlayError, "gives the switch numbers"):
            ov.validate(frozen, switch_prefix="SW-")        # the build's prefix: generated, not carried

    def test_a_carried_item_on_a_generated_bci_is_found(self) -> None:
        ov = self.ov
        lamp = self.LAMP.format(x=40, y=20)
        le = self.panel('<BlockContentsIcon blockcontents="W" x="30" y="15" size="13" style="0"/>', lamp)
        frozen = self.frozen((lamp, None, {"kind": "frame"}))
        bad = ov.check(le, frozen, self.le_mod, self.slots, {})
        self.assertEqual(len(bad), 1)
        self.assertIn("meets ['block contents W']", bad[0])
        # sized as the plugin placed it: a short box (44 px) leaves the lamp at x 80 clear, the full one does not
        le.find("sensoricon").set("x", "80")
        self.assertIn("meets ['block contents W']", ov.check(le, frozen, self.le_mod, self.slots, {})[0])
        self.assertEqual(ov.check(le, frozen, self.le_mod, self.slots, {}, bci_widths={"W": 44.0}), [])
        with self.assertRaisesRegex(ov.OverlayError, "not among the plugin's block contents icons"):
            ov.check(le, frozen, self.le_mod, self.slots, {}, bci_widths={})
        le.find("sensoricon").set("y", "-60")
        self.assertIn("off the panel", ov.check(le, frozen, self.le_mod, self.slots, {})[0])

    def test_station_clusters_go_to_the_plugin_as_extras_and_move_as_one(self) -> None:
        ov = self.ov
        its = [ov.Item(ET.fromstring(self.MARKER.format(b="W", x=520, y=500)), 0),
               ov.Item(ET.fromstring(self.LAMP.format(x=500, y=505)), 1)]
        for it in its:
            it.group = "station W"
        (extra,) = ov.station_extras({"W": its})
        w, h = its[0].x + its[0].w - its[1].x, its[0].h
        self.assertEqual(extra, {"id": "W", "block": "W", "size": [w, h]})
        P = mock.Mock(extras=[dict(id="W", block="W", xy=[30, -25], box=(30, -25, w, h), on_track=False)])
        self.assertEqual(ov.station_shift(its, "W", P), (30 - 500, -25 - 500))     # the box's corner, as one
        P.extras[0]["box"] = (30, -25, w + 1, h)
        with self.assertRaisesRegex(ov.OverlayError, "station cluster W: the plugin placed a"):
            ov.station_shift(its, "W", P)
        with self.assertRaisesRegex(ov.OverlayError, "station cluster Z: the plugin's label layer placed 0 boxes"):
            ov.station_shift(its, "Z", P)

    def test_frozen_and_hand_drawn_clusters_are_the_same(self) -> None:
        ov = self.ov
        panel = tables.layout_editor(tables.read(T.hand()), LIVE)    # the last hand-drawn panel (git)
        frozen = ov.station_clusters(I.load().overlay)
        self.assertEqual(len(frozen), 12)
        live = ov.panel_station_clusters(panel)
        self.assertEqual(ov.station_extras(frozen), ov.station_extras(live))

    def test_a_station_cluster_on_a_carried_item_is_found(self) -> None:
        ov = self.ov
        marker = self.MARKER.format(b="W", x=30, y=-25)
        lamp = self.LAMP.format(x=35, y=-20)
        le = self.panel(marker, lamp)
        frozen = self.frozen((marker, "station W", None), (lamp, None, {"kind": "frame"}))
        bad = ov.check(le, frozen, self.le_mod, self.slots, {})
        self.assertTrue(any("meets" in e and "MoveToTrack_W_stored" in e for e in bad), bad)

    def test_unknown_items_and_images_stop(self) -> None:
        ov = self.ov
        with self.assertRaisesRegex(ov.OverlayError, "memoryicon"):
            ov.overlay_items(ET.fromstring('<LayoutEditor><memoryicon x="1" y="1"/></LayoutEditor>'))
        with self.assertRaisesRegex(ov.OverlayError, "no known size"):
            ov.Item(ET.fromstring('<sensoricon sensor="S" x="1" y="2"><active url="program:x/y.gif"/></sensoricon>'),
                    0)
        with self.assertRaisesRegex(ov.OverlayError, "no number"):
            ov.Item(ET.fromstring('<positionablelabel text="A" x="z" y="2" size="10"/>'), 0)
        with self.assertRaisesRegex(ov.OverlayError, "no text"):
            ov.Item(ET.fromstring('<positionablelabel text=" " x="1" y="2" size="10"/>'), 0)

    def test_nx_icons_and_ladder_buttons_are_left_out(self) -> None:
        ov = self.ov
        nx = ('<sensoricon sensor="NX Mast 2L" x="1" y="2" level="11"><active url="program:resources/icons/USS/sensor/'
              'green-on.gif"/></sensoricon>')
        ladder = ('<turnouticon turnout="IT:HART:YL:L1" x="1" y="2" level="10"><closed url="program:resources/icons/'
                  'buttons/triangle_x.gif"/></turnouticon>')
        self.assertTrue(ov.left_out(ET.fromstring(nx)))
        self.assertTrue(ov.left_out(ET.fromstring(ladder)))
        self.assertFalse(ov.left_out(ET.fromstring(self.LAMP.format(x=1, y=2))))
        for x in (nx, ladder):          # a frozen file holding one stops: a re-freeze leaves them out
            with self.subTest(item=x[:30]), self.assertRaisesRegex(ov.OverlayError, "are not carried"):
                ov.validate(self.frozen((x, None, {"kind": "frame"})))

    def test_the_frame_and_the_room_are_checked(self) -> None:
        ov = self.ov
        track = ov.Track(self.panel(), self.le_mod, self.slots, "panel")
        self.assertEqual(track.box_of(set(track.pieces)), track.box)
        with self.assertRaisesRegex(ov.OverlayError, "none of the frame's 1 blocks is drawn"):
            track.box_of({"Track Nowhere"})
        P = mock.Mock(size=(500, 2000))
        self.assertEqual(ov.room(P, self.le_mod, B.FIT), (B.FIT[0] - self.le_mod.CHROME[0], 2000))
        with self.assertRaisesRegex(ov.OverlayError, "leaves no room"):
            ov.room(P, self.le_mod, (10, 10))

    def test_a_cluster_lamp_by_no_station_stops(self) -> None:
        ov = self.ov
        lamp = ('<sensoricon sensor="BS X" x="500" y="500" level="12"><active url="program:resources/icons/'
                'smallschematics/tracksegments/circuit-empty.gif"/></sensoricon>')
        move = ('<sensoricon sensor="MoveToTrack_X_stored" x="10" y="10" level="12"><active url="program:'
                'resources/icons/markers/loco-red.gif"/></sensoricon>')
        items = [ov.Item(ET.fromstring(lamp), 0), ov.Item(ET.fromstring(move), 1)]
        with self.assertRaisesRegex(ov.OverlayError, "stands by no station cluster"):
            ov.assign_groups(items)

    def test_share_along_a_run_round_trips(self) -> None:
        ov = self.ov
        run, one = ov.chain([((10, 0), (0, 0)), ((10, 0), (30, 10))])
        self.assertTrue(one)
        self.assertEqual(run[0][0], (0, 0))                      # from the left end
        tr = ov.Track.__new__(ov.Track)
        tr.what, tr.runs = "t", {"B": run}
        for p in ((5, -3), (20, 9), (-6, 1), (40, 12)):
            with self.subTest(p=p):
                got = tr.at("B", *tr.where("B", p))
                self.assertAlmostEqual(got[0], p[0])
                self.assertAlmostEqual(got[1], p[1])
        _run, one = ov.chain([((0, 0), (1, 0)), ((5, 5), (6, 5))])
        self.assertFalse(one)                                     # two pieces apart: reported as unchained
        with self.assertRaisesRegex(ov.OverlayError, "no drawn track"):
            tr.where("C", (0, 0))

    def test_a_flat_live_track_stops(self) -> None:
        with self.assertRaisesRegex(self.ov.OverlayError, "spans no height"):
            self.ov.frame_point((5, 5), (0, 3, 10, 3), (0, 0, 10, 10))

    def test_no_clear_spot_stops(self) -> None:
        ov = self.ov
        obstacles = ov.Obstacles.__new__(ov.Obstacles)
        obstacles.grid = ov.defaultdict(list)
        obstacles.add_rect("wall", ov.Rect(-500, -500, 1000, 1000))
        with self.assertRaisesRegex(ov.OverlayError, "no clear spot"):
            ov.nudge([ov.Rect(0, 0, 5, 5)], obstacles, False, (-1000, -1000, 1000, 1000), "item")



class RetiredYardLadder(unittest.TestCase):
    TABLES = """<layout-config>
  <turnouts class="t">
    <turnout><systemName>IT:HART:YL:L1</systemName></turnout>
    <turnout><systemName>M2T308</systemName></turnout>
  </turnouts>
  <routes class="r">
    <route controlTurnout="IT:HART:YL:L1"><systemName>IO:AUTO:0201</systemName>
      <routeOutputTurnout systemName="M2T308" state="CLOSED" /></route>
    <route controlTurnout="IT:OTHER"><systemName>IO:AUTO:0300</systemName>
      <routeOutputTurnout systemName="IT:HART:YL:L2" state="CLOSED" /></route>
    <route controlTurnout="IT:KEEP"><systemName>IO:AUTO:0400</systemName></route>
  </routes>
</layout-config>"""

    def test_the_yard_ladder_turnouts_and_their_routes_go(self) -> None:
        root = ET.fromstring(self.TABLES)
        self.assertEqual(B.retire_yard_ladder(root), 3)
        self.assertEqual([t.findtext("systemName") for t in root.iter("turnout")], ["M2T308"])
        self.assertEqual([r.findtext("systemName") for r in root.iter("route")], ["IO:AUTO:0400"])

    def test_another_reference_left_stops(self) -> None:
        root = ET.fromstring(self.TABLES.replace("IT:KEEP", "IT:KEEP\" comment=\"IT:HART:YL:L3"))
        root.find("routes/route[3]").set("note", "IT:HART:YL:L3")
        with self.assertRaisesRegex(B.BuildError, "yard ladder"):
            B.retire_yard_ladder(root)

    def test_the_released_tables_hold_none(self) -> None:
        self.assertNotIn(B.RETIRED_TURNOUT_PREFIX, Path(B.paths.REPO_TABLES_XML).read_text(encoding="utf-8"))

    def test_a_reference_by_user_name_stops(self) -> None:
        root = ET.fromstring(self.TABLES.replace("<systemName>IT:HART:YL:L1</systemName>",
                                                 "<systemName>IT:HART:YL:L1</systemName><userName>Ladder L1</userName>"))
        root.find("routes/route[3]").set("note", "Ladder L1")
        with self.assertRaisesRegex(B.BuildError, "yard ladder"):
            B.retire_yard_ladder(root)

    def test_the_parked_snapshot_holds_none(self) -> None:
        # the parked features never referred to them, so unparking cannot bring them back
        self.assertNotIn(B.RETIRED_TURNOUT_PREFIX, B.parked.PARKED_XML.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
