"""build_layout_le.py --levels staging --as-live: the cut-over candidate, the "HART Railroad" panel replaced by the
generated staging panel, built from the staging device map and panel_items.json (the device-map switch-over, owner
2026-11-17).

The candidate must be a drop-in: the tables it is built on (this checkout's tables.xml less what an earlier build
added, strip_build_owned) but the one panel, every staging turnout as the live panel in tables.xml has it (ident,
name, type, continuing route and leg blocks), every mast resolving to the blocks and kind of slot staging_masts.csv gives it, the panel's own items
(panel_items.json) each once, no Entry/Exit sensor (parked), and the audits passing on it.
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
        return B.build(T.TABLES, levels="staging", as_live=True, approved=None)     # the fingerprint: its own test


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


def item_elements(data: dict) -> list[ET.Element]:
    """The elements of a panel items file (panel_items.json), in order."""
    return [ET.fromstring(m["xml"]) for it in data["items"] for m in (it.get("members") or [it])]



# South Yard's tracks, whose names stand on one centre x (staging.preferences.json le_labels name_columns)
SOUTH_YARD = ("S-R", "S-1", "S-2", "S-3", "S-4")

class Cutover(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data, cls.P, cls.names, cls.bands = cutover()
        cls.root = tables.loads(cls.data).root
        cls.live = T.stripped()                                     # the tables the build draws on
        cls.le = tables.layout_editor(cls.root, LIVE)
        cls.live_le = tables.layout_editor(tables.read(paths.REPO_TABLES_XML), LIVE)     # the live generated panel
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
        # the window is the panel and its frame, at most the le_window; the stretched panel (le_stretch) is wider than it
        self.assertEqual((int(self.le.get("windowwidth")), int(self.le.get("windowheight"))),
                         (min(w + 18, T.le_window()[0]), min(h + 60, T.le_window()[1])))
        self.assertEqual(self.P.scale, (self.P.staging_fit[0] * stretch()[0], self.P.staging_fit[1]))
        self.assertTrue(0.7 < self.P.staging_fit[0] < 0.9, self.P.staging_fit)     # staging's own fit to le_window

    def test_no_placeholders_in_staging_mode(self) -> None:
        self.assertFalse([t for t in tables.turnouts(self.root) if tables.system_name(t).startswith(B.TURNOUT_SYS)])
        self.assertFalse([b for b in tables.blocks(self.root) if tables.system_name(b).startswith(B.BLOCK_SYS)])
        live_lb = {tables.user_name(b) for b in tables.layout_blocks(self.live)}
        self.assertLessEqual(T.used_blocks(self.le), live_lb)
        staging = set(self.names[B.STAGING]["os"].values()) | {
            b for v in self.names[B.STAGING]["blocks"].values() for b in v}
        self.assertEqual(T.used_blocks(self.le), staging)          # the staging device map's blocks, all drawn
        self.assertEqual({s.get("hidden") for s in self.le.findall("tracksegment")}, {"no"})     # no helix joins

    def test_levels_are_checked(self) -> None:
        with self.assertRaisesRegex(B.BuildError, "levels must be"):
            B.build(levels="main")

    # ---- turnouts and masts as the live panel and the staging facts have them
    def test_turnouts_keep_their_live_facts(self) -> None:
        idents = {sw.le_ident for sw in B.staging_switches().values()}
        self.assertEqual({t.get("ident") for t in self.le.findall("layoutturnout")}, idents)
        live = {i: f for i, f in B.turnout_facts(self.live_le).items() if i in idents}
        self.assertEqual(len(live), 20)
        self.assertEqual(B.turnout_facts(self.le), live)          # ident, name, type, continuing, leg blocks

    def test_every_mast_resolves_exactly_as_staging_masts_says(self) -> None:
        key = lambda m: (m["kind"], m["facing"], list(m["protects"]), m.get("turnout"))      # noqa: E731
        gen = {m["mast"]: key(m) for m in self.slots.Index(self.le).masts()}
        facts = {n: key(f) for n, f in B.sdm.mast_facts().items()}
        self.assertEqual(len(facts), 30)
        self.assertEqual(gen, facts)                   # kind, blocks and turnout: what discovery reads
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
        self.assertEqual(audit.errors, [])
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
        self.assertEqual(len(item_elements(self.items)), 15)          # the compass back (owner, 2026-11-18)
        self.assertEqual(self.P.items["count"], 15)

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
        prefix = page_prefs()["le_labels"]["switch_prefix"]
        for n in B.staging_switches():
            self.assertEqual(texts[f"{prefix}{n}"], 1, f"switch {n}: one number")
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
        self.assertIn("  panel items: 15 elements from", out.getvalue())
        self.assertIn("panel 'HART Railroad'", out.getvalue())

    def test_each_level_set_has_its_own_candidate_file(self) -> None:
        self.assertEqual(B.default_out("staging"), B.CUTOVER_STAGING)
        self.assertEqual(B.default_out("all"), B.CUTOVER)
        self.assertNotEqual(B.CUTOVER, B.CUTOVER_STAGING)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(B, "CUTOVER_STAGING", Path(tmp) / "s.xml"), \
                mock.patch.object(B, "CUTOVER", Path(tmp) / "a.xml"), \
                mock.patch.object(B, "build", return_value=(self.data, self.P, self.names, self.bands)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.main(["--levels", "staging", "--as-live"]), 0)
                self.assertEqual(B.main(["--levels", "staging", "--as-live", "--check"]), 0)
                self.assertEqual(B.main(["--as-live", "--check"]), 1)          # the three-level candidate: another file
            self.assertTrue((Path(tmp) / "s.xml").exists())
            self.assertFalse((Path(tmp) / "a.xml").exists())

    def test_the_viewing_trials_are_retired(self) -> None:
        """A run without --as-live (the retired viewing trials, owner 2026-11-17) stops naming --as-live, in the
        command and in build(), whatever the levels; nothing is built or written."""
        for levels in B.LEVELS:
            with self.subTest(levels=levels), self.assertRaisesRegex(B.BuildError, "retired.*--as-live"):
                B.build(T.TABLES, levels=levels)
        for name in ("TRIAL", "TRIAL_STAGING", "TRIAL_LE_LABELS", "PANEL_NAME"):
            self.assertFalse(hasattr(B, name), name)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(B, "build") as built:
            for argv in ([], ["--check"], ["--levels", "all"], ["--levels", "staging"],
                         ["--levels", "staging", "--check"], ["--out", str(Path(tmp) / "a.xml")]):
                with self.subTest(argv=argv), contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(B.main(argv), 1)
                    self.assertRegex(out.getvalue(), r"^ERROR: the viewing trials .* are retired .*--as-live")
            built.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_approve_staging_options_and_the_staging_file_beside_the_candidate(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            for argv in (["--approve-staging", "--levels", "staging"], ["--approve-staging", "--as-live"],
                         ["--approve-staging", "--check"]):
                self.assertEqual(B.main(argv), 1, argv)
        P = mock.Mock(staging_data=b"staging", log=[], mast_notes=[], moved=[], items=None, staging_same=["x"],
                      gaps=[10, 20], scale=(1.0, 1.0), stripped=dict.fromkeys(B.STRIPPED, 0))
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
            # the command builds on this checkout's tables.xml (strip_build_owned takes out the build's own)
            built.assert_called_with(levels="staging", as_live=True, live_path=B.paths.TABLES_XML)
        self.assertEqual(B.CUTOVER.parent, B.CUTOVER_STAGING.parent)       # gitignored trial folder
        self.assertEqual(B.CUTOVER.parent.name, "trial")


def three_levels():
    """(candidate bytes, Panel, names, bands) of the three-level candidate (--levels all --as-live), built once for
    every test module (test_build_layout_le.built)."""
    return T.built()


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
        # The helix-join release (owner, 2026-11-17): staging as in its candidate but for the two
        # helix joins, the only difference the guard accepts (the helix bumpers become anchors, their tracks run on)
        self.assertEqual(self.P.staging_same, [
            "end bumper EBG1 -> anchor AGE1 (hidden join TG218 to Track Helix Outer)",
            "end bumper EBG2 -> anchor AGE2 (hidden join TG219 to Track Helix Inner)",
            "track segment TG52 connect2name EBG1 -> AGE1",
            "track segment TG53 connect2name EBG2 -> AGE2"])
        self.assertTrue([j for (b, j) in self.P.join_ends if b == 0])           # the helix joins reach staging
        self.assertEqual(self.names[B.STAGING]["joins"], "other")               # the build joins the helix
        self.assertEqual(sum(1 for s in self.le.findall("tracksegment") if s.get("hidden") == "yes"), 4)
        self.assertEqual(self.P.scale, self.base[1].scale)
        self.assertEqual(self.P.staging_data, self.base[0])

    def test_the_guard_stops_when_the_helix_is_not_joined(self) -> None:
        # staging's own layout as the base has no end bumper that became an anchor: nothing is joined
        with self.assertRaisesRegex(B.BuildError, "staging guard: the helix is not joined"):
            B.check_staging_unchanged((self.base[0], self.P), self.data, self.P, LIVE)

    def test_the_guard_stops_on_any_other_change(self) -> None:
        def el(root, tag, **attrs):
            le = tables.layout_editor(root, LIVE)
            return next(e for e in le.iter(tag) if all(e.get(k) == v for k, v in attrs.items()))
        edits = {
            "a staging label moved": lambda r: el(r, "positionablelabel", text="STAGING LEVEL").set("x", "61"),
            "a staging bean changed": lambda r: next(t for t in tables.turnouts(r)
                                                     if tables.user_name(t) == "Switch 1").set("inverted", "true"),
            "a helix track's segment": lambda r: el(r, "tracksegment", ident="TG53").set("blockname", "Track X"),
            "a helix join moved": lambda r: el(r, "positionablepoint", ident="AGE2").set("x", "1600.0"),
            "a helix join's mast": lambda r: el(r, "positionablepoint", ident="AGE1").set(
                "westboundsignalmast", "Mast 38LA"),
            "a Princess mast icon moved": lambda r: el(r, "signalmasticon", signalmast="Mast 38LA").set("x", "1"),
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
                    B.build(T.TABLES, levels="staging", as_live=True, approved=path)
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

    def test_the_compass_rose_beside_the_status_cluster_and_the_plain_backdrop(self) -> None:
        urls = [el.find("icon").get("url") for el in self.le.iter("positionablelabel") if el.find("icon") is not None]
        self.assertEqual(sorted(u for u in urls if "hart_panel" in u),
                         ["preference:resources/misc/hart_panel_bg_plain.jpg",
                          "preference:resources/misc/hart_panel_compass.png"])       # owner, 2026-11-18
        for name in ("hart_panel_bg_plain.jpg", "hart_panel_compass.png"):
            self.assertTrue((T.ROOT / "jmri/resources/misc" / name).exists(), name)
        rose = next(el for el in self.le.iter("positionablelabel")
                    if el.find("icon") is not None and el.find("icon").get("url").endswith("hart_panel_compass.png"))
        caption = next(el for el in self.le.iter("positionablelabel") if el.get("text") == "Track Power")
        compass = next(it for it in B.panel_items.load(B.PANEL_ITEMS)["items"] if it["id"] == "compass")
        self.assertEqual(int(rose.get("x")) + compass["size"][0] + 10, int(caption.get("x")))   # 10 px left of them
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
        # every crossover at its level's angle, or as near as its track allows (the plugin logs those: no room, or
        # its crossover rounded to whole pixels past its room, 243 since schematic-maps 0.1.42)
        limited = {re.search(r"switch (\d+)", line).group(1) for line in self.P.log if "crossover" in line
                   and ("no room for" in line or "rounded to whole pixels" in line)}
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
        yard = [el for el in self.le.iter("positionablelabel") if el.get("text") in SOUTH_YARD]
        self.assertEqual(sorted(el.get("text") for el in yard), sorted(SOUTH_YARD))     # every name drawn, once
        centres = {round(int(el.get("x")) + jt.width(el.get("text"), int(el.get("size")), False) / 2) for el in yard}
        self.assertLessEqual(max(centres) - min(centres), 1, centres)
        # the engine house's buttons step alike, and West Yard's W-2 follows W-1 one row down at that step: kept
        # so in the parked station clusters (staging's le_labels extra_steps and extra_follow place them again when
        # the Dispatcher System is unparked and its clusters go back to the plugin as extras)
        parked_items = B.panel_items.load(PARKED_LAMPS)
        staging_le = tables.layout_editor(tables.loads(self.base[0]).root, LIVE)
        frame = {el.get("ident") for el in staging_le if el.tag in ("tracksegment", "layoutturnout")}
        whole, blocks = B.panel_items.drawn_boxes(self.le, B.plugin()[1], B.slots_module(), frame_idents=frame)
        at = {}
        for it in parked_items["items"]:
            el = ET.fromstring(it["xml"])
            if (el.get("sensor") or "").startswith("MoveToTrack_"):
                at[el.get("sensor")] = B.panel_items.anchor_point(it["anchor"], whole, blocks, it["id"])
        button = lambda n: at[f"MoveToTrack_{n}_stored"]       # noqa: E731
        # (EH-1 is 36 in since 2026-11-18, longer than EH-2 and EH-3, so its button stands just west of its own
        # track's end, east of EH-2's; EH-2 and EH-3 still step one row apart as W-1 and W-2 do)
        xs = [round(button(f"EH-{n}")[0]) for n in (1, 2, 3)]
        self.assertGreater(xs[0], xs[1])
        self.assertGreater(xs[1], xs[2])
        w1, w2 = button("W-1"), button("W-2")
        rows = (w2[1] - w1[1]) / (button("EH-3")[1] - button("EH-2")[1])
        self.assertAlmostEqual(w2[0] - w1[0], rows * (xs[2] - xs[1]), delta=2)      # parked; within 2 px
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
        shared = {t.get("ycen") for t in plain["Switch 101"]} & {t.get("ycen") for t in plain["Switch 103"]}
        self.assertEqual(len(shared), 1)                    # the one track both crossovers stand on
        middle = {k: next(t for t in v if t.get("ycen") in shared) for k, v in plain.items()}
        throats = abs(float(middle["Switch 103"].get("xcen")) - float(middle["Switch 101"].get("xcen")))
        self.assertLessEqual(throats, 37)
        for k, v in plain.items():
            (x0, y0), (x1, y1) = sorted((float(t.get("xcen")), float(t.get("ycen"))) for t in v)
            self.assertAlmostEqual(abs(y1 - y0), abs(x1 - x0), delta=0.5, msg=k)
        self.assertNotIn("101-103", {el.get("text") for el in self.le.iter("positionablelabel")})
        limited = {re.search(r"switch (\d+)", line).group(1) for line in self.P.log if "no room for" in line
                   and "crossover" in line}
        self.assertFalse(limited & {"225"})
        # 243 (241 before the upper renumber, 2026-11-19) has been short of room since the straight-level rules
        # (2026-11-18): drawn at 45.8 degrees then, owner accepted; since schematic-maps 0.1.42 the plugin slides it to
        # the band's angle and logs only its whole-pixel rounding, so it stands at no more than 46 degrees
        self.assertTrue([line for line in self.P.log if "switch 243: rounded to whole pixels" in line],
                        "no rounding log line for switch 243")
        x243 = next(t for t in self.le.findall("layoutturnout")
                    if t.get("turnoutname") == "Switch 243" and "XOVER" in t.get("type"))
        p243 = {L: (float(x243.get("x" + L.lower())), float(x243.get("y" + L.lower()))) for L in "ABCD"}
        dx = (p243["D"][0] + p243["C"][0] - p243["A"][0] - p243["B"][0]) / 2
        dy = (p243["D"][1] + p243["C"][1] - p243["A"][1] - p243["B"][1]) / 2
        self.assertLessEqual(math.degrees(math.atan2(abs(dy), abs(dx))), 46.0)
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
        self.assertEqual(stations.station_display("Track EH-1"), "EH-1")
        self.assertEqual(stations.station_display("Track East Lead"), "East End")

    def test_main_and_upper_objects_are_internal_with_device_map_names(self) -> None:
        added_t = [t for t in tables.turnouts(self.root) if B.is_level_bean(t)]
        added_lb = [b for b in tables.layout_blocks(self.root) if B.is_level_bean(b)]
        added_b = {tables.user_name(b) for b in tables.blocks(self.root) if B.is_level_bean(b)}
        self.assertEqual(len(added_t), 39)
        self.assertTrue(all(tables.system_name(t).startswith("IT:HART:C3:") for t in added_t))
        self.assertEqual({tables.user_name(t) for t in added_t}, {v for k, v in self.device.items()
                                                                   if k.startswith("Switch ")})
        self.assertEqual({tables.user_name(b) for b in added_lb}, {v for k, v in self.device.items()
                                                                    if not k.startswith("Switch ")} - T.HELIX_BLOCKS)
        self.assertEqual(added_b, {tables.user_name(b) for b in added_lb})
        self.assertEqual(len(added_lb), T.LEVEL_BLOCKS)   # the 107 Loop's and 227-241's halves, 225's four corners
        self.assertTrue(all(tables.system_name(b).startswith("IB:C3:") for b in tables.blocks(self.root)
                            if B.is_level_bean(b)))

    def test_main_and_upper_masts_and_no_sensors(self) -> None:
        """Main and upper: their masts (main_upper_masts.csv: control-point masts and APB intermediates), each in the slot JMRI resolves to its
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
            want = [rows[m["mast"]]["protects"]] if rows[m["mast"]]["protects"] else []     # a virtual mast: a bumper
            self.assertEqual((f, pr), (rows[m["mast"]]["facing"], want), m["mast"])
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
        self.assertEqual((len(heads), len(masts)), (T.LEVEL_HEADS, T.LEVEL_MASTS))
        self.assertEqual({m.findtext("userName") for m in masts}, set(rows))
        written = {self.P.name(i) for i in level}
        for el in self.le:
            if el.get("ident") in written:
                self.assertFalse([k for k in el.attrib if k.endswith("boundsensor")], el.get("ident"))
                self.assertIsNone(el.find("sensorA"))

    def test_each_helix_track_is_one_block_through_its_join(self) -> None:
        # one block from staging up the helix (owner, 2026-11-20): the join anchor is no block boundary, no mast stands
        # there, and the staging block is bound to the device map's virtual sensor
        ix = B.slots_module().Index(self.le)
        for anchor, block in (("AGE1", "Track Helix Outer"), ("AGE2", "Track Helix Inner")):
            with self.subTest(anchor=anchor):
                pp = next(p for p in self.le.findall("positionablepoint") if p.get("ident") == anchor)
                self.assertFalse([k for k in pp.attrib if k.endswith("signalmast")])
                segs = {s.get("blockname") for s in self.le.findall("tracksegment")
                        if anchor in (s.get("connect1name"), s.get("connect2name"))}
                self.assertEqual(segs, {block})
        self.assertFalse([m for m in self.P.masts if m["mast"] in ("Mast 38RA", "Mast 40RA")])
        self.assertEqual(self.P.moved, [])
        lbs = {tables.user_name(lb): lb.get("occupancysensor") for lb in tables.layout_blocks(self.root)}
        self.assertEqual((lbs["Track Helix Outer"], lbs["Track Helix Inner"]), ("BS Helix Outer", "BS Helix Inner"))
        del ix

    def test_one_block_contents_icon_per_block_on_every_level(self) -> None:
        icons = Counter(el.get("blockcontents") for el in self.le.iter("BlockContentsIcon"))
        # every block but those the levels' optional_block_contents let go when no clean spot is left (logged)
        optional = {b for v in page_prefs()["le_band_labels"].values() for b in v.get("optional_block_contents", [])}
        left_out = optional - set(icons)
        skipped = {re.search(r"block contents of (.+?): no clean spot", m).group(1) for m in self.P.bcis_skipped}
        self.assertEqual(skipped, left_out)
        self.assertEqual(len(skipped), len(self.P.bcis_skipped))
        self.assertEqual(set(icons) | left_out, T.used_blocks(self.le))
        self.assertEqual(set(icons.values()), {1})
        staging = {b["block"] for b in self.base[1].bcis}
        self.assertEqual(len(staging), 45)
        size = {el.get("blockcontents"): el.get("size") for el in self.le.iter("BlockContentsIcon")}
        self.assertEqual({size[b] for b in staging}, {"13"})
        # each level's icons at that level's own size (a level with the wrong size must not hide behind another's)
        per_level = defaultdict(set)
        for b in self.P.bcis:
            per_level[B.band_key(self.bands[b["band"]][0])].add(b["block"])
        wanted = page_prefs()["le_band_labels"]
        for key, entry in wanted.items():
            self.assertTrue(per_level[key], key)
            self.assertEqual({size[b] for b in per_level[key]}, {str(entry["block_contents_size"])}, key)
        self.assertEqual(set(per_level) - set(wanted), {"Staging"})
        self.assertEqual(per_level["Staging"], staging)        # no block's icon moved between staging and a level
        self.assertEqual(set().union(*per_level.values()) - staging, set(size) - staging)

    def test_switch_numbers_and_track_names(self) -> None:
        labels = [el for el in self.le.iter("positionablelabel") if el.get("text")]
        numbers = {el.get("text"): el.get("size") for el in labels if el.get("text").startswith("SW-")}
        # a single crossover reads by its number; the helix-top 127 and 131 keep a half on each level
        self.assertLessEqual({"SW-101", "SW-225", "SW-245", "SW-127A", "SW-127B", "SW-131A", "SW-131B"}, set(numbers))
        # 121 and 125 (halves joined B to C, drawn as two turnouts on one name) carry their number once, with no
        # half's letter (schematic-maps 0.1.43)
        for n in ("121", "125"):
            self.assertEqual([t for t in numbers if re.fullmatch(rf"SW-{n}[AB]?", t)], [f"SW-{n}"], n)
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

    def test_audit_reconcile_and_facts_on_the_candidate(self) -> None:
        stations = T._load("reconcile_dispatcher_stations", paths.LAYOUT_SCRIPTS / "reconcile_dispatcher_stations.py")
        facts = T._load("check_layout_facts", T.ROOT / "tools/audit/check_layout_facts.py")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(self.data)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(stations.main(["--panel", str(path), "--check", "--no-sync"]), 0)   # parked: skips
                self.assertEqual(AUDIT.main(["--tables", str(path)]), 0)   # --strict waits for Stage 1
                self.assertEqual(facts.main(["--tables", str(path)]), 0)
            self.assertEqual(path.read_bytes(), self.data)


class Rebuilt(unittest.TestCase):
    """The candidates are built on this checkout's tables.xml, which the last cut-over wrote: the build takes out what
    an earlier build added (strip_build_owned) and draws the rest of it again, so built from either candidate
    itself, or from the tables stripped beforehand, the result is the same file byte for byte, and whatever else is
    in the tables carries through."""

    def build_from(self, data: bytes, levels: str = "staging") -> bytes:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tables.xml"
            path.write_bytes(data)
            with contextlib.redirect_stdout(io.StringIO()):
                return B.build(path, levels=levels, as_live=True, approved=None)[0]

    def test_built_on_the_live_tables_less_the_builds_own(self) -> None:
        """Round trip: tables.xml stripped, then built, is the candidate built straight from tables.xml, whose panel
        is the owner-approved one (approved_le_candidate.sha256) and whose staging candidate's panel is the approved
        staging panel (approved_staging.sha256)."""
        data, P = three_levels()[:2]
        doc = tables.load(T.TABLES)
        counts = B.strip_build_owned(doc.root)
        self.assertGreater(counts[B.STRIPPED[0]], 0)        # tables.xml is a cut-over's: it holds the build's own
        self.assertEqual(B.strip_build_owned(doc.root), dict.fromkeys(B.STRIPPED, 0))      # nothing left to take
        self.assertEqual(self.build_from(doc.tobytes(), "all"), data)
        approval = sys.modules["approval"]          # the fingerprints (tools/schematic/approval.py), as B reads them
        out = next(o for o in approval.OUTPUTS if o.key == "le-candidate")
        want = approval.parse_fingerprint(out.approved.read_text(encoding="utf-8"), out.key, out.kind)
        got = approval.fingerprint(tables.layout_editor(tables.loads(data).root, LIVE), out.kind, out.drop_attrs)
        self.assertIsNone(approval.compare(want, got))
        B.check_approved(tables.layout_editor(tables.loads(P.staging_data).root, LIVE))      # raises when not

    def test_from_the_candidates_themselves(self) -> None:
        staging, three = cutover()[0], three_levels()[0]
        self.assertEqual(self.build_from(staging), staging)
        self.assertEqual(self.build_from(three), staging)       # the main and upper objects taken out again
        self.assertEqual(self.build_from(three, "all"), three)

    def test_what_else_is_in_the_tables_carries_through(self) -> None:
        """A bean added to the live tables after a cut-over (a memory, an internal sensor whose comment names a main
        level switch, a layout block PanelPro numbered after the build's last, ILB1127 today) is in the next candidates
        unchanged; the build's own objects are drawn as before."""
        doc = tables.load(T.TABLES)
        memory = ET.fromstring('<memory value="kept"><systemName>IMHART:KEEP</systemName><userName>Kept memory'
                               '</userName></memory>')
        sensor = ET.fromstring('<sensor inverted="false"><systemName>IS:HART:KEEP</systemName><userName>Kept sensor'
                               '</userName><comment>hand-added; names Switch 107</comment></sensor>')
        # the first number after the build's own (the retired helix pieces keep theirs taken)
        hand = f"ILB{B.LAYOUT_BLOCK_FIRST + T.LEVEL_BLOCKS + len(sys.modules['le_tables'].RETIRED_BLOCKS)}"
        layout_block = ET.fromstring(f'<layoutblock systemName="{hand}" occupiedsense="2" trackcolor="gray" '
                                     f'occupiedcolor="red" extracolor="white"><systemName>{hand}</systemName>'
                                     '<userName>Track Hand Added</userName></layoutblock>')
        internal = next(s for s in doc.root.findall("sensors") if "InternalSensorManager" in s.get("class"))
        added = [(doc.root.find("memories"), memory), (internal, sensor), (doc.root.find("layoutblocks"), layout_block)]
        for sec, el in added:
            sec.append(el)
        data = self.build_from(doc.tobytes(), "all")
        for root in (tables.loads(data).root, tables.loads(self.build_from(doc.tobytes())).root):
            got = {tables.system_name(el): el for el in root.iter() if el.tag in ("memory", "sensor", "layoutblock")}
            for _sec, el in added:
                self.assertEqual(B.canon(got[tables.system_name(el)]), B.canon(el))
        root = tables.loads(data).root
        for sec_tag, el in ((sec.tag, el) for sec, el in added):
            for sec in root.findall(sec_tag):
                for x in [x for x in sec if tables.system_name(x) == tables.system_name(el)]:
                    tables.remove_child(sec, x)
        self.assertEqual(B.canon(root), B.canon(tables.loads(three_levels()[0]).root))

    def test_tables_without_the_generated_panel_are_refused(self) -> None:
        data = cutover()[0]
        bare = without_live_panel(data)
        self.assertIsNone(tables.layout_editor(tables.loads(bare).root, LIVE))
        with self.assertRaisesRegex(B.BuildError, "no main Layout Editor panel.*starts from tables that hold the "
                                                  "generated panel"):
            self.build_from(bare)
        doc = tables.loads(data)
        panel = tables.layout_editor(doc.root, LIVE)
        panel.remove(next(lb for lb in panel.findall("positionablelabel")
                          if lb.get("text") == tables.GENERATED_PANEL_MARKER))
        with self.assertRaisesRegex(B.BuildError, "'HART Railroad' panel is not a generated one"):
            self.build_from(doc.tobytes())


class StripBuildOwned(unittest.TestCase):
    """strip_build_owned on small tables: the build's own objects, and the logic and paths stock JMRI derived from
    them, go; the rest stays, indentation and all."""
    TABLES = """<layout-config>
  <turnouts class="internal">
    <turnout><systemName>IT:KEEP</systemName><userName>Kept</userName></turnout>
    <turnout><systemName>IT:HART:C3:107</systemName><userName>Switch 107</userName></turnout>
  </turnouts>
  <signalheads class="h">
    <signalhead><systemName>IH:HART:C3:136RA</systemName><userName>Head 136RA</userName></signalhead>
  </signalheads>
  <signalmasts class="m">
    <signalmast><systemName>IF$shsm:basic:one-low(IH:HART:C3:136RA)</systemName><userName>Mast 136RA</userName>
    </signalmast>
    <virtualsignalmast><systemName>IF$vsm:basic:one-low($1)</systemName><userName>Mast 40RA</userName>
    </virtualsignalmast>
  </signalmasts>
  <blocks class="b">
    <block systemName="IB1"><systemName>IB1</systemName><userName>Track A</userName></block>
    <block systemName="IB:C3:0001"><systemName>IB:C3:0001</systemName><userName>Track 135-H1</userName></block>
    <block systemName="IB1"><systemName>IB1</systemName><userName>Track A</userName>
      <path todir="16" fromdir="32" block="IB2" />
      <path todir="96" fromdir="144" block="IB:C3:0001" />
      <path todir="16" fromdir="32" block="IB:C3:0099" />
    </block>
  </blocks>
  <layoutblocks class="lb">
    <layoutblock systemName="ILB1001"><systemName>ILB1001</systemName><userName>Track 135-H1</userName></layoutblock>
    <layoutblock systemName="ILB1126"><systemName>ILB1126</systemName><userName>Track Hand Added</userName>
    </layoutblock>
  </layoutblocks>
  <signalmastlogics class="l">
    <signalmastlogic source="Mast 136RA"><sourceSignalMast>Mast 136RA</sourceSignalMast>
      <destinationMast destination="Mast 40RB"><destinationSignalMast>Mast 40RB</destinationSignalMast>
      </destinationMast>
    </signalmastlogic>
    <signalmastlogic source="Mast 40RA"><sourceSignalMast>Mast 40RA</sourceSignalMast>
      <destinationMast destination="Mast 136RA"><destinationSignalMast>Mast 136RA</destinationSignalMast>
      </destinationMast>
    </signalmastlogic>
    <signalmastlogic source="Mast 38RA"><sourceSignalMast>Mast 38RA</sourceSignalMast>
      <destinationMast destination="Mast 36L"><destinationSignalMast>Mast 36L</destinationSignalMast>
        <comment>held for Switch 107 and Mast 136RA</comment>
      </destinationMast>
      <destinationMast destination="Mast 30L"><destinationSignalMast>Mast 30L</destinationSignalMast>
        <turnouts><turnout><turnoutName>Switch 107</turnoutName><turnoutState>closed</turnoutState></turnout>
        </turnouts>
      </destinationMast>
      <destinationMast destination="Mast 140RA"><destinationSignalMast>Mast 140RA</destinationSignalMast>
      </destinationMast>
    </signalmastlogic>
    <signalmastlogic source="Mast 150LA"><sourceSignalMast>Mast 150LA</sourceSignalMast>
      <destinationMast destination="Mast 36L"><destinationSignalMast>Mast 36L</destinationSignalMast>
      </destinationMast>
    </signalmastlogic>
  </signalmastlogics>
  <memories class="m"><memory><systemName>IM1</systemName><comment>Switch 107</comment></memory></memories>
</layout-config>"""

    def test_the_builds_own_and_their_derived_references_go(self) -> None:
        """Also a reference to a main or upper object no longer in the tables (Mast 140RA, Mast 150LA, IB:C3:0099:
        by the naming rule), and a layout block by its user name, not its number: ILB1126, a block added in PanelPro,
        stays. A staging destination whose comment names Switch 107 and Mast 136RA keeps: a comment is no
        reference."""
        root = ET.fromstring(self.TABLES)
        counts = B.strip_build_owned(root)
        self.assertEqual(counts, dict(zip(B.STRIPPED, (5, 2, 3, 1, 2, 0))))
        self.assertEqual([tables.system_name(b) for b in tables.layout_blocks(root)], ["ILB1126"])
        self.assertEqual([tables.system_name(t) for t in root.iter("turnout") if t.find("systemName") is not None],
                         ["IT:KEEP"])
        self.assertEqual([tables.user_name(m) for m in tables.masts(root)], ["Mast 40RA"])
        self.assertEqual([p.get("block") for p in root.iter("path")], ["IB2"])
        self.assertEqual({src: [d for _s, d, _e in tables.mast_logic_pairs(root) if _s == src]
                          for src in tables.mast_logic_sources(root)}, {"Mast 38RA": ["Mast 36L"]})
        self.assertEqual(root.find("memories/memory/comment").text, "Switch 107")    # not derived: carried
        self.assertEqual(root.find(".//destinationMast[@destination='Mast 36L']/comment").text,
                         "held for Switch 107 and Mast 136RA")
        self.assertEqual(B.strip_build_owned(root), dict.fromkeys(B.STRIPPED, 0))
        # what is left is indented as before: the section closes where it did
        self.assertEqual(root.find("turnouts")[-1].tail, "\n  ")
        self.assertEqual(root.find("signalheads").text, None)

    def test_a_reference_left_behind_stops(self) -> None:
        root = ET.fromstring(self.TABLES)
        with mock.patch.object(B.tables, "remove_child"), \
                self.assertRaisesRegex(B.BuildError, "left some of it in"):
            B.strip_build_owned(root)


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
