"""The JMRI additions page's counts and host lists follow the repository, and the build stops on what it cannot place."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import jmri_additions_page as ja  # noqa: E402


class JmriAdditions(unittest.TestCase):
    def setUp(self):
        self.page = (ja.ROOT / "www" / ja.PAGE_REL).read_text(encoding="utf-8")
        self.facts = ja.facts()

    def test_page_is_current(self):
        self.assertEqual(ja.fill(self.page, self.facts), self.page,
                         "run python3 www/scripts/jmri_additions_page.py")

    def test_mast_counts_add_up(self):
        f = self.facts
        self.assertEqual(f["planned"], f["planned-mu"] + f["planned-staging"])
        self.assertEqual(f["planned"], f["lit"] + f["hidden"])
        self.assertLessEqual(f["wired"], f["lit"])

    def test_lcos_head_rule_matches_the_coordinator(self):
        lo, hi = ja._lcos_range(ja.ROOT)
        self.assertTrue(ja.is_lcos_head("432", lo, hi))       # node 4, signal 32: Mast 6LB's head
        self.assertFalse(ja.is_lcos_head("431", lo, hi))      # signal 31 is below the LCOS range
        self.assertFalse(ja.is_lcos_head("932", lo, hi))      # node 9 is not an octal number

    def test_every_listed_script_reaches_a_host(self):
        hosts = self.facts["hosts"]
        for s in ja.SCRIPTS:
            self.assertTrue(any(s in v for v in hosts.values()), s)
        self.assertEqual(ja._hosts_cell("mimic_relay.py", {"Pi": {"mimic_relay.py"}, "Windows": set(), "Mac": set()}),
                         "the Pi only")
        self.assertEqual(ja._hosts_cell("x.py", {"Pi": {"x.py"}, "Windows": set(), "Mac": {"x.py"}}),
                         "the Pi and the Mac")
        with self.assertRaisesRegex(ja.PageError, "no host installs it"):
            ja._hosts_cell("x.py", {"Pi": set(), "Windows": set(), "Mac": set()})

    def test_windows_reads_without_the(self):
        self.assertEqual(ja._hosts_cell("x.py", {"Pi": {"x.py"}, "Windows": {"x.py"}, "Mac": set()}),
                         "the Pi and Windows")

    def test_a_list_must_close_on_its_own_line(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        coordinator = [p.relative_to(ja.ROOT).as_posix() for p in ja.coordinator.files(ja.ROOT / ja.COORDINATOR)]
        for rel in [r for r, _ in ja.HOST_LISTS.values()] + coordinator:
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ja.ROOT / rel, tmp / rel)
        pi = tmp / ja.HOST_LISTS["Pi"][0]
        text = pi.read_text(encoding="utf-8")
        pi.write_text(text.replace("JYTHON=(", "JYTHON=(  # (see the README)", 1), encoding="utf-8")
        self.assertEqual(ja.host_lists(tmp), self.facts["hosts"])   # a comment's bracket does not end the list

    def test_coordinator_modules_are_parts_not_scripts(self):
        parts = ja._siblings(ja.ROOT)
        self.assertIn("sml_beans.py", parts)
        for host, names in self.facts["hosts"].items():
            self.assertFalse(names & parts, host)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / ja.COORDINATOR).parent.mkdir(parents=True)
        shutil.copy(ja.ROOT / ja.COORDINATOR, tmp / ja.COORDINATOR)      # the script without its modules
        with self.assertRaisesRegex(ja.PageError, "no .py beside it"):
            ja._siblings(tmp)
        with self.assertRaisesRegex(ja.PageError, "no .py beside it"):
            ja._lcos_range(tmp)

    def test_unknown_and_missing_regions_stop(self):
        with self.assertRaisesRegex(ja.PageError, "unknown region ja:nope"):
            ja.fill(self.page + "<!--ja:nope-->x<!--/ja-->", self.facts)
        cut = self.page.replace("<!--ja:plant-turnouts-->", "", 1)
        with self.assertRaisesRegex(ja.PageError, "missing .*plant-turnouts"):
            ja.fill(cut, self.facts)

    def test_write_fills_a_built_copy(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / ja.PAGE_REL).parent.mkdir(parents=True)
        stale = self.page.replace("<!--ja:planned-masts-->%s<!--/ja-->" % self.facts["planned"],
                                  "<!--ja:planned-masts-->23<!--/ja-->")
        self.assertNotEqual(stale, self.page)
        (tmp / ja.PAGE_REL).write_text(stale, encoding="utf-8")
        self.assertTrue(ja.write(tmp))
        self.assertEqual((tmp / ja.PAGE_REL).read_text(encoding="utf-8"), self.page)


if __name__ == "__main__":
    unittest.main()
