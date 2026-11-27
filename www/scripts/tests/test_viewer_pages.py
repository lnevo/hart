"""The archive, gallery and wiring viewers (js/archive.js, js/gallery.js, js/wiring.js) and the parts the photo
viewers share (js/photo-viewer.js) in a stub page: runs each *_view_test.js and photo_viewer_test.js with node;
skipped when node is missing."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).parent


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ViewerPages(unittest.TestCase):
    def run_js(self, name: str) -> None:
        r = subprocess.run(["node", str(HERE / name)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_archive(self) -> None:
        self.run_js("archive_view_test.js")

    def test_gallery(self) -> None:
        self.run_js("gallery_view_test.js")

    def test_photo_viewer(self) -> None:
        self.run_js("photo_viewer_test.js")

    def test_wiring(self) -> None:
        self.run_js("wiring_view_test.js")


if __name__ == "__main__":
    unittest.main()
