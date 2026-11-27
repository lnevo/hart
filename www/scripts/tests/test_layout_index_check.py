"""--check on the two layout index builders: each builds in memory and passes its checks, and a PNG drawn from other
inputs fails.

A mast rename (16R, PR #441) used to leave www/data/layout-index.json behind until someone rebuilt it by hand; since
2026-11-25 the JSON is not committed (ADR-036) and is built wherever it is used.
"""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_cats_layout_index as cats_index  # noqa: E402
import png_stamp  # noqa: E402
import build_layout_index as le_index  # noqa: E402


class NamesFromTheMasterTest(unittest.TestCase):
    """load_names reads staging's rows of devices.csv, one place (hartlib.devices)."""

    def test_the_committed_master_names_a_switch_by_hardware_and_name(self) -> None:
        by_hw, by_name = le_index.load_names(le_index.NAMES)
        self.assertEqual(by_hw["M2T408"]["proposed"], "Switch 1")
        self.assertEqual(by_name["Switch 1"]["cp"], "Brick")
        self.assertEqual(by_name["Switch 1"]["comment"], by_hw["M2T408"]["comment"])
        self.assertIn("DCC: 100", by_hw["M2T408"]["comment"])

    def test_a_master_that_cannot_be_read_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(Exception, "cannot read it"):
            le_index.load_names(Path(tmp) / "missing.csv")


class LayoutIndexCheckTest(unittest.TestCase):
    """--check builds each index in memory and runs its checks (ADR-036: the JSON is not committed); the PNG it
    sits on is committed with a stamp of what it is drawn from."""

    def check(self, mod, **patches) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(mod, name, value))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            rc = mod.main(["--check"])
        return rc, out.getvalue(), err.getvalue()

    def tmp(self) -> Path:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        return tmp

    def png(self, mod) -> Path:
        return mod.SCHEMATIC if mod is le_index else mod.OUT_IMG

    def png_patch(self, mod, path: Path) -> dict:
        return {"SCHEMATIC" if mod is le_index else "OUT_IMG": path}

    def test_the_indexes_build_and_pass_without_a_json_file(self) -> None:
        # no www/data copy is read: a missing one changes nothing
        for mod in (le_index, cats_index):
            with self.subTest(index=mod.OUT_JSON.name):
                rc, out, err = self.check(mod, OUT_JSON=self.tmp() / "absent.json")
                self.assertEqual((rc, err), (0, ""))
                self.assertIn("builds and passes its checks", out)

    def test_the_cats_index_joins_to_the_layout_index_built_in_memory(self) -> None:
        # it used to read www/data/layout-index.json and join to nothing when the file was missing
        items = cats_index.build()["items"]
        self.assertTrue(any(it["mqtt"] for it in items), "no CATS hotspot got an MQTT address from the layout index")

    def test_a_layout_index_with_no_items_stops_the_cats_index(self) -> None:
        with self.assertRaisesRegex(cats_index.CatsIndexError, "has no items"):
            cats_index.build({"items": []})
        broken = mock.Mock(side_effect=le_index.LayoutIndexError("missing panel: x"))
        with mock.patch.object(cats_index.build_layout_index, "build", broken):
            with self.assertRaisesRegex(cats_index.CatsIndexError, "cannot build the layout index.*missing panel"):
                cats_index.build()

    def test_a_change_to_what_the_png_is_drawn_from_fails(self) -> None:
        for mod in (le_index, cats_index):
            with self.subTest(index=mod.OUT_JSON.name):
                render = self.tmp() / mod.RENDER.name
                render.write_bytes(mod.RENDER.read_bytes() + b"\n# changed\n")
                rc, _, err = self.check(mod, RENDER=render)
                self.assertEqual(rc, 1)
                self.assertIn("was drawn from other inputs", err)
                self.assertIn(f"run python3 www/scripts/{Path(mod.__file__).name}", err)

    def test_the_stamp_hashes_every_part_of_the_renderer(self) -> None:
        self.assertEqual((le_index.RENDER, *le_index.RENDER_PARTS), le_index.load_render_mod().SOURCES)
        part = self.tmp() / le_index.RENDER_PARTS[1].name
        part.write_bytes(le_index.RENDER_PARTS[1].read_bytes() + b"\n# changed\n")
        rc, _, err = self.check(le_index, RENDER_PARTS=(le_index.RENDER_PARTS[0], part))
        self.assertEqual(rc, 1)
        self.assertIn("was drawn from other inputs", err)

    def test_a_png_without_a_stamp_fails(self) -> None:
        for mod in (le_index, cats_index):
            with self.subTest(index=mod.OUT_JSON.name):
                bare = self.tmp() / "bare.png"
                Image.new("RGB", png_stamp.size(self.png(mod))).save(bare)
                rc, _, err = self.check(mod, **self.png_patch(mod, bare))
                self.assertEqual(rc, 1)
                self.assertIn("its stamp is None", err)

    def test_a_missing_png_stops_with_the_command(self) -> None:
        for mod in (le_index, cats_index):
            with self.subTest(index=mod.OUT_JSON.name):
                rc, _, err = self.check(mod, **self.png_patch(mod, self.tmp() / "gone.png"))
                self.assertEqual(rc, 1)
                self.assertIn("missing", err)
                self.assertIn(f"run python3 www/scripts/{Path(mod.__file__).name}", err)
                self.assertNotIn("Traceback", err)

    def test_a_broken_source_is_a_clear_error_not_a_traceback(self) -> None:
        # review of #1147: a tables.xml that is not XML, or a device master hartlib refuses, raised raw
        bad = self.tmp() / "tables.xml"
        bad.write_text("<layout-config>", encoding="utf-8")
        for mod, patch in ((le_index, {"PANEL": bad}), (cats_index, {"PANEL": bad})):
            with self.subTest(index=mod.OUT_JSON.name):
                rc, _, err = self.check(mod, **patch)
                self.assertEqual(rc, 1)
                self.assertIn("ParseError", err)
                self.assertNotIn("Traceback", err)
        refused = mock.Mock(side_effect=le_index.railroad_facts.FactsError("devices.csv: cannot read it"))
        with mock.patch.object(le_index, "load_names", refused), \
                self.assertRaisesRegex(le_index.LayoutIndexError, "FactsError: devices.csv: cannot read it"):
            le_index.build()

    def test_a_built_index_that_does_not_add_up_fails(self) -> None:
        for mod in (le_index, cats_index):
            with self.subTest(index=mod.OUT_JSON.name):
                good = mod.build()
                self.assertEqual(mod.problems(good), [])
                short = json.loads(json.dumps(good))
                short["items"].pop()
                twice = json.loads(json.dumps(good))
                twice["items"][1]["id"] = twice["items"][0]["id"]
                self.assertIn("counts.total", "\n".join(mod.problems(short)))
                self.assertIn("repeated item ids", "\n".join(mod.problems(twice)))
                with self.assertRaisesRegex(Exception, "fails its checks"):
                    mod.index_text({**good, "items": [], "counts": {}})

    def test_the_built_text_is_what_the_site_publishes(self) -> None:
        # index_text is the one builder of the JSON text: the site build, the preview and --write all use it
        self.assertEqual(json.loads(le_index.index_text()), le_index.build())
        self.assertEqual(json.loads(cats_index.index_text()), cats_index.build())


class Steps(unittest.TestCase):
    """The layout index's named steps: control points, kinds of unplaced devices, the overview window."""

    def test_cp_for_takes_the_place_then_the_desk_area(self) -> None:
        pairs = [("23a", "East End"), ("5", "West")]
        self.assertEqual(le_index.cp_for("Switch 5", pairs, "Yard"), "Yard")
        self.assertEqual(le_index.cp_for("Switch 23a", pairs, ""), "East End")
        self.assertEqual(le_index.cp_for("Switch 9", pairs, ""), "")

    def test_item_kind(self) -> None:
        for raw, want in (("lcc turnout", "turnout"), ("signal mast", "signal"), ("os block", "occupancy"),
                          ("feedback", "sensor")):
            self.assertEqual(le_index.item_kind(raw), want, raw)

    def test_overview_maps_panel_points_inside_the_padding(self) -> None:
        ov = le_index.overview_xy([{"cen": (10.0, 20.0)}], [((0.0, 0.0), (100.0, 50.0), None, None)], [], [])
        self.assertEqual(ov.x(-le_index.PAD), le_index.PAD)
        self.assertEqual(ov.y(-le_index.PAD), le_index.TOP)
        self.assertGreater(ov.width, ov.x(100.0))
        with self.assertRaises(le_index.LayoutIndexError):
            le_index.overview_xy([], [], [], [])

    def test_a_source_that_cannot_be_read_keeps_its_cause(self) -> None:
        boom = OSError("disk")
        with mock.patch.object(le_index, "_build", side_effect=boom):
            with self.assertRaisesRegex(le_index.LayoutIndexError, "OSError: disk") as cm:
                le_index.build()
        self.assertIs(cm.exception.__cause__, boom)


if __name__ == "__main__":
    unittest.main()
