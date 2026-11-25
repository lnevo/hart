"""split_status: a one-file STATUS.md splits into one file per entry (ADR-038), and the page built from them is the
canonical page byte for byte; a head, heading or intro the builder does not know, or two entries with one file name,
stop the split."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("split_status", ROOT / "tools/ops/split_status.py")
ss = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ss)
sc = ss.sc

COUNTS = "- **Counts:** 1 masts (1 real, 0 virtual), stale."


def page(now=("- **Waits:** b", "- **Active:** a ([p](projects/p.md#x))"), current_tail=("- **Zed:** z",)) -> str:
    return (sc.PAGE_HEAD + "\n## Now\n\n" + "\n".join(now) + "\n\n## Current state\n\n- **Beta (owner, 2026-11-25, "
            "[ADR-1](decisions/ADR-1.md)):** b\n" + sc.START + "\n" + COUNTS + "\n" + sc.END + "\n"
            + "\n".join(current_tail) + "\n\n## Owed\n\n" + sc.SECTIONS[2][2] + "\n\n- **Second:** two\n  - nested "
            "[d](../docs/d.md)\n\n- **First:** one\n\n\n## In progress\n\n- 3D maps: parts\n\n## Future goals\n\n"
            "- Move the bridge to the Pi. Then more.\n")


class Slug(unittest.TestCase):
    def test_names(self):
        for text, want in (
            ("**tables.xml is generated (owner, 2026-11-20, [ADR-029](decisions/ADR-029.md)):** x", "tables-xml-is-generated"),
            ("**Generated, then the owner's (owner):** x", "generated-then-the-owners"),
            ("**Layout documentation is a live document; the SOQ is frozen:** x", "layout-documentation-is-a-live-document"),
            ("Speed matching (owner, 2026-11-21): read both", "speed-matching"),
            ("3D station maps: multi-colour plates", "3d-station-maps"),
            ("Move the LCOS bridge from the Windows box to the Pi. The Pi is ready", "move-the-lcos-bridge-from-the"),
        ):
            with self.subTest(text=text):
                self.assertEqual(want, ss.slug(text))


class Split(unittest.TestCase):
    def test_canonical_sorts_by_file_name_keeps_owed_order_and_is_stable(self):
        text = ss.canonical(page())
        self.assertEqual(text, ss.canonical(text))
        self.assertLess(text.index("**Active:**"), text.index("**Waits:**"))
        self.assertLess(text.index("**Second:**"), text.index("**First:**"))
        self.assertLess(text.index("**Zed:**"), text.index(sc.START))      # the Counts block ends Current state
        self.assertNotIn("\n\n\n", text)

    def test_the_built_page_is_the_canonical_page(self):
        text = ss.canonical(page())
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "wiki/status"
            self.assertEqual(8, ss.split(text, folder))
            self.assertEqual("order: 10\n**Second:** two\n  - nested [d](../../../docs/d.md)\n",
                             (folder / "owed/second.md").read_text(encoding="utf-8"))
            self.assertEqual("**Active:** a ([p](../../projects/p.md#x))\n",
                             (folder / "now/active.md").read_text(encoding="utf-8"))
            self.assertTrue((folder / "README.md").is_file())
            entries, problems = sc.read_entries(folder)
            self.assertEqual([], problems)
            self.assertEqual(text, sc.page(entries, COUNTS))
            ss.split(text, folder)                                          # re-runnable: replaces, adds nothing
            self.assertEqual(8, len(sc.read_entries(folder)[0]))

    def test_a_head_heading_or_intro_change_stops_it(self):
        for bad in (page().replace("One or two lines", "Two lines"), page().replace("## Owed", "## Debts"),
                    page().replace(sc.SECTIONS[2][2], "Any order.")):
            with self.subTest(bad=bad[:30]), self.assertRaises(ss.SplitError):
                ss.parse(bad)

    def test_two_entries_with_one_file_name_stop_it(self):
        with self.assertRaises(ss.SplitError):
            ss.canonical(page(now=("- **Active:** a", "- **Active (owner):** b")))

    def test_the_readme_links_resolve(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "wiki/status"
            ss.split(ss.canonical(page()), folder)
            (Path(d) / "wiki/decisions").mkdir()
            (Path(d) / "wiki/decisions/ADR-038-one-file-per-status-entry.md").write_text("x")
            (Path(d) / "wiki/STATUS_LOG.md").write_text("x")
            readme = (folder / "README.md").read_text(encoding="utf-8")
            for m in sc.LINK.finditer(readme):
                with self.subTest(link=m.group(2)):
                    self.assertTrue((folder / m.group(2)).exists())


if __name__ == "__main__":
    unittest.main()
