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

    def test_lcos_heads_follow_the_coordinators_rule(self):
        rule = ja._lcos(ja.ROOT)
        self.assertEqual(Path(rule.is_head.__code__.co_filename).resolve(), (ja.ROOT / "jmri/scripts/sml_lcos.py").resolve())   # no copy
        self.assertEqual(ja.lcos_heads("IF$shsm:basic:one-searchlight(IH432)", rule), ["IH432"])   # node 4, signal 32: 6LB's head
        self.assertEqual(ja.lcos_heads("IF$shsm:basic:two-searchlight(IH432)(IH433)", rule), ["IH432", "IH433"])
        self.assertEqual(ja.lcos_heads("IF$shsm:basic:one-searchlight(IH431)", rule), [])      # signal 31 is below the LCOS range
        self.assertEqual(ja.lcos_heads("IF$shsm:basic:one-searchlight(IH932)", rule), [])      # node 9 is not an octal number
        self.assertEqual(ja.lcos_heads("IF$vsm:basic:one-low($1001)", rule), [])     # a staging mast has no heads
        self.assertEqual(ja.lcos_heads("IF$shsm:basic:one-low(IH:HART:C1:4RA)", rule), [])   # an internal head

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

    def listing_copy(self) -> Path:
        """A tree holding the jython list, its reader and the split scripts' files: what host_lists reads."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        coordinator = [p.relative_to(ja.ROOT).as_posix() for script in (ja.COORDINATOR, ja.PANEL_STATUS)
                       for p in ja.coordinator.files(ja.ROOT / script)]
        for rel in coordinator + [ja.JYTHON_LIST, ja.JYTHON_READER]:
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ja.ROOT / rel, tmp / rel)
        return tmp

    def test_every_host_follows_the_one_jython_list(self):
        tmp = self.listing_copy()
        listing = tmp / ja.JYTHON_LIST
        text = listing.read_text(encoding="utf-8")
        listing.write_text(text.replace("pi jmri/layouts/hart/scripts/mimic_relay.py",
                                        "startup jmri/layouts/hart/scripts/mimic_relay.py"), encoding="utf-8")
        hosts = ja.host_lists(tmp)
        for host in ("Pi", "Windows", "Mac"):                # a startup row is every host's
            self.assertIn("mimic_relay.py", hosts[host], host)
        self.assertNotIn("sml_beans.py", hosts["Pi"])        # a sibling row is a part, not a script
        listing.write_text(text.replace("pi jmri/layouts/hart/scripts/mimic_relay.py",
                                        "macpi jmri/layouts/hart/scripts/mimic_relay.py"), encoding="utf-8")
        hosts = ja.host_lists(tmp)
        self.assertIn("mimic_relay.py", hosts["Pi"])         # a macpi row is the Mac's and the Pi's, not Windows'
        self.assertIn("mimic_relay.py", hosts["Mac"])
        self.assertNotIn("mimic_relay.py", hosts["Windows"])
        listing.write_text(text, encoding="utf-8")
        hosts = ja.host_lists(tmp)
        self.assertIn("mimic_relay.py", hosts["Pi"])         # a pi row is the Pi's alone
        self.assertNotIn("mimic_relay.py", hosts["Mac"] | hosts["Windows"])
        listing.write_text(text + "module jmri/scripts/x.py\n", encoding="utf-8")
        with self.assertRaisesRegex(ja.PageError, "unknown role 'module'"):
            ja.host_lists(tmp)

    def test_coordinator_modules_are_parts_not_scripts(self):
        parts = ja._siblings(ja.ROOT)
        self.assertIn("sml_beans.py", parts)
        self.assertIn("panel_status_turnouts.py", parts)       # panel_status.py's PARTS are parts too
        for host, names in self.facts["hosts"].items():
            self.assertFalse(names & parts, host)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / ja.COORDINATOR).parent.mkdir(parents=True)
        shutil.copy(ja.ROOT / ja.COORDINATOR, tmp / ja.COORDINATOR)      # the script without its modules
        with self.assertRaisesRegex(ja.PageError, "no .py beside it"):
            ja._siblings(tmp)
        with self.assertRaisesRegex(ja.PageError, "sml_lcos.py: missing"):
            ja._lcos(tmp)

    def test_every_part_of_a_split_script_is_on_the_page(self):
        for script, parts in self.facts["parts"].items():
            self.assertTrue(parts, script)
            for m in parts:
                self.assertIn("<code>%s.py</code>" % m, self.page, script)

    def test_parts_sentence_counts_its_modules(self):
        self.assertEqual(ja._parts_sentence(("a",)),
                         "One module beside it holds the rest of its code and is deployed with it: <code>a.py</code>.")
        self.assertEqual(ja._parts_sentence(("a", "b", "c")),
                         "Three modules beside it hold the rest of its code and are deployed with it: "
                         "<code>a.py</code>, <code>b.py</code> and <code>c.py</code>.")

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
