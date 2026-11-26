"""Behaviour tests for publications/rebuild_crew_instructions.py: crew loading and the engine block height."""
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

PUB = Path(__file__).resolve().parents[1] / "publications"
sys.path.insert(0, str(PUB))

from PIL import Image  # noqa: E402

import rebuild_crew_instructions as rci  # noqa: E402


def crew(pub_id, photo="", revision="A"):
    return {"pub_id": pub_id, "file": f"{pub_id}.docx", "photo": photo,
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
        self.assertEqual(rci.PUBLICATION, rci.shared_publication(rci.CREWS))


class EngineBlockHeight(unittest.TestCase):
    def test_no_photo_uses_the_placeholder_height(self):
        self.assertEqual(rci._engine_block_height_in({"photo": None}), rci.ENGINE_BLOCK_NO_PHOTO_IN)

    def test_photo_height_follows_its_aspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.png"
            Image.new("RGB", (200, 100)).save(path)
            self.assertAlmostEqual(rci._engine_block_height_in({"photo": path}), 1.85 * 0.5 + 0.14)

    def test_unreadable_photo_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.png"
            path.write_bytes(b"not an image")
            with self.assertRaisesRegex(rci.CrewSheetError, "cannot read photo") as ctx:
                rci._engine_block_height_in({"pub_id": "CI-A", "photo": path})
            self.assertIsNotNone(ctx.exception.__cause__)
