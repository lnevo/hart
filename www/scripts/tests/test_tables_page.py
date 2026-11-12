"""The tables file page and its browser data follow tables.xml, and the check catches drift."""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import build_tables_browser as btb  # noqa: E402
import prepare_github_pages  # noqa: E402
import tables_page  # noqa: E402


class Copy(unittest.TestCase):
    """A temp copy of the portal's two outputs and of tables.xml, to change freely."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.www = self.tmp / "www"
        for rel in (btb.OUT_REL, btb.PAGE_REL):
            (self.www / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(btb.WWW / rel, self.www / rel)
        self.src = self.tmp / "tables.xml"
        shutil.copy(btb.SRC, self.src)
        self.xml = self.src.read_text(encoding="utf-8")

    def edit(self, old, new):
        self.assertIn(old, self.xml)
        self.xml = self.xml.replace(old, new, 1)
        self.src.write_text(self.xml, encoding="utf-8")

    def page(self):
        return (self.www / btb.PAGE_REL).read_text(encoding="utf-8")

    def region(self, key, text=None):
        m = re.search(r"<!--tf:%s-->(.*?)<!--/tf-->" % re.escape(key), text or self.page(), re.S)
        self.assertIsNotNone(m, key)
        return m.group(1)


class Facts(unittest.TestCase):
    def setUp(self):
        raw, root = btb.load()
        self.f = tables_page.facts(raw, root)

    def test_version_comes_from_the_file(self):
        raw, root = btb.load()
        jv = root.find("jmriversion")
        self.assertEqual(self.f["version"], f"{jv.findtext('major')}.{jv.findtext('minor')}")

    def test_size_and_lines_match_the_file(self):
        raw = btb.SRC.read_bytes()
        self.assertEqual(self.f["bytes"], len(raw))
        self.assertEqual(self.f["lines"], len(raw.splitlines()))

    def test_section_shares_add_up(self):
        self.assertAlmostEqual(sum(r["share"] for r in self.f["rows"]), 1.0, places=6)
        self.assertAlmostEqual(sum(self.f["share"].values()), 1.0, places=6)

    def test_every_top_level_section_is_counted(self):
        raw, root = btb.load()
        self.assertEqual(self.f["top"], len(list(root)))

    def test_shared_detectors_account_for_the_extra_blocks(self):
        self.assertGreater(self.f["layoutBlocks"], self.f["detectors"])
        self.assertGreater(self.f["sharedCount"], 0)


class CommittedPage(unittest.TestCase):
    def test_committed_page_and_data_are_current(self):
        self.assertEqual(btb.stale(), [], "run python3 www/scripts/build_tables_browser.py")

    def test_fill_is_idempotent(self):
        raw, root = btb.load()
        f = tables_page.facts(raw, root)
        once = tables_page.fill(btb.outputs()[btb.PAGE_REL], f)
        self.assertEqual(tables_page.fill(once, f), once)

    def test_no_region_left_as_a_placeholder(self):
        page = (btb.WWW / btb.PAGE_REL).read_text(encoding="utf-8")
        for key, body in tables_page.REGION.findall(page):
            self.assertTrue(body.strip(), key)


class Drift(Copy):
    def test_copy_starts_current(self):
        self.assertEqual(btb.stale(self.www, self.src), [])

    def test_new_layout_block_makes_the_page_stale(self):
        self.edit("</layoutblocks>", '  <layoutblock systemName="ILB999" occupancysensor="BS K-1">'
                  "<systemName>ILB999</systemName><userName>Test block</userName></layoutblock>\n  </layoutblocks>")
        self.assertIn(btb.PAGE_REL, btb.stale(self.www, self.src))
        before = int(self.region("layout-blocks"))
        btb.write(self.www, self.src)
        self.assertEqual(btb.stale(self.www, self.src), [])
        self.assertEqual(int(self.region("layout-blocks")), before + 1)

    def test_new_jmri_version_reaches_the_page(self):
        self.edit("<minor>16</minor>", "<minor>18</minor>")
        btb.write(self.www, self.src)
        self.assertEqual(self.region("version"), "5.18")

    def test_unknown_section_stops_the_build(self):
        self.edit("  <filehistory", "  <newthing />\n  <filehistory")
        with self.assertRaisesRegex(SystemExit, "newthing"):
            btb.outputs(self.www, self.src)

    def test_renamed_example_stops_the_build(self):
        self.edit("<userName>Switch 35</userName>", "<userName>Switch 35X</userName>")
        with self.assertRaisesRegex(SystemExit, "Switch 35"):
            btb.outputs(self.www, self.src)

    def test_example_with_one_feedback_sensor_stops_the_build(self):
        # The DCC twin carries the same sensors and comes first; change the turnout itself.
        self.xml = re.sub(r'feedback="TWOSENSOR"([^>]*>\s*<systemName>M2T108<)', r'feedback="ONESENSOR"\1', self.xml)
        self.src.write_text(self.xml, encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "two sensors"):
            btb.outputs(self.www, self.src)

    def test_unknown_region_stops_the_build(self):
        page = self.page().replace("<!--tf:top-->", "<!--tf:nonsense-->x<!--/tf--><!--tf:top-->", 1)
        (self.www / btb.PAGE_REL).write_text(page, encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "tf:nonsense"):
            btb.outputs(self.www, self.src)

    def test_removed_region_stops_the_build(self):
        page = re.sub(r"<!--tf:ctc-columns-->(.*?)<!--/tf-->", r"\1", self.page(), count=1)
        (self.www / btb.PAGE_REL).write_text(page, encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "tf:ctc-columns"):
            btb.outputs(self.www, self.src)


class SiteBuild(Copy):
    def test_site_build_refreshes_a_stale_page_and_data(self):
        (self.www / btb.PAGE_REL).write_text(
            re.sub(r"(<!--tf:lines-->)(.*?)(<!--/tf-->)", r"\g<1>1\3", self.page()), encoding="utf-8")
        (self.www / btb.OUT_REL).write_text("{}\n", encoding="utf-8")
        prepare_github_pages._refresh_tables_page(self.www)
        self.assertEqual(btb.stale(self.www), [])

    def test_site_build_skips_a_tree_without_the_page(self):
        (self.www / btb.PAGE_REL).unlink()
        prepare_github_pages._refresh_tables_page(self.www)
        self.assertFalse((self.www / btb.PAGE_REL).exists())


if __name__ == "__main__":
    unittest.main()
