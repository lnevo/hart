"""archive_catalogue.py: archive.json and the lineage charts checked against the archive catalogue, the
portal's edits reaching the catalogue, and the repo's files passing (lane L6 of ADR-039)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import archive_catalogue as A  # noqa: E402
import serve_portal  # noqa: E402


def row(item_id: str, collection: str = "archive", path: str = "../media/a.jpg", **cells) -> dict:
    return {**{c: "" for c in A.COLUMNS}, "id": item_id, "collection": collection, "path": path,
            "credit_confidence": "none", **cells}


def item(item_id: str, src: str = "../media/a.jpg", **fields) -> dict:
    return {"id": item_id, "src": src, "title": "T", "caption": "C", "credit_confidence": "none", **fields}


class ArchiveTests(unittest.TestCase):
    def test_a_matching_archive_passes_with_absent_and_null_fields_as_empty(self) -> None:
        data = {"items": [item("a", source_url=None)]}
        self.assertEqual(A.check_archive([row("a")], data), [])

    def test_a_changed_credit_or_path_fails(self) -> None:
        problems = A.check_archive([row("a", credit="Ann")], {"items": [item("a", "../media/b.jpg", credit="Bob")]})
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("src is '../media/b.jpg'", problems[0] + problems[1])

    def test_an_item_and_a_row_each_without_the_other_fail(self) -> None:
        problems = A.check_archive([row("a")], {"items": [item("b")]})
        self.assertEqual(sorted(problems), ["archive.json item 'b' is not an archive row of the catalogue",
                                            "catalogue archive row 'a' is not an item of archive.json"])

    def test_a_logo_row_is_not_an_archive_item(self) -> None:
        self.assertEqual(A.check_archive([row("logo-x", "logo")], {"items": []}), [])


class LineageTests(unittest.TestCase):
    ROWS = [row("logo-x", "logo", "../ops/x.png")]

    def test_a_card_cites_its_logo_by_id(self) -> None:
        data = {"lanes": [{"steps": [{"name": "X", "logo_id": "logo-x", "logo": "../ops/x.png"}, {"name": "Y"}]}]}
        self.assertEqual(A.check_lineage(self.ROWS, "a-lineage.json", data), [])

    def test_a_missing_id_or_a_path_that_differs_fails(self) -> None:
        data = {"steps": [{"name": "X", "logo": "../ops/x.png"}, {"name": "Y", "logo_id": "logo-x", "logo": "../y.png"}]}
        problems = A.check_lineage(self.ROWS, "a-lineage.json", data)
        self.assertEqual(len(problems), 2, problems)
        self.assertIn("logo_id '' is not a logo row", problems[0])
        self.assertIn("run with --write", problems[1])


class EditTests(unittest.TestCase):
    """The portal's edit API writes the catalogue with archive.json, so its checks keep passing."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.catalogue, self.archive, self.gallery = d / "c.csv", d / "archive.json", d / "gallery.json"
        A.write([row("a", credit="Ann"), row("logo-x", "logo")], self.catalogue)
        self.archive.write_text(json.dumps({"items": [item("a", credit="Ann")]}), encoding="utf-8")
        self.gallery.write_text(json.dumps({"albums": [{"id": "layout"}], "items": []}), encoding="utf-8")
        self.patches = [mock.patch.object(serve_portal, "CATALOGUE_PATH", self.catalogue),
                        mock.patch.object(serve_portal, "ARCHIVE_PATH", self.archive),
                        mock.patch.object(serve_portal, "GALLERY_PATH", self.gallery),
                        mock.patch.object(serve_portal, "ARCHIVE_LOG", d / "log.jsonl")]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def state(self) -> list[str]:
        return A.check_archive(A.read(self.catalogue), json.loads(self.archive.read_text(encoding="utf-8")))

    def test_a_credit_fix_reaches_the_catalogue(self) -> None:
        code, _ = serve_portal._update_archive_item({"id": "a", "credit": "Bob", "caption": "New"})
        self.assertEqual(code, 200)
        self.assertEqual(next(r for r in A.read(self.catalogue) if r["id"] == "a")["credit"], "Bob")
        self.assertEqual(self.state(), [])

    def test_a_move_to_the_layout_photos_and_back_keeps_the_two_in_step(self) -> None:
        self.assertEqual(serve_portal._move_archive_item_to_layout({"id": "a"})[0], 200)
        self.assertEqual([r["id"] for r in A.read(self.catalogue)], ["logo-x"])
        self.assertEqual(self.state(), [])
        self.assertEqual(serve_portal._update_gallery_item({"src": "../media/a.jpg", "to_archive": True})[0], 200)
        self.assertEqual(self.state(), [])


class RepoTests(unittest.TestCase):
    def test_the_repo_archive_and_lineage_charts_match_the_catalogue(self) -> None:
        self.assertEqual(A.check(), [])

    def test_write_changes_nothing_in_the_repo(self) -> None:
        with mock.patch.object(Path, "write_text") as written:
            A.write_lineage()
        written.assert_not_called()


if __name__ == "__main__":
    unittest.main()
