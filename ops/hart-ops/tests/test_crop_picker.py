"""Crop picker on the intake review page: box format, page, re-cut and sheet-import."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import crop_picker as cp  # noqa: E402
import finalize_car_images as final  # noqa: E402
import intake_stages as stages  # noqa: E402


def row(photo, **fields):
    r = {c: "" for c in stages.REVIEW_COLUMNS}
    r.update({"photo": photo, "kind": "car", "status": "pending", "blur": "100", **fields})
    return r


def gradient(w=400, h=300):
    """Each pixel's red is its column and green its row (both /2), so a crop can be located."""
    xs, ys = np.meshgrid(np.arange(w), np.arange(h))
    arr = np.stack([xs // 2, ys // 2, np.full_like(xs, 128)], -1).astype("uint8")
    return Image.fromarray(arr)


class Box(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(cp.parse_box("10,20,300,100"), (10, 20, 300, 100, 0.0))
        self.assertEqual(cp.parse_box("10, 20, 300, 100, -1.5"), (10, 20, 300, 100, -1.5))
        self.assertEqual(cp.format_box(10.4, 20, 300, 100, 0.02), "10,20,300,100")
        self.assertEqual(cp.format_box(10, 20, 300, 100, 1.5), "10,20,300,100,1.5")

    def test_bad_boxes_refused(self):
        for text in ("1,2,3", "a,b,c,d", "0,0,10,10"):
            with self.assertRaises(SystemExit):
                cp.parse_box(text)


class Cut(unittest.TestCase):
    def test_car_cut_is_the_box_on_the_leveled_photo(self):
        ctx = SimpleNamespace(IMAGES_DIR=Path("/nowhere"))
        with mock.patch.object(final, "_level_for_finalize", return_value=(gradient(), 0.0)):
            out = cp.cut(row("p.jpg", crop="100,60,200,100"), ctx)
        self.assertEqual(out.size, (200, 100))
        r, g, _ = out.getpixel((0, 0))
        self.assertEqual((r, g), (50, 30))  # top-left of the box is photo pixel (100, 60)

    def test_box_past_the_edge_is_filled_not_shifted(self):
        ctx = SimpleNamespace(IMAGES_DIR=Path("/nowhere"))
        with mock.patch.object(final, "_level_for_finalize", return_value=(gradient(), 0.0)):
            out = cp.cut(row("p.jpg", crop="-50,0,200,100"), ctx)
        self.assertEqual(out.size, (200, 100))
        self.assertEqual(out.getpixel((50, 0))[:2], (0, 0))  # photo column 0 lands 50 px in


class Page(unittest.TestCase):
    def test_buttons_only_for_photos_with_a_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp) / "b1"
            (batch / cp.VIEW_DIR).mkdir(parents=True)
            (batch / cp.VIEW_DIR / "a.car.jpg").write_bytes(b"x")
            cp.write_data(batch, {"a.jpg": {"kind": "car", "src": "picker/a.car.jpg",
                                            "w": 400, "h": 300, "auto": [1, 2, 300, 100]}})
            rows = [row("a.jpg", image="/x/a.png"), row("b.jpg", image="/x/b.png")]
            stages.contact_sheet(batch / "review.html", rows)
            text = (batch / "review.html").read_text(encoding="utf-8")
        self.assertEqual(text.count("Adjust crop</button>"), 1)
        self.assertIn('data-f="crop"', text)
        self.assertIn("Use this crop", text)

    def test_no_picker_without_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b1" / "review.html"
            path.parent.mkdir()
            stages.contact_sheet(path, [row("a.jpg", image="/x/a.png")])
            text = path.read_text(encoding="utf-8")
        self.assertNotIn("Adjust crop</button>", text)

    def test_view_for_other_kind_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp)
            (batch / cp.VIEW_DIR).mkdir()
            (batch / cp.VIEW_DIR / "a.car.jpg").write_bytes(b"x")
            cp.write_data(batch, {"a.jpg": {"kind": "car", "src": "picker/a.car.jpg",
                                            "w": 4, "h": 3, "auto": [0, 0, 4, 3]}})
            *_, pick = cp.page_parts(batch, [row("a.jpg", kind="loco")])
        self.assertEqual(pick, {})


class SheetImport(unittest.TestCase):
    def test_only_changed_crops_are_cut(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batch = root / "b1"
            batch.mkdir()
            old = [row("a.jpg", crop="1,1,100,100"), row("b.jpg"), row("c.jpg", crop="5,5,100,100")]
            new = [dict(r) for r in old]
            new[1]["crop"] = "2,2,200,100"   # newly picked
            new[2]["crop"] = "6,6,100,100"   # changed
            stages.write_csv(batch / "review.csv", stages.REVIEW_COLUMNS, old)
            stages.write_csv(root / "down.csv", stages.REVIEW_COLUMNS, new)
            cut = []
            with mock.patch.object(stages, "BATCH_ROOT", root), \
                 mock.patch.object(cp, "apply", side_effect=lambda r, ctx: cut.append(r["photo"])), \
                 mock.patch.object(stages, "refresh_rows"):
                stages.cmd_sheet_import(SimpleNamespace(batch="b1", file=str(root / "down.csv")), None)
            saved = stages.read_csv(batch / "review.csv")
        self.assertEqual(cut, ["b.jpg", "c.jpg"])
        self.assertEqual([r["crop"] for r in saved], ["1,1,100,100", "2,2,200,100", "6,6,100,100"])

    def test_sheet_without_crop_column_still_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b1").mkdir()
            cols = [c for c in stages.REVIEW_COLUMNS if c != "crop"]
            stages.write_csv(root / "b1" / "review.csv", cols, [row("a.jpg")])
            stages.write_csv(root / "down.csv", cols, [row("a.jpg")])
            with mock.patch.object(stages, "BATCH_ROOT", root), mock.patch.object(stages, "refresh_rows"):
                stages.cmd_sheet_import(SimpleNamespace(batch="b1", file=str(root / "down.csv")), None)
            self.assertEqual(stages.read_csv(root / "b1" / "review.csv")[0]["crop"], "")


if __name__ == "__main__":
    unittest.main()
