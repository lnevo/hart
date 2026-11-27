"""sharpen_card_fill_images: the command line reads car_paths' card-fill folders and writes the print copies."""
import contextlib
import io
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "card_pipeline"))

from PIL import Image  # noqa: E402

import car_paths  # noqa: E402
import sharpen_card_fill_images as scf  # noqa: E402


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = fn(*args, **kwargs)
    return code, out.getvalue()


class CommandLine(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.src = Path(tmp.name) / "fill"
        self.out = Path(tmp.name) / "print"
        self.src.mkdir()
        for stem in ("IMG_0001", "IMG_0002"):
            Image.new("RGB", (8, 6), (120, 80, 40)).save(self.src / f"{stem}.png")

    def test_all_writes_one_print_copy_per_image(self):
        code, text = quiet(scf.main, ["--all"], self.src, self.out)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["IMG_0001.png", "IMG_0002.png"])
        self.assertIn("Wrote 2 images", text)
        with Image.open(self.out / "IMG_0001.png") as img:
            self.assertEqual(img.size, (8, 6))
            self.assertNotEqual(img.getpixel((0, 0)), (120, 80, 40))  # brightened

    def test_one_stem_writes_only_that_image(self):
        code, _ = quiet(scf.main, ["IMG_0002.png"], self.src, self.out)
        self.assertEqual(code, 0)
        self.assertEqual([p.name for p in self.out.iterdir()], ["IMG_0002.png"])

    def test_missing_stem_exits_1(self):
        code, text = quiet(scf.main, ["IMG_9999"], self.src, self.out)
        self.assertEqual(code, 1)
        self.assertIn("missing", text)
        self.assertFalse(self.out.exists())

    def test_no_folders_given_uses_the_car_paths_folders(self):
        with mock.patch.object(car_paths, "CARD_FILL_DIR", self.src), \
                mock.patch.object(car_paths, "CARD_FILL_PRINT_DIR", self.out):
            code, _ = quiet(scf.main, [])
        self.assertEqual(code, 0)
        self.assertEqual(len(list(self.out.iterdir())), 2)

    def test_car_paths_folders_sit_under_the_cards_root(self):
        self.assertEqual(car_paths.CARD_FILL_DIR, car_paths.ROOT / "CarImagesCardFill")
        self.assertEqual(car_paths.CARD_FILL_PRINT_DIR, car_paths.ROOT / "CarImagesCardFillPrint")

    def test_unknown_option_or_two_images_are_refused_before_any_write(self):
        for argv in (["--sharpen"], ["IMG_0001", "IMG_0002"], ["--all", "IMG_0001"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    scf.main(argv, self.src, self.out)
                self.assertEqual(cm.exception.code, 2)
        self.assertFalse(self.out.exists())

    def test_unsharp_settings_reach_the_filter(self):
        img = Image.new("RGB", (8, 6), (120, 80, 40))
        with mock.patch.object(scf.ImageFilter, "UnsharpMask", wraps=scf.ImageFilter.UnsharpMask) as mask:
            scf.sharpen_for_print(img)
        mask.assert_called_once_with(0.9, 115, 2)

    def test_empty_source_exits_1(self):
        empty = self.src.parent / "empty"
        empty.mkdir()
        code, text = quiet(scf.main, [], empty, self.out)
        self.assertEqual(code, 1)
        self.assertIn("No images in", text)


if __name__ == "__main__":
    unittest.main()
