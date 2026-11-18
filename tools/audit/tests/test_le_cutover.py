"""build_layout_le.py --levels staging --as-live: the cut-over candidate, the "HART Railroad" panel replaced by the
generated staging panel, built from the staging device map and panel_items.json (the device-map switch-over, owner
2026-11-17).

The candidate must be a drop-in: the same tables but the one panel, every staging turnout with the last hand-drawn
panel's turnout, ident, type, continuing route and leg blocks, every mast resolving to the same blocks from the same
kind of slot, the panel's own items (panel_items.json) each once, no Entry/Exit sensor (parked), and the audits passing
on it. The comparisons read the last hand-drawn tables from git (hartlib.hand_drawn) and the staging device map, not
the panel in tables.xml.
"""
from __future__ import annotations

import contextlib
import copy
import functools
import importlib
import io
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
PARKED_LAMPS = paths.LAYOUT_DATA.parent / "parked" / "staging_panel_lamps.json"


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


def without_live_panel(data: bytes) -> bytes:
    doc = tables.loads(data)
    le = tables.layout_editor(doc.root, LIVE)
    idx = list(doc.root).index(le)
    doc.root[idx - 1].tail = le.tail
    doc.root.remove(le)
    return doc.tobytes()


def swap_legs(facts: dict) -> dict:
    """A turnout's facts (B.turnout_facts) with legs B and C swapped, as B.LEGS_SWAPPED draws Switch 13: the other
    hand and the continuing route on the other letter."""
    legs = dict(facts["legs"])
    legs["B"], legs["C"] = facts["legs"].get("C"), facts["legs"].get("B")
    a, b, c, d = facts["blocks"]
    hand = {"RH_TURNOUT": "LH_TURNOUT", "LH_TURNOUT": "RH_TURNOUT"}
    return dict(facts, legs={k: v for k, v in legs.items() if v is not None}, blocks=(a, c, b, d),
                type=hand.get(facts["type"], facts["type"]),
                continuing={"2": "4", "4": "2"}.get(facts["continuing"], facts["continuing"]))


def item_elements(data: dict) -> list[ET.Element]:
    """The elements of a panel items file (panel_items.json), in order."""
    return [ET.fromstring(m["xml"]) for it in data["items"] for m in (it.get("members") or [it])]


class Cutover(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.P, cls.names, cls.bands = cutover()
        cls.root = tables.loads(cls.data).root
        cls.live = tables.read(T.hand())
        cls.le = tables.layout_editor(cls.root, LIVE)
        cls.hand_le = tables.layout_editor(cls.live, LIVE)          # the last hand-drawn panel: the railroad
        cls.items = B.panel_items.load(B.PANEL_ITEMS)
        cls.slots = B.slots_module()

    # ---- the same tables but the panel
    def test_only_the_panel_changes(self) -> None:
        self.assertEqual(without_panel(self.root), without_panel(self.live))
        self.assertEqual([le.get("name") for le in tables.layout_editors(self.root)],
                         [le.get("name") for le in tables.layout_editors(self.live)])
        self.assertEqual(list(self.root).index(self.le), list(self.live).index(tables.layout_editor(self.live, LIVE)))

    def test_live_panel_attributes_fit_sizing(self) -> None:
        got = {k: v for k, v in self.le.attrib.items() if k not in SIZE_ATTRS | {"scrollable", "name", "class"}}
        want = {k: v for k, v in self.items["attributes"].items() if k not in SIZE_ATTRS | {"scrollable"}}
        self.assertEqual(got, want)
        # larger than its window, so it scrolls both ways (the file's attribute, for a panel that fits, is "none")
        self.assertEqual((self.le.get("editable"), self.le.get("scrollable")), ("no", "both"))
        self.assertEqual(self.items["attributes"]["scrollable"], "none")
        w, h = int(self.le.get("panelwidth")), int(self.le.get("panelheight"))
        # the window is the panel and its frame, at most FIT; the stretched panel (le_stretch) is wider than it
        self.assertEqual((int(self.le.get("windowwidth")), int(self.le.get("windowheight"))),
                         (min(w + 18, T.le_window()[0]), min(h + 60, T.le_window()[1])))
        self.assertEqual(self.P.scale, (self.P.staging_fit[0] * stretch()[0], self.P.staging_fit[1]))
        self.assertTrue(0.7 < self.P.staging_fit[0] < 0.9, self.P.staging_fit)     # staging's own fit to FIT

    def test_no_placeholders_in_staging_mode(self) -> None:
        self.assertFalse([t for t in tables.turnouts(self.root) if tables.system_name(t).startswith(B.TURNOUT_SYS)])
        self.assertFalse([b for b in tables.blocks(self.root) if tables.system_name(b).startswith(B.BLOCK_SYS)])
        live_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live)}
        self.assertLessEqual(T.used_blocks(self.le), live_lb)
        self.assertEqual(T.used_blocks(self.le), T.used_blocks(self.hand_le))
        self.assertEqual({s.get("hidden") for s in self.le.findall("tracksegment")}, {"no"})     # no helix joins

    def test_levels_are_checked(self) -> None:
        with self.assertRaisesRegex(B.BuildError, "levels must be"):
            B.build(levels="main")

    # ---- turnouts and masts as on the hand-drawn panel
    def test_turnouts_keep_their_live_facts(self) -> None:
        live = B.turnout_facts(self.hand_le)
        live = {i: swap_legs(f) if i in B.swapped_idents() else f for i, f in live.items()}
        self.assertEqual(len(live), 20)
        self.assertEqual(B.turnout_facts(self.le), live)          # ident, name, type, continuing, leg blocks
        self.assertEqual(B.swapped_idents(), {"TO1"})
        idents = {r["le_ident"] for r in B.read_csv(B.SWITCHES)}
        self.assertEqual({t.get("ident") for t in self.le.findall("layoutturnout")}, idents)

    def test_every_mast_resolves_exactly_as_live(self) -> None:
        key = lambda m: (m["kind"], m["facing"], list(m["protects"]), m.get("turnout"))      # noqa: E731
        live = {m["mast"]: key(m) for m in self.slots.Index(self.hand_le).masts()}
        gen = {m["mast"]: key(m) for m in self.slots.Index(self.le).masts()}
        facts = {n: key(f) for n, f in B.sdm.mast_facts().items()}
        self.assertEqual(len(live), 49)
        self.assertEqual(gen, live)                    # kind, blocks and turnout: what discovery reads
        self.assertEqual(gen, facts)                   # and what staging_masts.csv says
        self.assertEqual(self.P.moved, [])             # no helix-entrance exception in staging mode
        self.assertEqual(self.P.unplaced, [])

    def test_no_entry_exit_sensor_icon_or_ladder_button(self) -> None:
        # Entry/Exit is parked (hartlib.parked): no NX sensor in any slot, no NX icon, no yard ladder button
        slots = [el for el in self.le.iter() if (el.tag.startswith("sensor") and el.tag[-1:] in "ABCD"
                                                 and el.tag != "sensoricon")
                 or any(k.endswith("boundsensor") for k in el.attrib)]
        self.assertEqual(slots, [])
        self.assertFalse([i for i in self.le.iter("sensoricon") if (i.get("sensor") or "").startswith("NX ")])
        self.assertFalse([i for i in self.le.iter("turnouticon") if (i.get("turnout") or "").startswith("IT:HART:YL:")])

    def test_audit_passes_strict_on_the_candidate(self) -> None:
        boundaries = AUDIT.load_boundaries(AUDIT.BOUNDARIES)        # the live contract
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables_cutover.xml"
            path.write_bytes(self.data)
            audit = AUDIT.audit_source("deployment", path, boundaries, {b.mast for b in boundaries},
                                       generated=True)
            drift = AUDIT.report_drift([audit])
            with contextlib.redirect_stdout(io.StringIO()):
                cli = AUDIT.main(["--strict", "--tables", str(path), "--generated"])
        # the staging candidate is built on the last hand-drawn tables, whose Dispatcher System is not parked: its
        # station icons are parked with the lamps (jmri/layouts/hart/parked/staging_panel_lamps.json)
        self.assertEqual([e for e in audit.errors if "Dispatcher station sensor icons" not in e], [])
        self.assertTrue(all("run Stage 1" in w for w in audit.warnings), audit.warnings)
        self.assertEqual(drift, [])
        self.assertEqual(audit.facts["panel"], LIVE)
        self.assertEqual(cli, 1)

    # ---- the scripts that run on tables.xml
    def test_the_candidate_carries_one_generated_panel_marker(self) -> None:
        self.assertTrue(tables.generated_panel(self.le))
        self.assertFalse([el for el in item_elements(self.items) if el.get("text") == tables.GENERATED_PANEL_MARKER])
        self.assertEqual(1, sum(lb.get("text") == tables.GENERATED_PANEL_MARKER
                                for lb in self.root.iter("positionablelabel")))

    def test_polish_and_facts_leave_the_candidate_as_built(self) -> None:
        polish = T._load("polish_hart_layout_editor", paths.LAYOUT_SCRIPTS / "polish_hart_layout_editor.py")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(self.data)
            with contextlib.redirect_stdout(io.StringIO()):
                for fn in (polish.apply_visual_standard, polish.apply_overlap_cleanup,
                           polish.apply_block_labels_only):
                    self.assertEqual(fn(path, check=True)[1], [], fn.__name__)
                    fn(path, check=False, reference=path)
            self.assertEqual(path.read_bytes(), self.data)

    # ---- the panel's own items (panel_items.json)
    def test_every_panel_item_once(self) -> None:
        want = Counter(B.canon(el) for el in item_elements(self.items))
        got = Counter()
        for el in self.le:
            if el.tag in B.panel_items.TAGS and el.get("x") is not None:
                c = copy.deepcopy(el)
                c.attrib.pop("x")
                c.attrib.pop("y")
                c.tail = None
                got[B.canon(c)] += 1
        self.assertEqual(want - got, Counter())               # each item there, attributes as the file has them
        self.assertEqual(len(item_elements(self.items)), 14)
        self.assertEqual(self.P.items["count"], 14)

    def test_what_panel_status_and_signal_coordinator_look_up(self) -> None:
        for tag, names in STATUS.items():
            attr = "sensor" if tag == "sensoricon" else "signalhead"
            got = Counter(i.get(attr) for i in self.le.findall(tag) if i.get(attr) in names)
            self.assertEqual(set(got), names)
            self.assertEqual(set(got.values()), {1})
        texts = {lb.get("text") for lb in self.le.findall("positionablelabel")}
        self.assertLessEqual({"LCOS", "Turnouts", "Signals", "Track Power", "HART RAILROAD"}, texts)
        self.assertNotIn("Neville Island", texts)
        bcis = Counter(i.get("blockcontents") for i in self.le.findall("BlockContentsIcon"))
        self.assertEqual(set(bcis.values()), {1})              # one block contents icon per block
        self.assertEqual(set(bcis), T.used_blocks(self.le))
        # the lamps and station clusters are parked: only the status cluster's sensor icons are on the panel
        self.assertEqual({i.get("sensor") for i in self.le.findall("sensoricon")}, STATUS["sensoricon"])

    def test_generated_labels(self) -> None:
        texts = Counter(lb.get("text") for lb in self.le.findall("positionablelabel"))
        prefix = B.LE_LABELS["switch_prefix"]
        for r in B.read_csv(B.SWITCHES):
            self.assertEqual(texts[prefix + r["switch"]], 1, f"switch {r['switch']}: one number")
        self.assertIn("S-R", texts)
        self.assertNotIn("Track S-R", texts)
        lower = Counter(t.lower() for t in texts if t)
        for caption in ("Brick", "South Yard", "Princess"):
            with self.subTest(caption=caption):
                self.assertGreaterEqual(lower[caption.lower()], 1)         # the plugin's station caption

    def test_the_run_reports_the_panel_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
                B, "build", return_value=(self.data, self.P, self.names, self.bands)):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                B.main(["--levels", "staging", "--as-live", "--out", str(Path(tmp) / "c.xml")])
        self.assertIn("  panel items: 14 elements from", out.getvalue())
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
        P = mock.Mock(staging_data=b"staging", log=[], mast_notes=[], moved=[], items=None, staging_same=["x"],
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

    def test_staging_is_the_staging_candidate_joined_at_the_helix(self) -> None:
        # JOIN_HELIX on (owner, 2026-11-17, the helix-join release): staging as in its candidate but for the two
        # helix joins, the only difference the guard accepts (the helix bumpers become anchors, their tracks run on)
        self.assertTrue(B.JOIN_HELIX)
        self.assertEqual(self.P.staging_same, [
            "end bumper EBG1 -> anchor AGE1 (hidden join TG224 to Track 135-H2, Mast 38RA)",
            "end bumper EBG2 -> anchor AGE2 (hidden join TG225 to Track 135-H1, Mast 40RA)",
            "track segment TG6 connect2name EBG2 -> AGE2",
            "track segment TG32 connect2name EBG1 -> AGE1"])
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
                    B.check_staging_unchanged(self.base, doc.tobytes(), self.P, LIVE, B.JOIN_HELIX)

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
            with self.assertRaisesRegex(B.ApprovalError, r"child \d+ is positionablelabel STAGING LEVEL, approved "
                                                         r"positionablelabel STAGING LEVEL \(changed\)"):
                B.check_approved(moved, path)
            fewer = copy.deepcopy(le)
            fewer.remove(fewer[-1])
            with self.assertRaisesRegex(B.ApprovalError, "not the one the owner approved"):
                B.check_approved(fewer, path)
            # the build itself refuses a staging panel that is not the approved one, unless asked to (--review)
            with mock.patch.object(B, "check_approved", side_effect=B.ApprovalError("not approved")) as check, \
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
            with self.assertRaisesRegex(B.ApprovalError, "not the one the owner approved"):
                B.check_approved(le, path)
            path.write_text("# note\nnot a hash\n")
            with self.assertRaisesRegex(B.ApprovalError, "line 2: not"):
                B.check_approved(le, path)
            with self.assertRaisesRegex(B.ApprovalError, "--approve-staging"):
                B.check_approved(le, Path(tmp) / "none")

    def test_the_panel_has_the_windows_shape(self) -> None:
        w, h = int(self.le.get("panelwidth")), int(self.le.get("panelheight"))
        want = (T.le_window()[0] - 18) / (T.le_window()[1] - 60)
        self.assertLessEqual(abs(w / h / want - 1), stretch()[1])
        self.assertEqual((self.le.get("windowwidth"), self.le.get("windowheight")), tuple(map(str, T.le_window())))
        with self.assertRaisesRegex(B.plugin()[2].SchematicError, r"set le_stretch's factor to about 1\.\d+"):
            B.plugin()[1].check_stretch((1984, 1505), T.le_window(), page_prefs())

    def test_no_compass_rose_and_the_plain_backdrop(self) -> None:
        urls = [el.find("icon").get("url") for el in self.le.iter("positionablelabel") if el.find("icon") is not None]
        self.assertEqual([u for u in urls if "hart_panel" in u], ["preference:resources/misc/hart_panel_bg_plain.jpg"])
        self.assertTrue((T.ROOT / "jmri/resources/misc/hart_panel_bg_plain.jpg").exists())
        # the backdrop is panel_items.json's: the plain picture, at the panel's corner
        backdrop = next(it for it in B.panel_items.load(B.PANEL_ITEMS)["items"] if it["id"] == "backdrop")
        self.assertIn("hart_panel_bg_plain.jpg", backdrop["xml"])
        self.assertEqual(backdrop["anchor"]["to"], "origin")

    def test_the_status_cluster_stands_between_staging_and_main(self) -> None:
        def box(el):
            return int(el.get("x")), int(el.get("y"))
        status = {"LCOS", "Turnouts", "Signals", "Track Power", "Bridge HBLOOP", "SML Mode", "IH9990"}
        rows = {}
        for el in self.le:
            name = el.get("text") if el.tag == "positionablelabel" else (el.get("sensor") or el.get("signalhead"))
            if el.get("level") == "10" and name in status:
                rows.setdefault(el.tag == "positionablelabel", []).append(el)
        captions, lamps = rows[True], rows[False]
        self.assertEqual((len(captions), len(lamps)), (4, 4))
        B.plugin()
        jt = importlib.import_module("schematic.jmri_text")
        rights = {box(c)[0] + jt.width(c.get("text"), 12) for c in captions}
        self.assertEqual(len(rights), 1)                    # right-justified ...
        self.assertTrue(all(c.get("justification") == "right" for c in captions))
        self.assertEqual(len({box(l)[0] for l in lamps}), 1)                     # ... lamps in a column beside them
        self.assertGreater(min(box(l)[0] for l in lamps), rights.pop())
        right = max(box(l)[0] + 21 for l in lamps)          # the lamps' right edge: by the panel's right edge
        width = int(tables.layout_editor(tables.loads(self.base[0]).root, LIVE).get("panelwidth"))
        self.assertLessEqual(right, width - B.panel_items.EDGE)
        self.assertGreater(right, width - B.panel_items.EDGE - 80)
        staging_low = self.P.band_boxes[0][3]
        main_title = next(lb for lb in self.P.labels if lb["text"] == "MAIN LEVEL")
        for el in captions + lamps:
            self.assertGreater(box(el)[1], staging_low - 40)                          # in the gap ...
            self.assertLess(box(el)[1] + 20, main_title["box"][1])                    # ... above the main level

    def test_the_gaps_between_levels_are_as_small_as_is_clean(self) -> None:
        self.assertEqual(len(self.P.gaps), 2)
        boxes = self.P.band_boxes
        for i, gap in enumerate(self.P.gaps):
            self.assertAlmostEqual(boxes[i + 1][1] - boxes[i][3], gap)
        titles = [lb for lb in self.P.labels if lb.get("kind") == "title"][1:]
        extent = B.plugin()[1].extent
        lows = [max(extent(self.P, 0)[3], self.base[1].items["bottom"]), extent(self.P, 1)[3]]
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
        jt = importlib.import_module("schematic.jmri_text")
        centres = {round(int(el.get("x")) + jt.width(el.get("text"), int(el.get("size")), False) / 2)
                   for el in self.le.iter("positionablelabel") if el.get("text") in B.NAME_COLUMNS[0]}
        self.assertLessEqual(max(centres) - min(centres), 1, centres)
        # the engine house's buttons step alike, and West Yard's W-2 follows W-1 one row down at that step: kept
        # so in the parked station clusters (staging's le_labels extra_steps and extra_follow place them again when
        # the Dispatcher System is unparked and its clusters go back to the plugin as extras)
        parked_items = B.panel_items.load(PARKED_LAMPS)
        whole, blocks = B.panel_items.drawn_boxes(self.le, B.plugin()[1], B.slots_module(),
                                                  frame_blocks=T.used_blocks(tables.layout_editor(
                                                      tables.loads(self.base[0]).root, LIVE)))
        at = {}
        for it in parked_items["items"]:
            el = ET.fromstring(it["xml"])
            if (el.get("sensor") or "").startswith("MoveToTrack_"):
                at[el.get("sensor")] = B.panel_items.anchor_point(it["anchor"], whole, blocks, it["id"])
        button = lambda n: at[f"MoveToTrack_{n}_stored"]       # noqa: E731
        xs = [round(button(f"EH-{n}")[0]) for n in (1, 2, 3)]
        self.assertEqual(xs[2] - xs[1], xs[1] - xs[0])
        w1, w2 = button("W-1"), button("W-2")
        rows = (w2[1] - w1[1]) / (button("EH-2")[1] - button("EH-1")[1])
        self.assertAlmostEqual(w2[0] - w1[0], rows * (xs[1] - xs[0]), delta=1)
        self.assertLess(w2[0], w1[0])
        # the title is HART RAILROAD (panel_items.json), not the hand-drawn panel's Neville Island
        texts = {el.get("text") for el in self.le.iter("positionablelabel")}
        self.assertIn("HART RAILROAD", texts)
        self.assertNotIn("Neville Island", texts)
        # each OS lamp of a plain switch centred in its control circle, as parked
        own = {t.get("blockname"): t for t in self.le.findall("layoutturnout") if "XOVER" not in t.get("type")}
        lamps = [it for it in parked_items["items"] if it["id"].startswith("lamp ") and it["anchor"]["block"] in own]
        self.assertGreaterEqual(len(lamps), 15)
        for it in lamps:
            t = own[it["anchor"]["block"]]
            x, y = B.panel_items.anchor_point(it["anchor"], whole, blocks, it["id"])
            self.assertLessEqual(math.dist((round(x) + 5, round(y) + 5), (float(t.get("xcen")), float(t.get("ycen")))),
                                 1.5, it["id"])
        self.assertEqual(self.base[1].extra_x, {})            # no caller's items: the station clusters are parked

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
        # the OS lamps are parked with the Dispatcher System (owner, 2026-11-17): none on the panel, and the parked
        # file keeps one for every half of a single crossover, each anchored to its half's own OS block
        self.assertFalse([el for el in self.le.iter("sensoricon") if (el.get("sensor") or "").startswith("BS ")])
        lamps = {it["anchor"]["block"] for it in B.panel_items.load(PARKED_LAMPS)["items"]
                 if it["id"].startswith("lamp ")}
        for name in ("Switch 7", "Switch 23", "Switch 35"):
            t = xo[name]
            self.assertLessEqual({t.get("blockname"), t.get("blockcname")}, lamps, name)
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
        # parked with the Dispatcher System: none on the candidate, all 12 in the parked lamps file
        self.assertIn("dispatcher", B.PARKED)
        self.assertFalse([el for el in self.le.iter("sensoricon") if (el.get("sensor") or "").startswith("Move")])
        buttons = [ET.fromstring(it["xml"]) for it in B.panel_items.load(PARKED_LAMPS)["items"]
                   if "MoveTo" in it["xml"]]
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
        self.assertGreater(h, T.le_window()[1])
        self.assertLessEqual(int(self.le.get("windowwidth")), T.le_window()[0])
        self.assertLessEqual(int(self.le.get("windowheight")), T.le_window()[1])
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
                self.assertEqual(stations.main(["--panel", str(path), "--check", "--no-sync"]), 0)   # parked: skips
                self.assertEqual(AUDIT.main(["--tables", str(path)]), 0)   # --strict waits for Stage 1
                self.assertEqual(facts.main(["--tables", str(path)]), 0)
            self.assertEqual(path.read_bytes(), self.data)


class Rebuilt(unittest.TestCase):
    """The candidate is built from the staging device map and the schematic alone. Built from tables with no
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


class BuilderErrors(unittest.TestCase):
    """The cut-over helpers stop with BuildError, naming what is at fault."""

    def test_the_checkout_tables_are_refused_whatever_hart_tables_says(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(B.paths, "TABLES_XML", Path(tmp) / "c.xml"):
            self.assertTrue(B.live_target(paths.REPO_TABLES_XML))
            self.assertTrue(B.live_target(Path(tmp) / "c.xml"))
            self.assertFalse(B.live_target(Path(tmp) / "other.xml"))

    def test_generated_audit_needs_a_candidate(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(AUDIT.main(["--generated"]), 2)
        self.assertIn("--tables", out.getvalue())


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
