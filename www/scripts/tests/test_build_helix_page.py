"""build_helix_page.py: every STL on disk is in the index, and the status page links the files it names. Needs
markdown and trimesh (the root .venv); skipped without them."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
HAVE = all(importlib.util.find_spec(m) for m in ("markdown", "trimesh"))
if HAVE:
    import build_helix_page as helix  # noqa: E402


@unittest.skipUnless(HAVE, "markdown and trimesh not installed")
class Helix(unittest.TestCase):
    def test_the_repo_files_are_all_classified(self) -> None:
        self.assertIn("router_depth_block.stl", helix.listed_files())

    def test_an_unclassified_or_missing_file_stops_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "stray.stl").write_bytes(b"")
            with mock.patch.object(helix, "SRC", Path(d)), self.assertRaises(helix.HelixPageError) as cm:
                helix.listed_files()
        self.assertIn("unclassified: ['stray.stl']", str(cm.exception))
        self.assertIn("router_depth_block.stl", str(cm.exception))

    def test_the_status_page_links_published_files(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / helix.STATUS).write_text("# Status\n\nSee `a.stl` and `b.stl`.\n", encoding="utf-8")
            with mock.patch.object(helix, "DOCS", Path(d)):
                page = helix.status_page("{{TITLE}}|{{PAGE}}|{{BODY}}", {"a.stl": "stl/a.stl"})
        self.assertIn('<a href="stl/a.stl"><code>a.stl</code></a>', page)
        self.assertIn("<code>b.stl</code>", page)
        self.assertIn("<h2>Status</h2>", page)
        self.assertTrue(page.startswith("Helix build status|helix-status|"))


@unittest.skipUnless(HAVE, "markdown and trimesh not installed")
class MainExitTest(unittest.TestCase):
    def test_main_exits_with_the_list_of_files(self) -> None:
        with mock.patch.object(helix, "listed_files", side_effect=helix.HelixPageError("unclassified: ['x.stl']")), \
                self.assertRaises(SystemExit) as cm:
            helix.main()
        self.assertEqual(cm.exception.code, "unclassified: ['x.stl']")


if __name__ == "__main__":
    unittest.main()
