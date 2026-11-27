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
        self.assertEqual(c, sc.Counts(masts=3, real=2, virtual=1, sections=1, transits=2,
                                      nx=2, sml=1, dest=2, traininfo=2, parked=uss))
        self.assertEqual(sc.line(c), "- **Counts:** 3 masts (2 real, 1 virtual), 1 sections, 2 transits, "
                         "2 NX pairs, 1 SML sources with 2 destinations, 2 traininfo files"
                         + (", USS CTC machine parked." if uss else "."))

    def test_line_names_what_is_parked(self):
        c = sc.Counts(masts=3, real=2, virtual=1, sections=0, transits=0, nx=0, sml=1, dest=2,
                      traininfo=2, parked=frozenset({"nx", "dispatcher", "uss"}))
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

    def test_a_path_with_parentheses_and_a_title(self):
        entry = '[w](../../projects/a_(b).md "T") [x](../../x.md "two words")'
        page = sc.rebase(entry, "wiki/status/current", "wiki")
        self.assertEqual(page, '[w](projects/a_(b).md "T") [x](x.md "two words")')
        self.assertEqual(sc.rebase(page, "wiki", "wiki/status/current"), entry)

    def test_words_leave_out_list_markers(self):
        self.assertEqual(sc.words("**A:** one two\n  - three four"), 5)


COUNTS_FILE = {"current/counts.md": "order: 900\n" + sc.COUNTS_TOKEN + "\n"}


class Build(unittest.TestCase):
    def build(self, files: dict[str, str]) -> tuple[str, list[str]]:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "t.xml").write_text(TABLES)
            (d / "ti").mkdir()
            text, problems, _n = sc.build(folder(d, files), d / "t.xml", d / "ti")
        return text, problems

    def test_page_order_intros_and_counts(self):
        """Every section lists its files by their order: lines, not by name; the Counts line stands where its file is."""
        text, problems = self.build({
            "now/a.md": "order: 20\n**A:** now second\n", "now/b.md": "order: 10\n**B:** now first\n",
            "current/z.md": "order: 10\n**Z:** see [p](../../projects/p.md)\n",
            "current/counts.md": "order: 15\n" + sc.COUNTS_TOKEN + "\n", "current/a.md": "order: 20\n**Y:** last\n",
            "owed/late.md": "order: 20\n**Late:** second\n", "owed/early.md": "order: 10\n**Early:** first\n",
            "future/f.md": "order: 10\nA goal with\n  - a nested point\n",
        })
        self.assertEqual([], problems)
        head, _, rest = text.partition("## Now\n")
        self.assertEqual(sc.PAGE_HEAD + "\n", head)
        lines = rest.splitlines()
        self.assertEqual(lines[:4], ["", "- **B:** now first", "- **A:** now second", ""])
        self.assertEqual(lines[4:8], ["## Current state", "", "- **Z:** see [p](projects/p.md)", sc.START])
        self.assertTrue(lines[8].startswith("- **Counts:** 3 masts"))
        self.assertEqual(lines[9:17], [sc.END, "- **Y:** last", "", "## Owed", "", sc.SECTIONS[2][2], "",
                                       "- **Early:** first"])
        self.assertEqual(lines[17:], ["- **Late:** second", "", "## In progress", "", "## Future goals", "",
                                      "- A goal with", "  - a nested point"])
        self.assertTrue(text.endswith("  - a nested point\n"))

    def test_every_malformed_file_is_named(self):
        long = " ".join(["word"] * (sc.MAX_WORDS + 1))
        _text, problems = self.build({**COUNTS_FILE,
            "now/long.md": "order: 10\n" + long + "\n", "now/ok.md": "order: 20\n" + " ".join(["other"] * sc.MAX_WORDS) + "\n",
            "owed/no-order.md": "**N:** none\n", "current/no-order.md": "**O:** x\n",
            "current/gap.md": "order: 10\n**G:** one\n\ntwo\n", "current/dash.md": "order: 20\n- **D:** x\n",
            "current/empty.md": "order: 30\n\n", "future/counts.md": "order: 10\n" + sc.COUNTS_TOKEN + "\n",
            "current/notes.txt": "x", "misc/a.md": "x", "stray.md": "x",
        })
        want = ["wiki/status/misc: not a section", "wiki/status/stray.md: not a section",
                f"wiki/status/now/long.md: {sc.MAX_WORDS + 1} words", "wiki/status/owed/no-order.md: an entry opens",
                "wiki/status/current/no-order.md: an entry opens", "wiki/status/current/gap.md: a blank line",
                "wiki/status/current/dash.md: the file holds", "wiki/status/current/empty.md: empty entry",
                "wiki/status/future/counts.md: the Counts line stands in current/ only",
                "wiki/status/current/notes.txt: not an entry"]
        for w in want:
            self.assertTrue(any(p.startswith(w) for p in problems), (w, problems))
        self.assertEqual(len(want), len(problems), problems)

    def test_two_entries_with_one_order_number_fail(self):
        _text, problems = self.build({**COUNTS_FILE, "owed/a.md": "order: 10\n**A:** one\n",
                                      "owed/b.md": "order: 10\n**B:** two\n", "now/c.md": "order: 10\n**C:** x\n"})
        self.assertEqual(["wiki/status/owed/: a.md and b.md have the same order: 10; give one a number between its "
                          "neighbours'"], problems)

    def test_the_counts_file_is_needed_once(self):
        _text, problems = self.build({"current/a.md": "order: 10\n**A:** one\n"})
        self.assertEqual(1, len(problems), problems)
        self.assertIn("needs one file whose text is", problems[0])

    def test_read_entry_keeps_an_entry_that_breaks_only_a_text_rule(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "dash.md").write_text("order: 30\n- **D:** x\n")
            (d / "bad.md").write_text("**N:** none\n")
            (d / "counts.md").write_text("order: 5\n" + sc.COUNTS_TOKEN + "\n")
            problems: list[str] = []
            self.assertEqual(sc.Entry("now", d / "dash.md", "- **D:** x", 30), sc.read_entry("now", d / "dash.md", problems))
            self.assertIsNone(sc.read_entry("now", d / "bad.md", problems))
            self.assertIsNone(sc.read_entry("now", d / "counts.md", problems))
            self.assertEqual(sc.Entry("current", d / "counts.md", sc.COUNTS_TOKEN, 5),
                             sc.read_entry("current", d / "counts.md", problems))
        want = ["wiki/status/now/dash.md: the file holds", "wiki/status/now/bad.md: an entry opens",
                "wiki/status/now/counts.md: the Counts line stands in current/ only"]
        self.assertEqual(len(want), len(problems), problems)
        for p, w in zip(problems, want):
            self.assertTrue(p.startswith(w), (w, p))

    def test_two_files_for_one_entry_are_found(self):
        _text, problems = self.build({**COUNTS_FILE, "current/a.md": "order: 10\n**Same:** one\n",
                                      "current/b.md": "order: 20\n**Same:** two\n"})
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


class AtomicWrite(unittest.TestCase):
    def test_the_page_is_replaced_whole_and_no_temp_file_is_left(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "STATUS.md"
            out.write_text("old", encoding="utf-8")
            sc.files.write_atomic(out, "new page\n")
            self.assertEqual("new page\n", out.read_text(encoding="utf-8"))
            self.assertEqual(["STATUS.md"], sorted(p.name for p in Path(d).iterdir()))

    def test_a_failed_write_keeps_the_old_page(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "STATUS.md"
            out.write_text("old", encoding="utf-8")
            with self.assertRaises(TypeError):
                sc.files.write_atomic(out, None)
            self.assertEqual("old", out.read_text(encoding="utf-8"))
            self.assertEqual(["STATUS.md"], sorted(p.name for p in Path(d).iterdir()))


class Hook(unittest.TestCase):
    def test_a_build_past_the_timeout_is_stopped_and_named(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "slow"
            (root / "tools/ops").mkdir(parents=True)
            (root / hook.STATUS_SCRIPT).write_text("import time; time.sleep(30)\n", encoding="utf-8")
            started = hook.start_status_pages(str(root), str(root))
            old, hook.STATUS_TIMEOUT = hook.STATUS_TIMEOUT, 0.5
            try:
                lines = hook.status_lines(started)
            finally:
                hook.STATUS_TIMEOUT = old
            self.assertEqual(1, len(lines), lines)
            self.assertIn("was stopped; run make status", lines[0])

    def test_the_builds_fit_the_hooks_budget(self):
        """They run beside the sweep, so the hook's 60 s (.claude/settings.json) holds the drivers, then the longer
        of the sweep and the builds."""
        self.assertLess(hook.DRIVER_TIMEOUT + max(hook.TIMEOUT, hook.STATUS_TIMEOUT, hook.ORIENT_TIMEOUT), 60)

    def test_a_failed_build_is_one_line_and_a_good_one_says_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            good, bad = Path(d) / "good", Path(d) / "bad"
            for root, code in ((good, "pass"), (bad, "print('wiki/status/ has problems:'); raise SystemExit(1)")):
                (root / "tools/ops").mkdir(parents=True)
                (root / "wiki").mkdir()
                (root / hook.STATUS_SCRIPT).write_text(code + "\n", encoding="utf-8")
            self.assertEqual([], hook.status_lines(hook.start_status_pages(str(good), str(good / "wiki"))))
            lines = hook.status_lines(hook.start_status_pages(str(good), str(bad / "wiki")))
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
