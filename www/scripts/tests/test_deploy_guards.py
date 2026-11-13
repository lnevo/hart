"""Deploy guards: a build without the photo mirrors, or with no last-deploy record, must stop."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import check_portal_build as check  # noqa: E402
import prepare_github_pages as build  # noqa: E402


def _portal(tmp: str, items: dict[str, list[dict]]) -> Path:
    portal = Path(tmp) / "repo" / "www"
    (portal / "data").mkdir(parents=True)
    for name, rows in items.items():
        (portal / "data" / name).write_text(json.dumps({"items": rows}), encoding="utf-8")
    return portal


class MissingMirrorsTest(unittest.TestCase):
    def test_mirror_photo_without_original_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            portal = _portal(tmp, {"gallery.json": [{"src": "../media/photos-layout/a.jpg"}]})
            self.assertEqual(build._missing_mirrors(portal)[-1], "data/gallery.json: ../media/photos-layout/a.jpg")

    def test_present_original_and_tracked_assets_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            portal = _portal(
                tmp,
                {
                    "fleet-gallery.json": [{"src": "../ops/car-cards/x.png"}, {"src": "assets/panels/p.png"}],
                },
            )
            original = portal.parent / "ops" / "car-cards" / "x.png"
            original.parent.mkdir(parents=True)
            original.write_bytes(b"x")
            self.assertEqual([m for m in build._missing_mirrors(portal) if m.startswith("data/")], [])

    def test_private_and_review_items_are_not_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            portal = _portal(
                tmp,
                {
                    "archive.json": [
                        {"src": "../media/hart-research/a.jpg", "public": False},
                        {"src": "../media/hart-research/b.jpg", "bucket": "review"},
                    ]
                },
            )
            self.assertEqual([m for m in build._missing_mirrors(portal) if m.startswith("data/")], [])


class PreviousManifestTest(unittest.TestCase):
    def _run(self, *extra: str) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "search-index.json").write_text('{"version": 1, "generated": "2026-01-01T00:00:00Z", "records": []}')
            argv = ["check_portal_build.py", "--dist", str(dist), "--previous", str(Path(tmp) / "absent.json"), *extra]
            with mock.patch.object(sys, "argv", argv), mock.patch.object(check.share_cards, "report", return_value=0):
                with redirect_stdout(io.TextIOWrapper(io.BytesIO())), redirect_stderr(io.StringIO()):
                    return check.main()

    def test_missing_previous_manifest_stops(self):
        self.assertEqual(self._run(), 3)

    def test_force_accepts_missing_previous_manifest(self):
        self.assertEqual(self._run("--allow-drop"), 0)


if __name__ == "__main__":
    unittest.main()
