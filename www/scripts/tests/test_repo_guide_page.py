"""The repository guide's lists and counts follow the checkout, and the build stops on anything it cannot describe."""
import io
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
        self.assertGreater(self.facts["scripts"], 0)
        vals = rg.regions(self.facts)
        self.assertIn("<code>external/</code>", vals["folders"])
        self.assertIn("<code>media/</code>", vals["folders"])

    def test_a_hand_typed_value_is_replaced(self):
        key = "<!--rg:folder-count-->%s<!--/rg-->" % rg.word(len(rg.FOLDERS))
        stale = self.page.replace(key, "<!--rg:folder-count-->nine<!--/rg-->")
        self.assertNotEqual(stale, self.page)
        self.assertEqual(rg.fill(stale, self.facts), self.page)

    def test_unknown_region_stops(self):
        with self.assertRaisesRegex(rg.PageError, "unknown region rg:nope"):
            rg.fill(self.page + "<!--rg:nope-->x<!--/rg-->", self.facts)

    def test_missing_region_stops(self):
        cut = self.page.replace("<!--rg:ops-count-->", "", 1)
        with self.assertRaisesRegex(rg.PageError, "missing .*ops-count"):
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
        del other["parked"]
        with mock.patch.object(rg, "HARTLIB_OTHER", other):
            with self.assertRaisesRegex(rg.PageError, "parked"):
                rg.facts()

    def test_lists_of_any_length_read(self):
        self.assertEqual(rg._and(["a"]), "a")
        self.assertEqual(rg._and(["a", "b", "c"]), "a, b and c")

    def test_folders_come_from_indexed_files(self):
        files = ["a/x.py", "a/b/y.py", "c/z", "top.txt"]
        self.assertEqual(rg._dirs(files, ""), {"a", "c"})
        self.assertEqual(rg._dirs(files, "a/"), {"b"})

    def test_write_fills_a_built_copy(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / rg.PAGE_REL).parent.mkdir(parents=True)
        (tmp / rg.PAGE_REL).write_text(self.page.replace(
            "<!--rg:folder-count-->%s<!--/rg-->" % rg.word(len(rg.FOLDERS)), "<!--rg:folder-count-->nine<!--/rg-->"),
            encoding="utf-8")
        self.assertTrue(rg.write(tmp))
        self.assertEqual((tmp / rg.PAGE_REL).read_text(encoding="utf-8"), self.page)


class Cli(unittest.TestCase):
    def test_check_writes_nothing_and_says_current(self):
        with mock.patch.object(rg, "write", side_effect=AssertionError("wrote")), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(0, rg.main(["--check"]))
        self.assertEqual("repository-guide.html is current\n", out.getvalue())

    def test_an_unknown_argument_is_a_usage_error_not_a_write_run(self):
        for argv in (["--chek"], ["check"], ["--check", "extra"]):
            with self.subTest(argv), mock.patch.object(rg, "write", side_effect=AssertionError("wrote")), \
                    mock.patch("sys.stderr", new_callable=io.StringIO) as err, \
                    self.assertRaises(SystemExit) as stop:
                rg.main(argv)
            self.assertEqual(2, stop.exception.code)
            self.assertIn("usage:", err.getvalue())

    def test_no_argument_is_a_write_run(self):
        with mock.patch.object(rg, "write", return_value=False) as write, \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(0, rg.main([]))
        write.assert_called_once_with(rg.ROOT / "www")
        self.assertEqual("unchanged: www/%s\n" % rg.PAGE_REL, out.getvalue())


if __name__ == "__main__":
    unittest.main()
