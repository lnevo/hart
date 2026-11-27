"""Behaviour of the CC/WB label and single-card generators: the shipment reader, the labels a shipment gives, the
STS export's errors and the single card's car argument. Each run writes to a temp directory against a stand-in
sticker sheet."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

from docx import Document  # noqa: E402

import generate_all_cards as gac  # noqa: E402
import generate_cc_waybill_labels as gcl  # noqa: E402
import generate_single_card as gsc  # noqa: E402
from card_errors import CardPipelineError  # noqa: E402


def shipment(**fields: str) -> dict[str, str]:
    row = {name: "" for name in gcl.SHIPMENT_FIELDS}
    row.update(fields)
    return row


def stand_in_sheet(path: Path) -> Path:
    doc = Document()
    doc.add_table(rows=3, cols=3)
    doc.save(str(path))
    return path


class TempDir(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)


class ReadShipments(TempDir):
    def write(self, data: object) -> Path:
        path = self.tmp / "cc.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_a_full_list_reads(self) -> None:
        rows = [shipment(code="S1")]
        self.assertEqual(gcl.read_shipments(self.write(rows)), rows)

    def test_a_missing_field_is_named_with_the_shipment(self) -> None:
        row = shipment(code="S9")
        del row["unload_trk"]
        with self.assertRaisesRegex(CardPipelineError, r"shipment 0 \(S9\) has no unload_trk"):
            gcl.read_shipments(self.write([row]))

    def test_not_a_list_or_not_objects_is_refused(self) -> None:
        with self.assertRaisesRegex(CardPipelineError, "expected a list of shipments, found dict"):
            gcl.read_shipments(self.write({"code": "S1"}))
        with self.assertRaisesRegex(CardPipelineError, "shipment 0 is str"):
            gcl.read_shipments(self.write(["S1"]))

    def test_bad_json_is_named_with_its_cause(self) -> None:
        path = self.tmp / "cc.json"
        path.write_text("[", encoding="utf-8")
        with self.assertRaisesRegex(CardPipelineError, "cannot read the shipments") as cm:
            gcl.read_shipments(path)
        self.assertIsInstance(cm.exception.__cause__, ValueError)


class Labels(unittest.TestCase):
    def test_one_shipment_gives_an_empty_then_a_freight_label(self) -> None:
        s = shipment(code=" S1 ", consignment="Coal", car_code="HT", load_loc="MINE", load_sta="Mine",
                     load_trk="Staging", load_spot="OUT", unload_loc="AEP", unload_rpt="AEP plant",
                     unload_sta="Columbus", unload_trk="T4", unload_spot="in", special=" hold ", load_color="pink")
        with mock.patch.object(gcl, "logo_for_party", lambda party: f"logo:{party}"):
            empty, freight = gcl.labels_from_shipments([s])
        self.assertEqual(empty, {
            "BillKind": "empty", "ShipmentCode": "S1", "ToLocation": "MINE", "Station": "Mine",
            "Track": "STAGING", "Spot": "IN", "Flow": "IN", "CarCode": "HT", "Consignment": "Coal",
            "Color": "pink", "Description": "", "LogoParty": "Mine", "LogoPath": "logo:Mine",
        })
        self.assertEqual(freight["Station"], "AEP plant")  # the reporting station wins over the routing one
        self.assertEqual((freight["Track"], freight["Spot"], freight["Flow"]), ("T4", "in", "IN"))
        self.assertEqual((freight["FromLocation"], freight["FromStation"]), ("MINE", "Mine"))
        self.assertEqual(freight["Special"], "hold")

    def test_a_null_field_reads_as_blank(self) -> None:
        s = shipment(code="S1")
        s["special"] = None  # type: ignore[assignment]
        with mock.patch.object(gcl, "logo_for_party", lambda party: ""):
            self.assertEqual(gcl.labels_from_shipments([s])[1]["Special"], "")

    def test_padding_fills_the_last_page_with_blank_freight_labels(self) -> None:
        padded = gcl.pad_to_page([{"BillKind": "empty"}] * 10)
        self.assertEqual(len(padded), 18)
        self.assertEqual(padded[-1], gcl.FILLER)
        self.assertIsNot(padded[-1], gcl.FILLER)
        self.assertEqual(len(gcl.pad_to_page([{"BillKind": "empty"}] * 9)), 9)


class StsExport(TempDir):
    def test_a_failed_docker_run_is_a_named_error_with_its_cause(self) -> None:
        failure = subprocess.CalledProcessError(1, ["docker"])
        with mock.patch.object(gcl.subprocess, "check_output", side_effect=failure):
            with self.assertRaisesRegex(CardPipelineError, "sts-docker-web-1") as cm:
                gcl.refresh_shipments_from_sts(self.tmp / "cc.json")
        self.assertIs(cm.exception.__cause__, failure)

    def test_no_docker_is_a_named_error(self) -> None:
        with mock.patch.object(gcl.subprocess, "check_output", side_effect=FileNotFoundError("docker")):
            with self.assertRaises(CardPipelineError):
                gcl.refresh_shipments_from_sts(self.tmp / "cc.json")

    def test_an_export_that_prints_no_count_is_refused(self) -> None:
        with mock.patch.object(gcl.subprocess, "check_output", return_value="Warning: x\n"), \
                mock.patch.object(gcl.subprocess, "check_call"):
            with self.assertRaisesRegex(CardPipelineError, "not a count"):
                gcl.refresh_shipments_from_sts(self.tmp / "cc.json")


class CcMain(TempDir):
    def test_main_writes_two_labels_a_shipment_on_whole_pages(self) -> None:
        sheet = stand_in_sheet(self.tmp / "sheet.docx")
        data = self.tmp / "cc.json"
        data.write_text(json.dumps([shipment(code=f"S{i}") for i in range(5)]), encoding="utf-8")
        out = self.tmp / "out" / "labels.docx"
        built: list[int] = []
        with mock.patch.object(gcl.car_paths, "require_sticker_sheet", lambda: sheet), \
                mock.patch.object(gcl.g, "build_cc_waybill_label", lambda cell, *, idx, record: built.append(idx)), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            gcl.main(["--json", str(data), "--output", str(out)])
        self.assertEqual(built, list(range(18)))
        self.assertEqual(len(Document(str(out)).tables), 2)
        self.assertIn("5 shipments → 5 empty + 5 freight labels · 2 sticker pages", stdout.getvalue())


def card_entry(roster_id: str, photo: str) -> gac.CardEntry:
    record: gac.CardRecord = {"Type": "Box Car", "RoadName": "B&O", "RoadNumber": "1", "Description": "Red"}
    return gac.CardEntry(record, None, {"roster_id": roster_id, "source_image": photo})


class SingleCard(TempDir):
    def run_main(self, *argv: str) -> str:
        sheet = stand_in_sheet(self.tmp / "sheet.docx")
        with mock.patch.object(gsc.car_paths, "require_sticker_sheet", lambda: sheet), \
                mock.patch.object(gsc.car_paths, "OUTPUT_DIR", self.tmp / "out"), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            gsc.main(list(argv))
        return stdout.getvalue()

    def test_no_argument_writes_the_golden_card(self) -> None:
        text = self.run_main()
        out = self.tmp / "out" / "HART_Card_NW32800.docx"
        self.assertTrue(out.is_file())
        self.assertIn("N&W 32800 - Black Flatcar · 52'", text)
        self.assertIn("Image: NW32800.png", text)
        self.assertEqual(sorted(p.name for p in out.parent.iterdir()), [out.name])
        body = Document(str(out)).element.body
        self.assertIn("32800", "".join(body.itertext()))

    def test_a_roster_id_writes_that_cars_repository_card(self) -> None:
        with mock.patch.object(gsc.generate_all_cards, "load_cards", lambda: [card_entry("BO1", "IMG_1.png")]):
            text = self.run_main("BO1")
        self.assertTrue((self.tmp / "out" / "HART_Card_BO1.docx").is_file())
        self.assertIn("B&O 1 - Red", text)
        self.assertIn("Image: none (placeholder)", text)

    def test_an_unknown_car_is_named(self) -> None:
        with mock.patch.object(gsc.generate_all_cards, "load_cards", lambda: [card_entry("BO1", "IMG_1.png")]):
            with self.assertRaisesRegex(CardPipelineError, "no photographed car XX9"):
                gsc.repository_card("XX9")

    def test_a_car_on_two_rows_is_refused(self) -> None:
        rows = [card_entry("BO1", "IMG_1.png"), card_entry("BO1", "IMG_2.png")]
        with mock.patch.object(gsc.generate_all_cards, "load_cards", lambda: rows):
            with self.assertRaisesRegex(CardPipelineError, r"BO1 is on 2 photographed rows \(IMG_1.png, IMG_2.png\)"):
                gsc.repository_card("BO1")


if __name__ == "__main__":
    unittest.main()
