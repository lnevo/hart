"""Behaviour tests for publications/rebuild_crew_instructions.py: crew loading, the engine block height and a sheet."""
import importlib
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

PUB = Path(__file__).resolve().parents[1] / "publications"
sys.path.insert(0, str(PUB))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from PIL import Image  # noqa: E402

import rebuild_crew_instructions as rci  # noqa: E402


def crew(pub_id, photo="", revision="A"):
    return {"train": pub_id[3:], "pub_id": pub_id, "file": f"{pub_id}.docx", "subtitle": "Local",
            "engine": "HART 1", "photo": photo, "intro": "Work the island.", "steps": ["Pick up.", "Set out."],
            "publication": {"title": "Crew Instructions", "revision": revision, "effective": "1 May"}}


class LoadCrews(unittest.TestCase):
    def load(self, crews, photos_dir):
        with mock.patch.object(rci.crew_master, "crews", lambda master: crews), \
             mock.patch.object(rci, "ROSTER_PHOTOS", photos_dir):
            return rci.load_crews({})

    def test_photo_paths_resolve_under_the_roster(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "loco.jpg").write_bytes(b"x")
            out = self.load([crew("CI-A", "loco.jpg"), crew("CI-B")], Path(tmp))
        self.assertEqual(out[0]["photo"], Path(tmp) / "loco.jpg")
        self.assertIsNone(out[1]["photo"])
        self.assertEqual(out[1]["out"], rci.DOCS / "CI-B.docx")

    def test_missing_named_photo_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(rci.CrewSheetError, "CI-A: photo .*gone.jpg is not a file"):
                self.load([crew("CI-A", "gone.jpg")], Path(tmp))

    def test_no_crews_is_refused(self):
        with self.assertRaisesRegex(rci.CrewSheetError, "no crew jobs"):
            self.load([], Path("/nonexistent"))


class SharedPublication(unittest.TestCase):
    def test_agreeing_lines(self):
        pub = rci.shared_publication([crew("CI-A"), crew("CI-B")])
        self.assertEqual(pub, {"title": "Crew Instructions", "revision": "A", "effective": "1 May"})

    def test_disagreeing_revision_names_the_crew(self):
        with self.assertRaisesRegex(rci.CrewSheetError, "crew CI-B prints"):
            rci.shared_publication([crew("CI-A"), crew("CI-B", revision="B")])

    def test_repo_master_agrees(self):
        sheets = rci.load_sheets()
        self.assertEqual(sheets.publication, rci.shared_publication(sheets.crews))
        self.assertTrue(all(c["out"].parent == rci.DOCS for c in sheets.crews))

    def test_import_reads_no_file(self):
        with mock.patch.object(rci.crew_master, "load", side_effect=AssertionError("read at import")):
            importlib.reload(rci)


class EngineBlockHeight(unittest.TestCase):
    def test_no_photo_uses_the_placeholder_height(self):
        self.assertEqual(rci._engine_block_height_in({"pub_id": "CI-A", "photo": None}), rci.ENGINE_BLOCK_NO_PHOTO_IN)

    def test_photo_height_follows_its_aspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.png"
            Image.new("RGB", (200, 100)).save(path)
            self.assertAlmostEqual(rci._engine_block_height_in({"pub_id": "CI-A", "photo": path}), 1.85 * 0.5 + 0.14)

    def test_unreadable_photo_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.png"
            path.write_bytes(b"not an image")
            with self.assertRaisesRegex(rci.CrewSheetError, "cannot read photo") as ctx:
                rci._engine_block_height_in({"pub_id": "CI-A", "photo": path})
            self.assertIsNotNone(ctx.exception.__cause__)


class RebuildCrew(unittest.TestCase):
    def build(self, tmp: Path, photo: Path | None):
        pub: rci.Publication = {"title": "Crew Instructions", "revision": "A", "effective": "1 May"}
        sheet: rci.CrewSheet = {
            "train": "T", "pub_id": "CI-T", "subtitle": "Local", "engine": "HART 1", "photo": photo,
            "intro": "Work the island.", "steps": ["Pick up.", "Set out."], "publication": {"title": "Crew Instructions", "revision": "A", "effective": "1 May"},
            "out": tmp / "ci.docx",
        }
        self.assertEqual(rci.rebuild_crew(sheet, pub), tmp / "ci.docx")
        return Document(str(tmp / "ci.docx"))

    def test_sheet_without_photo_prints_the_placeholder_and_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.build(Path(tmp), None)
        engine, steps = doc.tables[0], doc.tables[1]
        self.assertEqual(engine.rows[0].cells[0].text, "No assigned\nengine photo")
        self.assertIn("Engine:  HART 1", engine.rows[0].cells[1].text)
        self.assertEqual([p.text for p in steps.rows[0].cells[0].paragraphs],
                         ["CREW STEPS", "1.  Pick up.", "2.  Set out."])
        for cell in engine.rows[0].cells:
            self.assertEqual([el.get(qn("w:val")) for el in cell._tc.tcPr.findall(qn("w:vAlign"))], ["center"])
        tblp = steps._tbl.tblPr.find(qn("w:tblpPr"))
        self.assertEqual(tblp.get(qn("w:vertAnchor")), "page")
        self.assertIn("CI-T  ·  Rev A", doc.sections[0].footer.paragraphs[0].text)

    def test_sheet_with_photo_places_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = Path(tmp) / "loco.png"
            Image.new("RGB", (200, 100)).save(photo)
            doc = self.build(Path(tmp), photo)
        self.assertEqual(len(doc.tables[0].rows[0].cells[0]._tc.findall(".//" + qn("w:drawing"))), 1)
