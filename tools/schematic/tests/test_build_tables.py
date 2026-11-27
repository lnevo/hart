"""build_tables.py: tables.xml generated from the template, devices.csv, the Layout Editor build and the discovered
Signal Mast Logic (ADR-029). The command runs the real build over the repo's committed files under repo_read_only (a
write into the repo fails the test); the files it writes are pointed at a temporary folder."""
from __future__ import annotations

import contextlib
import functools
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))     # repo_read_only.py

import build_tables as bt  # noqa: E402
import publish_draft as pd  # noqa: E402
from hartlib import paths, tables, tables_sml  # noqa: E402
from hartlib import tables_build as tb  # noqa: E402
from repo_read_only import repo_read_only  # noqa: E402


def plugin_here() -> bool:
    try:
        bt.ble.plugin()
    except bt.ble.BuildError:
        return False
    return True


@functools.lru_cache(maxsize=None)
def generated() -> tuple[bytes, dict]:
    with repo_read_only(), pd.cache_on(), contextlib.redirect_stdout(io.StringIO()):
        return bt.generate()


def run(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with repo_read_only(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bt.main(list(argv))
    return code, out.getvalue(), err.getvalue()


@unittest.skipUnless(plugin_here(), "the schematic-maps plugin is not checked out")
class Generated(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_the_committed_tables_are_what_it_writes(self) -> None:
        data, counts = generated()
        self.assertEqual(paths.REPO_TABLES_XML.read_bytes(), data)
        self.assertEqual(1, counts["digicon masts"])                # Mast 6LB, on the wired head IH432
        code, out, _err = run("--check")
        self.assertEqual(0, code)
        self.assertIn("current", out)

    def test_a_stale_file_fails_the_check(self) -> None:
        stale = self.tmp / "tables.xml"
        stale.write_bytes(paths.REPO_TABLES_XML.read_bytes().replace(b"Clock running", b"Clock stopped"))
        with mock.patch.object(bt, "OUT", stale):
            code, _out, err = run("--check")
        self.assertEqual(1, code)
        self.assertIn("STALE", err)

    def test_the_output_holds_its_sources_once(self) -> None:
        root = tables.loads(generated()[0]).root
        bt.check(root)                                   # the invariants hold on the committed output
        # the full panel and its three band panels (band_panels.py, 2026-11-22)
        self.assertEqual(["HART Railroad", *tables.BAND_PANEL_NAMES.values()],
                         [p.get("name") for p in root.findall("LayoutEditor")])
        self.assertEqual("LayoutEditor", list(tables.elements(root))[-1].tag)
        dup = tables.loads(generated()[0]).root
        dup.find("memories").append(tables.section(dup, "memories", "memory")[0].__copy__())
        with self.assertRaisesRegex(tb.TablesBuildError, "names given twice: .*memory 'IMCURRENTTIME' x2"):
            bt.check(dup)

    def test_a_missing_master_bean_fails_the_invariants(self) -> None:
        root = tables.loads(generated()[0]).root
        sec = root.find("signalheads")
        sec.remove(next(h for h in sec if tables.system_name(h) == "IH432"))
        with self.assertRaisesRegex(tb.TablesBuildError, "missing from the output: IH432"):
            bt.check(root)

    def test_discovery_writes_its_file_then_the_tables(self) -> None:
        """--discovered-from a Store: its logic replaces the discovered file and tables.xml follows. The committed
        tables stand in for a discovery Store (their logic is the discovered one), with the Digicon destinations
        enabled as stock Discover stores them (the build disables them again), so both files come out the same."""
        store = self.tmp / "store.xml"
        doc = tables.load(paths.REPO_TABLES_XML)
        masts = tables_sml.digicon_masts(doc.root)
        self.assertTrue(tables_sml.disable_digicon(doc.root, masts)[1])        # the committed tables hold them disabled
        for logic in tables.mast_logics(doc.root):
            if logic.get("source") in masts:
                for dest in logic.findall("destinationMast"):
                    dest.find("enabled").text = "yes"
        store.write_bytes(doc.tobytes())
        out, disc = self.tmp / "tables.xml", self.tmp / "discovered_sml.xml"
        with mock.patch.object(bt, "OUT", out), mock.patch.object(tables_sml, "DISCOVERED", disc), \
                mock.patch.object(bt.ble, "build", wraps=bt.ble.build), pd.cache_on():
            code, stdout, err = run("--discovered-from", str(store))
        self.assertEqual(0, code, err)
        self.assertEqual(paths.REPO_TABLES_XML.read_bytes(), out.read_bytes())
        self.assertEqual(tables_sml.DISCOVERED.read_bytes(), disc.read_bytes())
        self.assertIn("wrote", stdout)

    def test_a_store_without_logic_writes_nothing(self) -> None:
        store = self.tmp / "store.xml"
        doc = tables.load(paths.REPO_TABLES_XML)
        box = doc.root.find("signalmastlogics")
        for logic in box.findall("signalmastlogic"):
            box.remove(logic)
        store.write_bytes(doc.tobytes())
        out, disc = self.tmp / "tables.xml", self.tmp / "discovered_sml.xml"
        with mock.patch.object(bt, "OUT", out), mock.patch.object(tables_sml, "DISCOVERED", disc):
            code, _stdout, err = run("--discovered-from", str(store))
        self.assertEqual(2, code)
        self.assertIn("no Signal Mast Logic", err)
        self.assertFalse(out.exists() or disc.exists())

    def discovered_copy(self, edit) -> Path:
        """A copy of the discovered file with `edit` (on its text) applied."""
        disc = self.tmp / "discovered_sml.xml"
        text = tables_sml.DISCOVERED.read_text(encoding="utf-8")
        new = edit(text)
        self.assertNotEqual(text, new)
        disc.write_text(new, encoding="utf-8")
        return disc

    def test_a_renamed_mast_stops_the_build_but_not_the_discovery_base(self) -> None:
        """A discovered file that names a mast the tables no longer hold stops the normal build loudly, and the
        discovery base, which reads no discovered file, still builds, so run_sml_discover.sh can repair it."""
        disc = self.discovered_copy(lambda t: t.replace('destination="Mast 24RA"', 'destination="Mast 24RX"', 1))
        out = self.tmp / "tables.xml"
        with mock.patch.object(bt, "OUT", out), mock.patch.object(tables_sml, "DISCOVERED", disc):
            code, _stdout, err = run("--check")
            self.assertEqual(2, code)
            self.assertIn("names masts the tables do not hold (Mast 24RX)", err)
            code, stdout, err = run("--discovery-base")
        self.assertEqual(0, code, err)
        self.assertIn("discovery base", stdout)
        root = tables.read(out)
        self.assertEqual([], tables.mast_logics(root))
        self.assertFalse([m for m in tables.masts(root) if m.find("properties") is not None])
        with mock.patch.object(bt, "OUT", out):
            self.assertEqual(1, run("--check")[0])          # the base is stale until discovery has run

    def test_a_mast_with_no_discovered_logic_stops_the_build(self) -> None:
        """Every head mast is a logic's source and every virtual mast a logic's destination (missing_logic): a mast
        added since discovery fails the build, naming the mast and the wrapper to run."""
        def drop_source(text: str) -> str:
            start = text.index('<signalmastlogic source="Mast 4RA">')
            return text[:start] + text[text.index("</signalmastlogic>", start) + len("</signalmastlogic>\n  "):]
        disc = self.discovered_copy(drop_source)
        with mock.patch.object(tables_sml, "DISCOVERED", disc):
            code, _stdout, err = run("--check")
        self.assertEqual(2, code)
        self.assertIn("1 mast(s) with no discovered logic they need (Mast 4RA)", err)
        self.assertIn("run_sml_discover.sh", err)

    def test_a_missing_store_stops_naming_it(self) -> None:
        code, _out, err = run("--discovered-from", str(self.tmp / "none.xml"))
        self.assertEqual(2, code)
        self.assertIn("none.xml", err)

    def test_a_missing_template_section_stops_the_build(self) -> None:
        doc = tables.load(tb.TEMPLATE)
        doc.root.remove(doc.root.find("memories"))
        bad = self.tmp / "template.xml"
        bad.write_bytes(doc.tobytes())
        with mock.patch.object(tb, "TEMPLATE", bad), mock.patch.object(tb.read_template, "__defaults__", (bad,)), \
                mock.patch.object(tb.base, "__defaults__", (None, bad, None)):
            code, _out, err = run("--check")
        self.assertEqual(2, code)
        self.assertIn("no <memories", err)


class Skipped(unittest.TestCase):
    def test_check_skips_without_the_plugin_unless_required(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "SCHEMATIC_REQUIRED"}   # CI sets it for every job
        with mock.patch.object(bt.ble, "plugin", side_effect=bt.ble.BuildError("no plugin")):
            with mock.patch.dict(os.environ, env, clear=True):
                code, out, _err = run("--check")
            self.assertEqual((0, True), (code, "SKIPPED" in out))
            with mock.patch.dict(os.environ, {"SCHEMATIC_REQUIRED": "1"}):
                self.assertEqual(bt.EXIT_NO_PLUGIN, run("--check")[0])
            self.assertEqual(bt.EXIT_NO_PLUGIN, run()[0])         # a write needs the plugin


class ReviewFlagRetired(unittest.TestCase):
    """--review skipped the staging fingerprint, retired with the staging guard."""

    def test_review_is_no_option(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            bt.main(["--review"])
        self.assertEqual(stop.exception.code, 2)

    def test_the_discovery_wrapper_passes_no_review(self):
        """build_tables.py has no --review any more; HART_TABLES_REVIEW only lets the wrapper skip its own approval
        check (check_approved.py le-panel), never passed to build_tables.py.
        Source text on purpose: the wrapper drives PanelPro on a host, so no test can run it; what it passes to
        build_tables.py is visible only in its lines."""
        text = (Path(__file__).resolve().parents[3] / "jmri/layouts/hart/scripts/run_sml_discover.sh").read_text()
        self.assertNotIn("--review", text)
        self.assertEqual([line for line in text.splitlines() if "REVIEW" in line and "build_tables.py" in line], [])
        notes = [line for line in text.splitlines() if "build_tables.py" in line and ("Restore" in line or "Fix" in line)]
        self.assertEqual(len(notes), 2)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(plugin_here(), "the schematic-maps plugin is not checked out")
class DiscoveryDigest(unittest.TestCase):
    """discovery_digest keeps what stock SML discovery reads and drops geometry."""

    @classmethod
    def setUpClass(cls) -> None:
        with repo_read_only(), pd.cache_on(), contextlib.redirect_stdout(io.StringIO()):
            cls.base, _ = bt.generate(with_logic=False)

    def digest(self, mutate=None) -> str:
        if mutate is None:
            return bt.discovery_digest(self.base)
        root = bt.ET.fromstring(self.base)
        mutate(root)
        return bt.discovery_digest(bt.ET.tostring(root, encoding="utf-8"))

    def test_geometry_and_window_size_keep_the_digest(self) -> None:
        def move(root):
            for el in root.iter():
                for a in ("x", "y", "xcen", "ycen", "xa", "ya", "xb", "yb", "xc", "yc", "xd", "yd"):
                    if a in el.attrib:
                        el.set(a, str(float(el.get(a)) + 7.5))
            le = root.find("LayoutEditor")
            le.set("windowwidth", "1111")
            le.set("panelheight", "999")
            le.set("defaulttrackcolor", "red")
            arc = root.find(".//tracksegment[@arc]")
            arc.set("angle", "12")
        self.assertEqual(self.digest(), self.digest(move))

    def test_a_connection_change_changes_it(self) -> None:
        def swap(root):
            segs = root.findall(".//tracksegment")
            segs[0].set("connect1name", segs[1].get("connect1name"))
        self.assertNotEqual(self.digest(), self.digest(swap))

    def test_a_block_change_changes_it(self) -> None:
        def block(root):
            root.find(".//tracksegment").set("blockname", "NO-SUCH-BLOCK")
        self.assertNotEqual(self.digest(), self.digest(block))

    def test_a_mast_slot_change_changes_it(self) -> None:
        def slot(root):
            pp = root.find(".//positionablepoint[@eastboundsignalmast]")
            pp.set("eastboundsignalmast", "Other mast")
        self.assertNotEqual(self.digest(), self.digest(slot))

    def test_a_turnout_type_change_changes_it(self) -> None:
        def kind(root):
            lt = root.find(".//layoutturnout")
            lt.set("type", "99")
        self.assertNotEqual(self.digest(), self.digest(kind))
