"""Staged intake: flags, approval, records, and the locomotive repository."""
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "card_pipeline"))

import cars  # noqa: E402
import intake_stages as st  # noqa: E402
import locos  # noqa: E402


STAND_IN = "blue moon"  # tests use a stand-in phrase; the real name is never written down


def stand_in_name():
    import hashlib
    from unittest import mock

    import private_name

    return mock.patch.object(private_name, "FINGERPRINTS",
                             frozenset({hashlib.sha256(STAND_IN.encode()).hexdigest()}))


def review_row(**kw):
    row = {c: "" for c in st.REVIEW_COLUMNS}
    row.update(photo="IMG_1.png", kind="car", reporting_marks="N&W", road_number="32800",
               roster_id="NW32800", crop_status="ok", blur="1500", status="pending")
    row.update(kw)
    return row


def find(rows, rid):
    return next((r for r in rows if r.get("roster_id") == rid), None)


class FlagTests(unittest.TestCase):
    def flags(self, row, repo=(), seen=None):
        return st.flag_row(row, {"N&W", "B&O"}, list(repo), find, {} if seen is None else seen)

    def test_clean_photo_has_no_flags(self):
        self.assertEqual(self.flags(review_row()), [])

    def test_unreadable_number_and_blur(self):
        flags = self.flags(review_row(road_number="", roster_id="", blur="5"))
        self.assertEqual(flags, ["blurry", "no-number"])

    def test_unknown_road(self):
        self.assertIn("road-not-in-fleet", self.flags(review_row(reporting_marks="XYZ")))

    def test_duplicate_of_photographed_car_and_of_batch(self):
        repo = [{"roster_id": "NW32800", "source_image": "IMG_9106.png"}]
        self.assertIn("duplicate-has-photo", self.flags(review_row(), repo))
        seen = {"NW32800": "IMG_0.png"}
        self.assertIn("same-id-as-IMG_0.png", self.flags(review_row(), seen=seen))

    def test_unphotographed_car_is_not_a_duplicate(self):
        repo = [{"roster_id": "NW32800", "source_image": ""}]
        self.assertEqual(self.flags(review_row(), repo), [])

    def test_private_name(self):
        with stand_in_name():
            self.assertIn("private-name", self.flags(review_row(full_name="Blue Moon boxcar")))

    def test_bad_crop(self):
        self.assertIn("crop-fallback", self.flags(review_row(crop_status="fallback")))


class KindTests(unittest.TestCase):
    def flags(self, row):
        return st.flag_row(row, {"N&W"}, [], find, {})

    def test_loco_words_in_ocr_flag_a_car(self):
        self.assertIn("maybe-loco", self.flags(review_row(ocr_text="EMD GP20 HORSEPOWER 2000")))
        self.assertNotIn("maybe-loco", self.flags(review_row(ocr_text="LD LMT 100000 CAPY")))
        self.assertNotIn("maybe-loco", self.flags(review_row(kind="loco", ocr_text="EMD GP20")))

    def test_ai_type_disagreeing_with_kind(self):
        rows = [review_row(photo="a.png"), review_row(photo="b.png", kind="loco")]
        st.apply_ai_notes(rows, {"a.png": {"marks": "N&W", "number": "32800", "type": "Diesel"},
                                 "b.png": {"marks": "N&W", "number": "32800", "type": "Boxcar"}})
        self.assertEqual(rows[0]["flags"], "ai-says-loco")
        self.assertEqual(rows[1]["flags"], "ai-says-car")

    def test_kind_command_switches_and_clears_flags(self):
        class Ctx:
            def guess_roster_id(self, row, kind):
                return "NW 32800" if kind == "loco" else "NW32800"

        with tempfile.TemporaryDirectory() as tmp:
            st.BATCH_ROOT = Path(tmp)
            out = st.batch_dir("k")
            out.mkdir()
            st.write_csv(out / "review.csv", st.REVIEW_COLUMNS,
                         [review_row(photo="a.png", flags="maybe-loco;blurry"), review_row(photo="b.png")])
            st.cmd_kind(SimpleNamespace(batch="k", kind="loco", photos=["a.png"]), Ctx())
            a, b = st.read_csv(out / "review.csv")
            self.assertEqual((a["kind"], a["roster_id"], a["flags"]), ("loco", "NW 32800", "blurry"))
            self.assertEqual(b["kind"], "car")
            with self.assertRaises(SystemExit):
                st.cmd_kind(SimpleNamespace(batch="k", kind="loco", photos=["zz.png"]), Ctx())


class PhotoTests(unittest.TestCase):
    def test_cars_and_locos_found_and_known_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in ("a.png", "b.jpg", "loco_c.png", "known.png", "notes.txt"):
                (tmp / name).write_bytes(b"x")
            repo = [{"source_image": "known.png"}]
            found = st.photos_to_review(tmp, repo, {".png", ".jpg"})
            self.assertEqual([(p.name, k) for p, k in found],
                             [("a.png", "car"), ("b.jpg", "car"), ("loco_c.png", "loco")])

    def test_converted_copy_is_one_photo(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.heic").write_bytes(b"x")
            (tmp / "a.png").write_bytes(b"x")
            found = st.photos_to_review(tmp, [], {".png", ".heic"})
            self.assertEqual(len(found), 1)


class ApproveRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        st.BATCH_ROOT = Path(self.tmp.name)
        out = st.batch_dir("b1")
        out.mkdir()
        st.write_csv(out / "review.csv", st.REVIEW_COLUMNS, [
            review_row(photo="ok.png"),
            review_row(photo="bad.png", flags="blurry", roster_id="NW1"),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_approve_takes_only_unflagged(self):
        st.cmd_approve(SimpleNamespace(batch="b1", no_ai=True), None)
        rows = {r["photo"]: r["status"] for r in st.read_csv(st.batch_dir("b1") / "review.csv")}
        self.assertEqual(rows, {"ok.png": "approved", "bad.png": "pending"})

    def test_records_refuses_while_pending(self):
        st.cmd_approve(SimpleNamespace(batch="b1", no_ai=True), None)
        with self.assertRaises(SystemExit):
            st.cmd_records(SimpleNamespace(batch="b1", dry_run=False, allow_pending=False), FakeCtx())

    def test_records_writes_manifest_and_marks_recorded(self):
        st.cmd_approve(SimpleNamespace(batch="b1", no_ai=True), None)
        ctx = FakeCtx()
        args = SimpleNamespace(batch="b1", dry_run=False, allow_pending=True)
        st.cmd_records(args, ctx)
        self.assertEqual(ctx.recorded, ["ok.png"])
        manifest = st.read_csv(st.batch_dir("b1") / "manifest.csv")
        self.assertEqual([(m["photo"], m["outcome"]) for m in manifest], [("ok.png", "new car NW32800")])
        statuses = {r["photo"]: r["status"] for r in st.read_csv(st.batch_dir("b1") / "review.csv")}
        self.assertEqual(statuses["ok.png"], "recorded")
        st.cmd_records(args, ctx)  # a second run records nothing twice
        self.assertEqual(ctx.recorded, ["ok.png"])

    def test_dry_run_writes_nothing(self):
        st.cmd_approve(SimpleNamespace(batch="b1", no_ai=True), None)
        ctx = FakeCtx()
        st.cmd_records(SimpleNamespace(batch="b1", dry_run=True, allow_pending=True), ctx)
        self.assertFalse(ctx.written)
        self.assertFalse((st.batch_dir("b1") / "manifest.csv").exists())


class AiNotesTests(unittest.TestCase):
    def test_agreement_and_disagreement(self):
        rows = [review_row(photo="a.png"), review_row(photo="b.png")]
        unknown = st.apply_ai_notes(rows, {
            "a.png": {"marks": "N & W", "number": "32800", "type": "Flatcar"},
            "b.png": {"marks": "N&W", "number": "32808", "note": "last digit is an 8"}})
        self.assertEqual(unknown, [])
        self.assertEqual(rows[0]["flags"], "")
        self.assertEqual(rows[1]["flags"], "ai-disagrees")
        self.assertEqual(rows[1]["status"], "pending")
        self.assertEqual(rows[1]["road_number"], "32800")  # OCR value untouched

    def test_rerun_does_not_duplicate_flag(self):
        rows = [review_row(photo="b.png")]
        for _ in range(2):
            st.apply_ai_notes(rows, {"b.png": {"marks": "N&W", "number": "1"}})
        self.assertEqual(rows[0]["flags"], "ai-disagrees")

    def test_unknown_photo_reported(self):
        self.assertEqual(st.apply_ai_notes([review_row()], {"zz.png": {}}), ["zz.png"])

    def test_approve_waits_for_ai_unless_told(self):
        with tempfile.TemporaryDirectory() as tmp:
            st.BATCH_ROOT = Path(tmp)
            out = st.batch_dir("b2")
            out.mkdir()
            st.write_csv(out / "review.csv", st.REVIEW_COLUMNS, [review_row(photo="a.png")])
            with self.assertRaises(SystemExit):
                st.cmd_approve(SimpleNamespace(batch="b2", no_ai=False), None)
            st.apply_ai_notes(rows := st.read_csv(out / "review.csv"),
                              {"a.png": {"marks": "N&W", "number": "32800"}})
            st.write_csv(out / "review.csv", st.REVIEW_COLUMNS, rows)
            st.cmd_approve(SimpleNamespace(batch="b2", no_ai=False), None)
            self.assertEqual(st.read_csv(out / "review.csv")[0]["status"], "approved")


class FakeCtx:
    def __init__(self):
        self.recorded, self.written = [], False

    def read_rows(self):
        return [], []

    def read_queue(self):
        return []

    def write_rows(self, *_):
        self.written = True

    def write_queue(self, *_):
        self.written = True

    def record_car(self, r, rows, columns, queue, dry_run):
        if not dry_run:
            self.recorded.append(r["photo"])
        return f"new car {r['roster_id']}"

    def record_loco(self, r, dry_run):
        return "loco"


class RealCarRecordTests(unittest.TestCase):
    def test_new_car_row_gets_roster_id_and_queue(self):
        columns = ["source_image", "reporting_marks", "road_name", "road_number", "car_type",
                   "roster_id", "roster_road", "roster_length_ft", "roster_weight_oz",
                   "roster_weight_tons", "crop_status", "cropped_image", "ocr_zoom_image",
                   "match_confidence", "notes", "car_class", "color", "capy_lbs", "ld_lmt_lbs",
                   "lt_wt_lbs", "built", "full_name", "ocr_text"]
        rows, queue = [], []
        row = review_row(car_type="Flatcar", roster_length_ft="52")
        outcome = cars.record_car(row, rows, columns, queue, False)
        self.assertEqual(outcome, "new car NW32800")
        self.assertEqual(rows[0]["source_image"], "IMG_1.png")
        self.assertEqual(queue[0]["roster_id"], "NW32800")

    def test_existing_unphotographed_car_gets_the_photo(self):
        columns = ["source_image", "reporting_marks", "road_name", "road_number", "car_type",
                   "roster_id", "roster_road", "roster_length_ft", "roster_weight_oz",
                   "roster_weight_tons", "crop_status", "cropped_image", "ocr_zoom_image",
                   "match_confidence", "notes", "car_class", "color", "capy_lbs", "ld_lmt_lbs",
                   "lt_wt_lbs", "built", "full_name", "ocr_text"]
        rows = [{c: "" for c in columns} | {"roster_id": "NW32800", "road_number": "32800",
                                             "reporting_marks": "N&W", "road_name": "N&W"}]
        queue = []
        outcome = cars.record_car(review_row(car_type="Flatcar"), rows, columns, queue, False)
        self.assertEqual(outcome, "photo added to NW32800")
        self.assertEqual(rows[0]["source_image"], "IMG_1.png")
        self.assertEqual(queue[0]["reason"], "photo added")


ENGINES = """<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet href="/xml/XSLT/operations-engines.xsl" type="text/xsl"?>
<!DOCTYPE operations-config SYSTEM "/xml/DTD/operations-engines.dtd">
<operations-config>
  <models><model name="GP20" /></models>
  <engines>
    <engine id="POHC2091" roadName="POHC" roadNumber="2091" type="Diesel" length="56" locationId="3" moves="7" model="GP20" />
  </engines>
</operations-config>
"""


class LocoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        locos.LOCOS, locos.LOCO_QUEUE = t / "locos.csv", t / "queue.csv"
        locos.ENGINE_ROSTER = t / "engines.xml"
        locos.ENGINE_ROSTER.write_text(ENGINES)
        locos.ROSTER_PHOTOS, locos.IMPORT_LIST = t / "photos", t / "new_locos.json"

    def tearDown(self):
        self.tmp.cleanup()

    def full(self, **kw):
        base = dict(road_name="NW", road_number="1776", dcc_address="1776", model="SW1200",
                    loco_type="Diesel", length_ft="45", weight_tons="124", hp="1200")
        base.update(kw)
        return base

    def test_ids(self):
        self.assertEqual(locos.loco_roster_id("BO", "572"), "BO 572")
        self.assertEqual(locos.ops_id("NWR", "06"), "NWR06")

    def test_add_then_update_keeps_one_row_and_one_queue_entry(self):
        rows, queue = [], []
        self.assertEqual(locos.upsert(rows, queue, {"road_name": "NW", "road_number": "1776"}), "added")
        self.assertEqual(locos.upsert(rows, queue, {"road_name": "NW", "road_number": "1776",
                                                    "model": "SW1200"}), "updated")
        self.assertEqual((len(rows), len(queue), rows[0]["model"]), (1, 1, "SW1200"))

    def test_missing_fields(self):
        self.assertEqual(locos.missing_fields({"road_name": "NW", "road_number": "1"}),
                         ["dcc_address", "model", "loco_type", "length_ft"])

    def test_merge_engines_adds_and_keeps_state(self):
        row = {**self.full(), "roster_id": "NW 1776"}
        existing = {**self.full(road_name="POHC", road_number="2091", model="GP20"), "roster_id": "POHC 2091"}
        added = locos.merge_engines(locos.ENGINE_ROSTER, [existing, row])
        self.assertEqual(added, ["NW1776"])
        root = ET.parse(locos.ENGINE_ROSTER).getroot()
        found = {e.get("id"): e for e in root.findall("./engines/engine")}
        self.assertEqual(found["POHC2091"].get("moves"), "7")
        self.assertIn("SW1200", [m.get("name") for m in root.find("models")])
        self.assertTrue(locos.ENGINE_ROSTER.read_text().startswith("<?xml"))
        self.assertIn("<!DOCTYPE operations-config", locos.ENGINE_ROSTER.read_text())

    def test_roster_entry_long_address_from_number(self):
        entry = locos.roster_entry({**self.full(dcc_address="1776"), "roster_id": "NW 1776"})
        self.assertTrue(entry["long_address"])
        short = locos.roster_entry({**self.full(dcc_address="3"), "roster_id": "NW 3"})
        self.assertFalse(short["long_address"])

    def test_publish_refuses_incomplete_and_publishes_complete(self):
        rows, queue = [], []
        locos.upsert(rows, queue, {"road_name": "NW", "road_number": "1776"})
        locos.write_table(locos.LOCOS, locos.COLUMNS, rows)
        locos.write_table(locos.LOCO_QUEUE, locos.QUEUE_COLUMNS, queue)
        with self.assertRaises(SystemExit):
            locos.cmd_publish(None, None)
        rows[0].update(self.full())
        locos.write_table(locos.LOCOS, locos.COLUMNS, rows)
        locos.cmd_publish(None, None)
        entries = json.loads(locos.IMPORT_LIST.read_text())
        self.assertEqual([e["id"] for e in entries], ["NW 1776"])
        self.assertTrue(locos.read_queue()[0]["published"])
        locos.cmd_publish(None, None)  # nothing is published twice
        self.assertEqual(len(json.loads(locos.IMPORT_LIST.read_text())), 1)


if __name__ == "__main__":
    unittest.main()
