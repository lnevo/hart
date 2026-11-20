"""The repository guide's lists and counts follow the checkout, and the build stops on anything it cannot describe."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import repo_guide_page as rg  # noqa: E402


class RepoGuide(unittest.TestCase):
    def setUp(self):
        self.page = (rg.ROOT / "www" / rg.PAGE_REL).read_text(encoding="utf-8")
        self.facts = rg.facts()

    def test_page_is_current(self):
        self.assertEqual(rg.fill(self.page, self.facts), self.page,
                         "run python3 www/scripts/repo_guide_page.py")

    def test_counts_come_from_the_checkout(self):
        self.assertEqual(self.facts["subs"], len(rg.SUBMODULES))
        self.assertGreater(self.facts["jobs"], 0)
        self.assertGreater(self.facts["scripts"], 0)
        vals = rg.regions(self.facts)
        self.assertEqual(vals["check-jobs"], str(self.facts["jobs"]))
        self.assertIn("<code>external/</code>", vals["folders"])
        self.assertIn("<code>media/</code>", vals["folders"])

    def test_a_hand_typed_value_is_replaced(self):
        stale = self.page.replace("<!--rg:check-jobs-->%s<!--/rg-->" % self.facts["jobs"],
                                  "<!--rg:check-jobs-->30<!--/rg-->")
        self.assertNotEqual(stale, self.page)
        self.assertEqual(rg.fill(stale, self.facts), self.page)

    def test_unknown_region_stops(self):
        with self.assertRaisesRegex(rg.PageError, "unknown region rg:nope"):
            rg.fill(self.page + "<!--rg:nope-->x<!--/rg-->", self.facts)

    def test_missing_region_stops(self):
        cut = self.page.replace("<!--rg:check-jobs-->", "").replace(
            "%s<!--/rg--> checks" % self.facts["jobs"], "%s checks" % self.facts["jobs"])
        with self.assertRaisesRegex(rg.PageError, "missing .*check-jobs"):
            rg.fill(cut, self.facts)

    def test_undescribed_folder_stops(self):
        folders = dict(rg.FOLDERS)
        del folders["wiki"]
        with mock.patch.object(rg, "FOLDERS", folders):
            with self.assertRaisesRegex(rg.PageError, r"not described \['wiki'\]"):
                rg.facts()

    def test_undescribed_submodule_stops(self):
        subs = dict(rg.SUBMODULES)
        del subs["sts-helpers"]
        with mock.patch.object(rg, "SUBMODULES", subs):
            with self.assertRaisesRegex(rg.PageError, "sts-helpers"):
                rg.facts()

    def test_undescribed_hartlib_module_stops(self):
        other = dict(rg.HARTLIB_OTHER)
        del other["boundaries"]
        with mock.patch.object(rg, "HARTLIB_OTHER", other):
            with self.assertRaisesRegex(rg.PageError, "boundaries"):
                rg.facts()

    def test_lists_of_any_length_read(self):
        self.assertEqual(rg._and(["a"]), "a")
        self.assertEqual(rg._and(["a", "b", "c"]), "a, b and c")

    def test_an_untracked_module_is_ignored(self):
        stray = rg.ROOT / "tools/hartlib/src/hartlib/zz_scratch_not_in_git.py"
        stray.write_text("", encoding="utf-8")
        self.addCleanup(stray.unlink)
        self.assertEqual(rg.facts(), self.facts)

    def test_write_fills_a_built_copy(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / rg.PAGE_REL).parent.mkdir(parents=True)
        (tmp / rg.PAGE_REL).write_text(self.page.replace(
            "<!--rg:folder-count-->%s<!--/rg-->" % rg.word(len(rg.FOLDERS)), "<!--rg:folder-count-->nine<!--/rg-->"),
            encoding="utf-8")
        self.assertTrue(rg.write(tmp))
        self.assertEqual((tmp / rg.PAGE_REL).read_text(encoding="utf-8"), self.page)


if __name__ == "__main__":
    unittest.main()
