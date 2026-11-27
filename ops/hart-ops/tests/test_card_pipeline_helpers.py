"""Behaviour of the card pipeline's shared helpers: the card overrides file, the sticker deck writer, the hartlib
path finder and the STS shipment export the CC/WB labels read."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

from docx import Document  # noqa: E402

import card_template_sheet as cts  # noqa: E402
import generate_all_cards as gac  # noqa: E402
import generate_cc_waybill_labels as gcl  # noqa: E402
import hartlib_path  # noqa: E402
from card_errors import CardPipelineError  # noqa: E402

HEAD = "source_image,image,card_type,road_name,road_number,description\n"


class TempDir(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class CardOverrides(TempDir):
    def overrides(self, text: str) -> dict[str, gac.CardOverride]:
        path = self.write("card_overrides.csv", text)
        with mock.patch.object(gac.car_paths, "HART_OPS_ROOT", self.tmp):
            return gac.read_card_overrides(path)

    def test_a_good_row_gives_the_card_and_its_image(self):
        image = self.write("card_pipeline/assets/X1.png", "png")
        got = self.overrides(HEAD + "IMG_1.png,card_pipeline/assets/X1.png,Flat Car,N&W,1,Flatcar · 52'\n")
        self.assertEqual(list(got), ["IMG_1.png"])
        self.assertEqual(got["IMG_1.png"].image, image)
        self.assertEqual(got["IMG_1.png"].record, {"Type": "Flat Car", "RoadName": "N&W", "RoadNumber": "1",
                                                   "Description": "Flatcar · 52'"})

    def test_wrong_columns_are_named(self):
        with self.assertRaisesRegex(CardPipelineError, "columns are"):
            self.overrides("source_image,image\nIMG_1.png,x.png\n")

    def test_a_photo_listed_twice_is_named_with_its_line(self):
        self.write("a.png", "png")
        row = "IMG_1.png,a.png,Flat Car,N&W,1,d\n"
        with self.assertRaisesRegex(CardPipelineError, r":3: IMG_1.png is listed twice"):
            self.overrides(HEAD + row + row)

    def test_a_missing_image_is_named(self):
        with self.assertRaisesRegex(CardPipelineError, r":2: the image .*nope.png for IMG_1.png is missing"):
            self.overrides(HEAD + "IMG_1.png,nope.png,Flat Car,N&W,1,d\n")

    def test_the_repository_file_reads(self):
        self.assertIn("IMG_9088.png", gac.read_card_overrides(gac.CARD_OVERRIDES_CSV))


class StickerDeck(TempDir):
    def sheet(self) -> Path:
        path = self.tmp / "sheet.docx"
        doc = Document()
        doc.add_paragraph("template intro")
        doc.add_table(rows=3, cols=3)
        doc.save(path)
        return path

    def test_an_empty_deck_stops_and_writes_nothing(self):
        out = self.tmp / "out" / "deck.docx"
        with self.assertRaisesRegex(CardPipelineError, "no cards to write"):
            cts.write_sticker_deck([], lambda cell, idx, rec: None, sticker_sheet=self.sheet(), output=out)
        self.assertFalse(out.exists())

    def test_a_short_deck_fills_its_slots_in_order_on_one_page(self):
        out = self.tmp / "out" / "deck.docx"
        calls: list[tuple[int, str]] = []

        def fill(cell, idx: int, rec: str) -> None:
            calls.append((idx, rec))
            cell.text = rec

        cts.write_sticker_deck(["a", "b"], fill, sticker_sheet=self.sheet(), output=out)
        self.assertEqual(calls, [(0, "a"), (1, "b")])
        doc = Document(str(out))
        self.assertEqual(len(doc.tables), 1)
        self.assertEqual([c.text for c in doc.tables[0].rows[0].cells], ["a", "b", ""])
        self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ["deck.docx"])

    def test_ten_cards_take_two_pages_and_idx_runs_on(self):
        out = self.tmp / "deck.docx"
        seen: list[int] = []
        cts.write_sticker_deck(list(range(10)), lambda cell, idx, rec: seen.append(idx),
                               sticker_sheet=self.sheet(), output=out)
        self.assertEqual(seen, list(range(10)))
        self.assertEqual(len(Document(str(out)).tables), 2)
        self.assertEqual(cts.page_count(10), 2)
        self.assertEqual(cts.page_count(9), 1)


class HartlibPath(TempDir):
    def test_finds_the_nearest_src_and_puts_it_on_the_path_once(self):
        src = self.tmp / "repo/tools/hartlib/src"
        src.mkdir(parents=True)
        start = self.write("repo/ops/hart-ops/card_pipeline/x.py", "")
        with mock.patch.object(sys, "path", ["other"]):
            self.assertEqual(hartlib_path.ensure_on_path(start), src.resolve())
            hartlib_path.ensure_on_path(start)
            self.assertEqual(sys.path, [str(src.resolve()), "other"])

    def test_no_checkout_above_raises_a_named_error(self):
        start = self.write("loose/x.py", "")
        with self.assertRaises(hartlib_path.HartlibNotFoundError) as cm:
            hartlib_path.find_hartlib_src(start)
        self.assertIsInstance(cm.exception, CardPipelineError)
        self.assertIn("hart checkout", str(cm.exception))


class ShipmentExport(TempDir):
    def test_the_export_is_the_file_body_without_its_php_header(self):
        code = gcl.export_php()
        self.assertNotIn("<?php", code)
        self.assertFalse(any(line.startswith("//") for line in code.splitlines()))
        self.assertTrue(code.startswith("\nrequire "))
        self.assertTrue(code.endswith("echo count($out);\n"))

    def test_a_file_without_the_open_tag_is_refused(self):
        with self.assertRaisesRegex(CardPipelineError, "does not start with <\\?php"):
            gcl.export_php(self.write("x.php", "echo 1;\n"))

    def test_refresh_runs_the_export_in_the_web_container_and_copies_the_file_out(self):
        dest = self.tmp / "docs" / "cc.json"
        with mock.patch.object(gcl.subprocess, "check_output", return_value="12\n") as run, \
                mock.patch.object(gcl.subprocess, "check_call") as copy:
            self.assertEqual(gcl.refresh_shipments_from_sts(dest), 12)
        self.assertEqual(run.call_args.args[0], ["docker", "exec", "sts-docker-web-1", "php", "-r", gcl.export_php()])
        self.assertEqual(copy.call_args.args[0], ["docker", "cp", "sts-docker-web-1:/tmp/cc_shipments.json", str(dest)])
        self.assertTrue(dest.parent.is_dir())


if __name__ == "__main__":
    unittest.main()
