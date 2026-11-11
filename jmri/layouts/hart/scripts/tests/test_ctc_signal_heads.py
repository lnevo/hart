"""USS CTC signal icons, the generator that draws them, and the as-built remap
must follow the masts and heads in tables.xml and the CATS desk."""
from __future__ import annotations

import ast
import csv
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[3]
TABLES = SCRIPTS.parent / "output" / "tables.xml"
GUI = SCRIPTS.parent / "ctc" / "GUIObjects.xml"
CATS = ROOT / "cats/panels/HART_CTC.xml"
WIRING = ROOT / "docs/wiring/signals/signal_wiring.csv"
REFRESH = ROOT / "docs/wiring/scripts/refresh_wiring_docs.py"

sys.path.insert(0, str(SCRIPTS))
import gen_ctc_track_plan as gen  # noqa: E402


def mast_heads() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for el in ET.parse(TABLES).getroot().iter("signalmast"):
        sn = el.findtext("systemName") or ""
        if sn.startswith("IF$shsm:"):
            out[el.findtext("userName")] = re.findall(r"IH\d+", sn)
    return out


def head_icons(path: Path) -> set[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r'<signalheadicon signalhead="(IH\d+)" x="(\d+)" y="(\d+)"', text))


def load_remap():
    """PANEL_TO_WIRING_IH and remap_panel_ih without importing openpyxl."""
    tree = ast.parse(REFRESH.read_text(encoding="utf-8"))
    keep = []
    for node in tree.body:
        targets = []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        names = {t.id for t in targets if isinstance(t, ast.Name)}
        if names & {"PANEL_TO_WIRING_IH", "_IH_TOKEN"}:
            keep.append(node)
        if isinstance(node, ast.FunctionDef) and node.name == "remap_panel_ih":
            keep.append(node)
    ns: dict = {"re": re}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(REFRESH), "exec"), ns)
    return ns["PANEL_TO_WIRING_IH"], ns["remap_panel_ih"]


def signal_icons(path: Path) -> set[tuple[str, str, str, str]]:
    text = path.read_text(encoding="utf-8")
    pe = re.search(r"<paneleditor\b.*?</paneleditor>", text, re.S).group(0)
    out = set()
    for kind, name, x, y in re.findall(
        r'<signal(mast|head)icon signal(?:mast|head)="([^"]+)" x="(\d+)" y="(\d+)"', pe
    ):
        out.add((kind, name, x, y))
    return out


# Brick masts whose USS facing has differed from the CATS SIGORIENT since before
# this test; left as drawn until someone checks them on the layout.
FACING_EXCEPTIONS = {"Mast 4RA", "Mast 4RB", "Mast 2L"}


def cats_facing() -> dict[str, str]:
    """Mast -> E (SIGORIENT RIGHT) or W (LEFT); TOP/BOTTOM lamps on diagonals are left out."""
    out = {}
    for sig in ET.parse(CATS).getroot().iter("SECSIGNAL"):
        orient = sig.find("PANELSIGNAL").get("SIGORIENT")
        if orient in ("RIGHT", "LEFT"):
            out[(sig.text or "").strip()] = "E" if orient == "RIGHT" else "W"
    return out


def cats_signals() -> dict[str, tuple[int, int, str]]:
    """Mast -> (x, y, kind) from the CATS desk; LAMP2 draws as h2, LAMP1 as d1."""
    out = {}
    for sec in ET.parse(CATS).getroot().find("TRACKPLAN").findall("SECTION"):
        for sig in sec.iter("SECSIGNAL"):
            lamp = sig.find("PANELSIGNAL").get("SIGPANTYPE")
            kind = "h2" if lamp == "LAMP2" else "d1"
            out[(sig.text or "").strip()] = (int(sec.get("X")), int(sec.get("Y")), kind)
    return out


class CtcSignalHeadsTest(unittest.TestCase):
    def test_icon_kind_follows_mast_head_count(self) -> None:
        """d1 (head icon) only for one-head masts, on that head; h2 (mast icon) only for two-head masts."""
        masts = mast_heads()
        for mast, _x, _y, _facing, kind, head in gen.SIGNALS:
            with self.subTest(mast=mast):
                self.assertIn(mast, masts)
                heads = masts[mast]
                if kind == "d1":
                    self.assertEqual(len(heads), 1, "d1 drawn for a two-head mast")
                    self.assertEqual(head, heads[0])
                else:
                    self.assertEqual(kind, "h2")
                    self.assertEqual(len(heads), 2, "h2 drawn for a one-head mast")
                    self.assertIsNone(head)

    def test_icons_sit_in_the_cats_desk_cells(self) -> None:
        cats = cats_signals()
        self.assertEqual({s[0] for s in gen.SIGNALS}, set(cats))
        for mast, x, y, _facing, kind, _head in gen.SIGNALS:
            with self.subTest(mast=mast):
                self.assertEqual((x, y, kind), cats[mast])

    def test_icons_face_as_on_the_cats_desk(self) -> None:
        facing = cats_facing()
        for mast, _x, _y, face, _kind, _head in gen.SIGNALS:
            if mast in FACING_EXCEPTIONS or mast not in facing:
                continue
            with self.subTest(mast=mast):
                self.assertEqual(face, facing[mast])

    def test_gui_objects_head_icons_match_tables(self) -> None:
        tables = head_icons(TABLES)
        gui = head_icons(GUI)
        self.assertEqual(gui, {i for i in tables if i[0] != "IH9990"})

    def test_uss_signal_icons_match_generator(self) -> None:
        """Both copies of the USS panel carry exactly the icons SIGNALS describes."""
        want = set()
        for mast, cx, cy, facing, kind, head in gen.SIGNALS:
            x, y = gen.signal_pos(cx, cy, facing, kind)
            want.add(("mast", mast, str(x), str(y)) if kind == "h2" else ("head", head, str(x), str(y)))
        self.assertEqual(signal_icons(GUI), want)
        self.assertEqual(signal_icons(TABLES), want)


class GeneratorTest(unittest.TestCase):
    def test_apply_is_idempotent(self) -> None:
        """A second regen strips what the first drew (occupancy jewels are BS sensors)."""
        cells = gen.parse_cats(CATS)
        text = GUI.read_text(encoding="utf-8")
        once = gen.apply(text, cells)
        self.assertEqual(gen.apply(once, cells), once)
        self.assertEqual(once.count('<sensoricon sensor="BS Barn"'), 1)

    def test_brick_sidi_patch_keeps_tables(self) -> None:
        """Switch 1 (Mast 2L) codes from R and Switch 3 (4RA/4RB) from L, as stored."""
        text = TABLES.read_text(encoding="utf-8")
        self.assertEqual(gen.patch_brick_sidi(text), text)


class AsBuiltRemapTest(unittest.TestCase):
    def test_remap_is_one_pass_onto_wired_heads(self) -> None:
        mapping, remap = load_remap()
        self.assertEqual(len(mapping), 17)
        with WIRING.open(newline="") as f:
            wired = {r["system_name"] for r in csv.DictReader(f)}
        self.assertLessEqual(set(mapping.values()), wired)
        # IH1232 was 24RA (now IH232); IH1237 was 34L (now IH1232). No chaining.
        self.assertEqual(remap("IH1232=Red IH1237=Green"), "IH232=Red IH1232=Green")
        self.assertEqual(remap("IH137 IH132 IH13"), "IH132 IH1132 IH13")
        self.assertEqual(remap("IH1332"), "IH1332")
        self.assertEqual(remap(None), None)


if __name__ == "__main__":
    unittest.main()
