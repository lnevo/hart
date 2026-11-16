"""build_layout_le.py --levels staging --as-live: the cut-over candidate, the "HART Railroad" panel replaced by the
generated staging panel (Phases 1 and 2, owner approved 2026-11-15), built from the frozen inputs (Phase 3b).

The candidate must be a drop-in: the same tables but the one panel, the same idents, leg letters and slots, every
mast and Entry/Exit sensor resolving as frozen from the hand-drawn panel, every frozen icon and label carried once,
the audits passing on it. The comparisons read the frozen files (jmri/layouts/hart/data/schematic/staging_le/), not
the panel in tables.xml, so they hold after the cut-over too, when that panel is the generated one; and the
candidate is the same whether the tables hold the hand-drawn panel, a generated one or none.
"""
from __future__ import annotations

import contextlib
import copy
import functools
import io
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_build_layout_le as T  # noqa: E402  loads the builder and the audit once

B, AUDIT = T.B, T.AUDIT
tables, paths = T.tables, T.paths
LIVE = "HART Railroad"
SIZE_ATTRS = {"panelwidth", "panelheight", "windowwidth", "windowheight", "x", "y"}
STATUS = {"sensoricon": {"Bridge HBLOOP", "SML Mode", "Track Power"}, "signalheadicon": {"IH9990"}}


@functools.lru_cache(maxsize=None)
def cutover():
    """(candidate bytes, Panel, names, bands), built once for every test that needs it."""
    with contextlib.redirect_stdout(io.StringIO()):
        return B.build(levels="staging", as_live=True)


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
        cls.live = tables.read(paths.TABLES_XML)
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
        got = {k: v for k, v in self.le.attrib.items() if k not in SIZE_ATTRS}
        want = {k: v for k, v in self.inputs.attrs.items() if k not in SIZE_ATTRS}
        self.assertEqual(got, want)
        self.assertEqual((self.le.get("editable"), self.le.get("scrollable")), ("no", "none"))
        w, h = int(self.le.get("panelwidth")), int(self.le.get("panelheight"))
        self.assertEqual((int(self.le.get("windowwidth")), int(self.le.get("windowheight"))), (w + 18, h + 60))
        self.assertLessEqual(w + 18, B.FIT[0])
        self.assertLessEqual(h + 60, B.FIT[1])

    def test_no_placeholders_in_staging_mode(self) -> None:
        self.assertFalse([t for t in tables.turnouts(self.root) if tables.system_name(t).startswith(B.TURNOUT_SYS)])
        self.assertFalse([b for b in tables.blocks(self.root) if tables.system_name(b).startswith(B.BLOCK_SYS)])
        live_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live)}
        self.assertLessEqual(T.used_blocks(self.le), live_lb)
        self.assertEqual(T.used_blocks(self.le), frozen_blocks(self.inputs))
        self.assertEqual({s.get("hidden") for s in self.le.findall("tracksegment")}, {"no"})     # no helix joins

    def test_as_live_needs_staging_alone(self) -> None:
        with self.assertRaisesRegex(B.BuildError, "staging alone"):
            B.build(levels="all", as_live=True)
        with self.assertRaisesRegex(B.BuildError, "levels must be"):
            B.build(levels="main")

    # ---- Phase 1: idents, leg letters, masts, sensors
    def test_live_idents_and_leg_letters_are_kept(self) -> None:
        gen_t = {t.get("ident"): t for t in self.le.findall("layoutturnout")}
        for t in self.inputs.turnouts:
            with self.subTest(turnout=t["ident"]):
                g = gen_t[t["ident"]]
                for a in ("turnoutname", "type", "blockname", "blockbname", "blockcname", "blockdname"):
                    self.assertEqual(g.get(a), t.get(a), a)
                if "XOVER" not in t["type"]:
                    self.assertEqual(g.get("continuing"), t.get("continuing"))
        self.assertEqual(len(self.inputs.turnouts), 20)
        self.assertEqual(B.turnout_facts(self.le), {**B.turnout_facts(self.le), **self.inputs.turnout_facts()})
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
            live[m["mast"]] = dict(mast=m["mast"], kind=m["kind"], ident=m["ident"], slot=m["slot"],
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
        # the NX sensor beans: the frozen set, each bound once and shown by one icon, as frozen
        nx_beans = {tables.user_name(s) for s in self.root.iter("sensor")
                    if tables.user_name(s).startswith("NX Mast ")}
        self.assertEqual(set(live_slots.values()), nx_beans)
        icons = lambda els: Counter(i.get("sensor") for i in els if i.tag == "sensoricon"      # noqa: E731
                                    and (i.get("sensor") or "").startswith("NX "))
        self.assertEqual(icons(self.le), icons(frozen_items()))
        self.assertEqual(set(icons(self.le)), nx_beans)
        self.assertEqual(set(icons(self.le).values()), {1})
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
        self.assertEqual(audit.warnings, [])
        self.assertEqual(drift, [])
        self.assertEqual(audit.facts["panel"], LIVE)
        self.assertEqual(cli, 0)

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
                self.assertEqual(AUDIT.main(["--strict", "--tables", str(path)]), 0)   # found by its marker
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
        self.assertEqual(ov.check(self.le, self.inputs.overlay, le_mod, self.slots, size), [])
        live_items = frozen_items()
        self.assertEqual(Counter(el.tag for el in live_items), Counter(
            sensoricon=103, BlockContentsIcon=55, positionablelabel=42, turnouticon=10, signalheadicon=1))
        self.assertEqual(len(self.P.overlay["records"]), len(live_items))
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
        self.assertLessEqual({"LCOS", "Turnouts", "Signals", "Track Power", "Neville Island"}, texts)
        self.assertEqual(Counter(i.get("blockcontents") for i in self.le.findall("BlockContentsIcon")),
                         Counter(i.get("blockcontents") for i in frozen_items() if i.tag == "BlockContentsIcon"))
        status = [r for r in self.P.overlay["records"] if r["anchor"] == "group status"]
        self.assertEqual(len(status), 8)
        moves = {(r["new"][0] - r["live"][0], r["new"][1] - r["live"][1]) for r in status}
        self.assertEqual(len(moves), 1, "the status cluster moves as one block")

    def test_generated_duplicates_are_dropped(self) -> None:
        texts = {lb.get("text") for lb in self.le.findall("positionablelabel")}
        self.assertFalse({"BRICK", "SOUTH YARD", "1", "39", "S-R"} & texts)
        self.assertLessEqual({"SW-1", "SW-39", "Brick", "South Yard", "Track S-R"}, texts)

    def test_overlay_report_is_printed(self) -> None:
        lines = B.overlay_lines(self.P.overlay)
        self.assertTrue(lines[0].startswith(f"{len(self.P.overlay['records'])} live items carried"))
        self.assertIn("BRICK", lines[1])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                B, "build", return_value=(self.data, self.P, self.names, self.bands)):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                B.main(["--levels", "staging", "--as-live", "--out", str(Path(tmp) / "c.xml")])
        self.assertIn("  overlay: generated labels dropped", out.getvalue())
        self.assertIn("panel 'HART Railroad'", out.getvalue())

    def test_each_option_set_has_its_own_trial_file(self) -> None:
        self.assertEqual(B.default_out("all", False), B.TRIAL)
        self.assertEqual(B.default_out("staging", False), B.TRIAL_STAGING)
        self.assertEqual(B.default_out("staging", True), B.CUTOVER)
        self.assertEqual(len({B.TRIAL, B.TRIAL_STAGING, B.CUTOVER}), 3)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(B, "TRIAL_STAGING", Path(tmp) / "s.xml"), \
                mock.patch.object(B, "TRIAL", Path(tmp) / "a.xml"), \
                mock.patch.object(B, "build", return_value=(self.data, self.P, self.names, self.bands)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["--levels", "staging"]), 0)
                self.assertEqual(B.main(["--levels", "staging", "--check"]), 0)
                self.assertEqual(B.main(["--check"]), 1)          # the all-levels trial is another file
            self.assertTrue((Path(tmp) / "s.xml").exists())
            self.assertFalse((Path(tmp) / "a.xml").exists())

    def test_check_mode_and_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                B, "build", return_value=(self.data, self.P, self.names, self.bands)) as built:
            out = Path(tmp) / "c.xml"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["--levels", "staging", "--as-live", "--out", str(out)]), 0)
                self.assertEqual(B.main(["--levels", "staging", "--as-live", "--check", "--out", str(out)]), 0)
            built.assert_called_with(levels="staging", as_live=True)
        self.assertEqual(B.CUTOVER.parent, B.TRIAL.parent)                 # gitignored trial folder


class Rebuilt(unittest.TestCase):
    """Phase 3b: the candidate is built from the frozen files and the schematic alone. Built from tables with no
    "HART Railroad" panel, or from the candidate itself (after the cut-over tables.xml holds the generated panel), it
    is the same file byte for byte."""

    def build_from(self, data: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(data)
            with contextlib.redirect_stdout(io.StringIO()):
                return B.build(path, levels="staging", as_live=True)[0]

    def test_without_the_hand_drawn_panel(self) -> None:
        data = cutover()[0]
        bare = without_live_panel(paths.TABLES_XML.read_bytes())
        self.assertIsNone(tables.layout_editor(tables.loads(bare).root, LIVE))
        self.assertEqual(self.build_from(bare), data)

    def test_after_the_cut_over(self) -> None:
        data = cutover()[0]
        self.assertEqual(self.build_from(data), data)


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

        def fake_build(_path, levels, as_live, inputs, freeze_from=None):      # the two builds, without drawing
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
                B.freeze(paths.TABLES_XML, folder)
            self.assertEqual([p.name for p in folder.iterdir()], ["kept.txt"])     # untouched
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["staging_le"])   # nothing left beside
            rebuilt = b"from the panel"
            with mock.patch.object(B, "build", side_effect=fake_build):
                written = B.freeze(paths.TABLES_XML, folder)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), sorted(p.name for p in I.FOLDER.iterdir()))
            self.assertEqual(sorted(written), sorted(folder / p.name for p in I.FOLDER.iterdir()))
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["staging_le"])
            for p in I.FOLDER.iterdir():
                if p.name != "panel.json":                  # its note names today's date: compare the rest
                    self.assertEqual((folder / p.name).read_text().split("\n", 1)[1],
                                     p.read_text().split("\n", 1)[1], p.name)

    def test_freezing_refuses_a_generated_panel(self) -> None:
        doc = tables.load(paths.REPO_TABLES_XML)
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
        B.check_live_turnouts(two_block_panel(), frozen)
        with self.assertRaisesRegex(B.BuildError, "type: live RH_TURNOUT, new LH_TURNOUT"):
            B.check_live_turnouts(two_block_panel(turnout_type="LH_TURNOUT"), frozen)
        gen = two_block_panel()
        t = gen.find("layoutturnout")
        t.set("connectbname", "T4")
        t.set("connectcname", "T3")
        with self.assertRaisesRegex(B.BuildError, "legs"):
            B.check_live_turnouts(gen, frozen)


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
                         (20, 35, 17, 7, 26, 23, 49, 211))
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

    def test_moving_the_panel_down_moves_bezier_control_points(self) -> None:
        ov = self.ov
        le = ET.fromstring('<LayoutEditor><tracksegment ident="T1" bezier="yes"><controlpoints>'
                           '<controlpoint index="0" x="5" y="10"/></controlpoints></tracksegment>'
                           '<positionablepoint ident="A1" x="1" y="2"/></LayoutEditor>')
        ov.shift_panel(le, 7)
        self.assertEqual(le.find(".//controlpoint").get("y"), "17.0")
        self.assertEqual(le.find(".//controlpoint").get("x"), "5")
        self.assertEqual(le.find("positionablepoint").get("y"), "9.0")

    def test_a_flat_live_track_stops(self) -> None:
        with self.assertRaisesRegex(self.ov.OverlayError, "spans no height"):
            self.ov.frame_point((5, 5), (0, 3, 10, 3), (0, 0, 10, 10))

    def test_no_clear_spot_stops(self) -> None:
        ov = self.ov
        obstacles = ov.Obstacles.__new__(ov.Obstacles)
        obstacles.grid = ov.defaultdict(list)
        obstacles.add_rect("wall", ov.Rect(-500, -500, 1000, 1000))
        with self.assertRaisesRegex(ov.OverlayError, "no clear spot"):
            ov.nudge([ov.Rect(0, 0, 5, 5)], obstacles, False, (-1000, 1000), "item")


if __name__ == "__main__":
    unittest.main()
