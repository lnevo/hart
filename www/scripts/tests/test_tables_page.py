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
        self.assertTrue(self.f["version"].startswith(f"{jv.findtext('major')}.{jv.findtext('minor')}"))

    def test_test_release_and_modifier_are_kept(self):
        raw, root = btb.load()
        jv = root.find("jmriversion")
        jv.find("test").text, jv.find("modifier").text = "3", "ish"
        self.assertEqual(tables_page.facts(raw, root)["version"],
                         f"{jv.findtext('major')}.{jv.findtext('minor')}.3ish")

    def test_detector_named_by_system_name_counts_once(self):
        raw, root = btb.load()
        sensors = {e.findtext("userName"): e.findtext("systemName")
                   for m in root.findall("sensors") for e in m if e.tag == "sensor"}
        lb = next(lb for m in root.findall("layoutblocks") for lb in m
                  if lb.tag == "layoutblock" and lb.get("occupancysensor") == "BS S-1")
        lb.set("occupancysensor", sensors["BS S-1"])
        f = tables_page.facts(raw, root)
        self.assertEqual((f["detectors"], f["sharedCount"]), (self.f["detectors"], self.f["sharedCount"]))

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


class OtherPages(unittest.TestCase):
    """Counts other pages state by hand; update them when tables.xml changes."""

    def test_control_page_counts_match_the_file(self):
        meta = btb.build(btb.load()[1])["meta"]
        text = (btb.WWW / "ai/control.html").read_text(encoding="utf-8")
        m = re.search(r"(\d+) signal masts, (\d+) sections and ([\d,]+) transits", text)
        self.assertIsNotNone(m, "ai/control.html no longer states the counts; drop this test")
        self.assertEqual((int(m.group(1)), int(m.group(2)), int(m.group(3).replace(",", ""))),
                         (meta["masts"], meta["sections"], meta["transits"]),
                         "update the counts in www/ai/control.html")


class Words(unittest.TestCase):
    def test_counts_agree_in_number(self):
        self.assertEqual(tables_page.count(1, "panel", "panels"), "one panel")
        self.assertEqual(tables_page.count(3, "panel", "panels"), "three panels")
        self.assertEqual(tables_page.count(40, "item", "items"), "40 items")

    def test_bar_never_runs_past_its_width(self):
        for obj, pan in ((0.7256, 0.2733), (0.5, 0.5), (0.999, 0.0005), (0.0, 1.0)):
            rects = [(int(x), int(w)) for x, w in re.findall(r'<rect[^>]* x="(\d+)"[^>]* width="(\d+)"', tables_page.bar(obj, pan))]
            self.assertLessEqual(rects[-1][0] + rects[-1][1], tables_page.BAR_X + tables_page.BAR_W, (obj, pan))


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

    def test_missing_conditionalng_action_gives_a_message(self):
        self.xml = self.xml.replace("<systemName>IQDA:AUTO:0002</systemName>\n      </Socket>",
                                    "<systemName>IQDA:GONE</systemName>\n      </Socket>", 1)
        self.src.write_text(self.xml, encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "no connected action"):
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
