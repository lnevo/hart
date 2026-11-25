"""status_counts: wiki/STATUS.md is built from one file per entry in wiki/status/ (ADR-038), with the Counts line
generated from tables.xml and traininfo; --check fails an entry over 60 words and every malformed file."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("status_counts", ROOT / "tools/ops/status_counts.py")
sc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sc)
HOOK_SPEC = importlib.util.spec_from_file_location("worktree_sweep_for_status", ROOT / ".claude/hooks/worktree_sweep.py")
hook = importlib.util.module_from_spec(HOOK_SPEC)
HOOK_SPEC.loader.exec_module(hook)
WT_SPEC = importlib.util.spec_from_file_location("worktrees_for_status", ROOT / "tools/agent/worktrees.py")
wt = sys.modules.setdefault("worktrees_for_status", importlib.util.module_from_spec(WT_SPEC))   # its dataclasses look it up
WT_SPEC.loader.exec_module(wt)

TABLES = """<layout-config>
<signalmasts><signalmast/><signalmast/><virtualsignalmast/></signalmasts>
<sections><section/></sections>
<transits><transit/><transit/></transits>
<signalmastlogics><signalmastlogic><destinationMast/><destinationMast/></signalmastlogic></signalmastlogics>
<entryexitpairs><layoutPanel><source><destination/><destination/></source></layoutPanel></entryexitpairs>
</layout-config>"""


def folder(d: Path, files: dict[str, str]) -> Path:
    base = d / "wiki/status"
    for rel, body in files.items():
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_text(body, encoding="utf-8")
    return base


class StatusCounts(unittest.TestCase):
    def test_counts_and_line(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "t.xml").write_text(TABLES)
            (d / "ti").mkdir()
            for n in ("a.xml", "b.xml", ".DS_Store"):
                (d / "ti" / n).write_text("")
            c = sc.counts(d / "t.xml", d / "ti")
        # the fixture has no CTC data: the USS CTC machine counts as parked while it is (hartlib.parked)
        uss = frozenset({"uss"}) & sc.parked.PARKED
        self.assertEqual(c, {"masts": 3, "real": 2, "virtual": 1, "sections": 1, "transits": 2,
                             "nx": 2, "sml": 1, "dest": 2, "traininfo": 2, "parked": uss})
        self.assertEqual(sc.line(c), "- **Counts:** 3 masts (2 real, 1 virtual), 1 sections, 2 transits, "
                         "2 NX pairs, 1 SML sources with 2 destinations, 2 traininfo files"
                         + (", USS CTC machine parked." if uss else "."))

    def test_line_names_what_is_parked(self):
        c = {"masts": 3, "real": 2, "virtual": 1, "sections": 0, "transits": 0, "nx": 0, "sml": 1, "dest": 2,
             "traininfo": 2, "parked": frozenset({"nx", "dispatcher", "uss"})}
        self.assertEqual(sc.line(c), "- **Counts:** 3 masts (2 real, 1 virtual), sections and transits parked, "
                         "NX pairs parked, 1 SML sources with 2 destinations, 2 traininfo files kept in the repo, "
                         "USS CTC machine parked.")


class Rebase(unittest.TestCase):
    def test_links_lead_to_the_same_file_from_the_page(self):
        entry = ("[a](../../projects/a.md#part) [b](../../../docs/b/) [log](../../STATUS_LOG.md) "
                 "[w](https://x.org/a.md) [top](#top) [m](mailto:a@example.invalid)")
        page = sc.rebase(entry, "wiki/status/current", "wiki")
        self.assertEqual(page, "[a](projects/a.md#part) [b](../docs/b/) [log](STATUS_LOG.md) "
                               "[w](https://x.org/a.md) [top](#top) [m](mailto:a@example.invalid)")
        self.assertEqual(sc.rebase(page, "wiki", "wiki/status/current"), entry)

    def test_words_leave_out_list_markers(self):
        self.assertEqual(sc.words("**A:** one two\n  - three four"), 5)


class Build(unittest.TestCase):
    def build(self, files: dict[str, str]) -> tuple[str, list[str]]:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "t.xml").write_text(TABLES)
            (d / "ti").mkdir()
            text, problems, _n = sc.build(folder(d, files), d / "t.xml", d / "ti")
        return text, problems

    def test_page_order_intros_and_counts(self):
        text, problems = self.build({
            "now/b.md": "**B:** now two\n", "now/a.md": "**A:** now one\n",
            "current/x.md": "**X:** see [p](../../projects/p.md)\n",
            "owed/late.md": "order: 20\n**Late:** second\n", "owed/early.md": "order: 10\n**Early:** first\n",
            "future/f.md": "A goal with\n  - a nested point\n",
        })
        self.assertEqual([], problems)
        head, _, rest = text.partition("## Now\n")
        self.assertEqual(sc.PAGE_HEAD + "\n", head)
        lines = rest.splitlines()
        self.assertEqual(lines[:4], ["", "- **A:** now one", "- **B:** now two", ""])
        self.assertEqual(lines[4:8], ["## Current state", "", "- **X:** see [p](projects/p.md)", sc.START])
        self.assertTrue(lines[8].startswith("- **Counts:** 3 masts"))
        self.assertEqual(lines[9:16], [sc.END, "", "## Owed", "", sc.SECTIONS[2][2], "", "- **Early:** first"])
        self.assertEqual(lines[16:], ["- **Late:** second", "", "## In progress", "", "## Future goals", "",
                                      "- A goal with", "  - a nested point"])
        self.assertTrue(text.endswith("  - a nested point\n"))

    def test_every_malformed_file_is_named(self):
        long = " ".join(["word"] * (sc.MAX_WORDS + 1))
        _text, problems = self.build({
            "now/long.md": long + "\n", "now/ok.md": " ".join(["other"] * sc.MAX_WORDS) + "\n",
            "owed/no-order.md": "**N:** none\n", "current/ordered.md": "order: 5\n**O:** x\n",
            "current/gap.md": "**G:** one\n\ntwo\n", "current/dash.md": "- **D:** x\n", "current/empty.md": "\n",
            "current/notes.txt": "x", "misc/a.md": "x", "stray.md": "x",
        })
        want = ["wiki/status/misc: not a section", "wiki/status/stray.md: not a section",
                f"wiki/status/now/long.md: {sc.MAX_WORDS + 1} words", "wiki/status/owed/no-order.md: an owed entry",
                "wiki/status/current/ordered.md: only an ordered", "wiki/status/current/gap.md: a blank line",
                "wiki/status/current/dash.md: the file holds", "wiki/status/current/empty.md: empty entry",
                "wiki/status/current/notes.txt: not an entry"]
        for w in want:
            self.assertTrue(any(p.startswith(w) for p in problems), (w, problems))
        self.assertEqual(len(want), len(problems), problems)

    def test_two_files_for_one_entry_are_found(self):
        _text, problems = self.build({"current/a.md": "**Same:** one\n", "current/b.md": "**Same:** two\n"})
        self.assertEqual(["the built page has two entries for: Same:"], problems)

    def test_the_repo_entries_pass(self):
        entries, problems = sc.read_entries()
        self.assertEqual([], problems)
        self.assertTrue(entries)


class Main(unittest.TestCase):
    def test_check_writes_nothing_and_passes_on_the_repo(self):
        before = sc.STATUS.read_bytes() if sc.STATUS.exists() else None
        done = subprocess.run([sys.executable, str(ROOT / "tools/ops/status_counts.py"), "--check"], cwd=ROOT,
                              capture_output=True, text=True)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(before, sc.STATUS.read_bytes() if sc.STATUS.exists() else None)

    def test_out_writes_the_page(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "page.md"
            done = subprocess.run([sys.executable, str(ROOT / "tools/ops/status_counts.py"), "--out", str(out),
                                   "--quiet"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            self.assertEqual("", done.stdout)
            self.assertEqual(sc.build()[0], out.read_text(encoding="utf-8"))


class Hook(unittest.TestCase):
    def test_a_failed_build_is_one_line_and_a_good_one_says_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            good, bad = Path(d) / "good", Path(d) / "bad"
            for root, code in ((good, "pass"), (bad, "print('wiki/status/ has problems:'); raise SystemExit(1)")):
                (root / "tools/ops").mkdir(parents=True)
                (root / "wiki").mkdir()
                (root / hook.STATUS_SCRIPT).write_text(code + "\n", encoding="utf-8")
            self.assertEqual([], hook.status_pages(str(good), str(good / "wiki")))
            lines = hook.status_pages(str(good), str(bad / "wiki"))
            self.assertEqual(1, len(lines), lines)
            self.assertIn("wiki/status/ has problems:", lines[0])
            self.assertIn("run make status", lines[0])


class MakeWt(unittest.TestCase):
    def test_a_new_worktree_gets_the_page_and_an_old_checkout_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            new, old = Path(d) / "new", Path(d) / "old"
            for root in (new, old):
                (root / "tools/ops").mkdir(parents=True)
                (root / wt.STATUS_PAGE).write_text("open('wiki/STATUS.md', 'w').write('built')\n", encoding="utf-8")
            (new / "wiki/status").mkdir(parents=True)
            (old / "wiki").mkdir()
            self.assertTrue(wt.build_status_page(new))
            self.assertEqual("built", (new / "wiki/STATUS.md").read_text(encoding="utf-8"))
            self.assertTrue(wt.build_status_page(old))
            self.assertFalse((old / "wiki/STATUS.md").exists())


if __name__ == "__main__":
    unittest.main()
