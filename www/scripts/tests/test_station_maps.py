"""Station maps: every generated sheet is published from docs/ops/stations, the crew data names only
published sheets, the schematic is published, no page links the removed preview pages, and the current maps carry
the schematic's revision and date."""
from __future__ import annotations

import contextlib
import datetime
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/hartlib/src"))
sys.path.insert(0, str(ROOT / "ops/hart-ops/publications"))
import build_crew_json  # noqa: E402
import crew_master  # noqa: E402

from hartlib import layer_files, map_revision  # noqa: E402

PREFS = map_revision.page_prefs()           # the main_upper section of preferences.json
PUBLISHED = json.loads((ROOT / "www/scripts/published-files.json").read_text())
CREW = json.loads((ROOT / "www/data/crew.json").read_text())
MAPS = ROOT / "www/crew/maps"
FOLDER = "crew/maps/generated-sheets/"


def page_prefs(data, section):
    """A preferences.json in `data` whose main_upper section, the page's, is `section`."""
    (data / "preferences.json").write_text(json.dumps({"_sections": True, "staging": {}, "main_upper": section}))
    return layer_files.Section("preferences", map_revision.PAGE_SHEET, data)


class StationMapsTest(unittest.TestCase):
    def test_every_station_svg_is_published_from_docs(self):
        svgs = sorted((ROOT / "docs/ops/stations").glob("*.svg"))
        self.assertTrue(svgs)
        for svg in svgs:
            self.assertEqual(PUBLISHED.get(FOLDER + svg.name), f"docs/ops/stations/{svg.name}")

    def test_crew_data_uses_published_sheets(self):
        for m in CREW["maps"]:
            self.assertTrue(m["sheets"], m["id"])
            for sheet in m["sheets"]:
                self.assertIn(sheet, CREW["sheets"])
        for sheet in CREW["sheets"]:
            self.assertIn(FOLDER + sheet + ".svg", PUBLISHED)

    def test_schematic_is_published_with_its_pdf(self):
        sc = CREW["schematic"]
        self.assertEqual(PUBLISHED[sc["svg"]], "docs/ops/schematic-system-draft.svg")
        self.assertEqual(PUBLISHED[sc["pdf"]], "docs/ops/schematic-system-draft.pdf")
        self.assertNotIn(">DRAFT<", (ROOT / PUBLISHED[sc["svg"]]).read_text())

    def test_every_map_has_a_live_and_an_archive_page(self):
        for m in CREW["maps"]:
            self.assertTrue((MAPS / m["id"] / "index.html").is_file(), m["id"])
            self.assertTrue((MAPS / "archive" / m["id"] / "index.html").is_file(), m["id"])

    def test_no_preview_pages_remain(self):
        self.assertEqual(list(MAPS.rglob("generated.html")), [])
        for page in MAPS.rglob("*.html"):
            self.assertNotRegex(page.read_text(), r"generated\.html|preview", str(page))


class MapRevisionTest(unittest.TestCase):
    def test_current_maps_carry_the_schematic_revision(self):
        prefs = PREFS.read()
        day = datetime.date.fromisoformat(prefs["date"])
        rev, effective = str(prefs["revision"]), f"{day.day} {day.strftime('%B')} {day.year}"
        self.assertEqual(CREW["schematic"]["revision"], rev)
        self.assertEqual(CREW["schematic"]["effective"], effective)
        pubs = json.loads((ROOT / "www/data/publications.json").read_text())["items"]
        by_page = {i.get("page"): i for i in pubs}
        self.assertEqual(by_page[CREW["schematic"]["svg"]]["revision"], rev)
        for m in CREW["maps"]:
            page = f"crew/maps/{m['id']}/index.html"
            self.assertEqual(by_page[page]["revision"], rev, m["id"])
            self.assertIn(f">Publication {m['pub']} · Revision {rev} · Effective {effective}</p>",
                          (ROOT / "www" / page).read_text(), m["id"])
        self.assertEqual(map_revision.drift(), [])

    def test_archive_pages_keep_their_own_revision(self):
        planned = map_revision.planned(ROOT / "www")
        for m in CREW["maps"]:
            self.assertNotIn(MAPS / "archive" / m["id"] / "index.html", planned)
        self.assertIn("Revision A", (MAPS / "archive/west-yard/index.html").read_text())

    def test_fields_from_the_title_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefs = page_prefs(Path(tmp), {"revision": 12, "date": "2026-12-01"})
            self.assertEqual(map_revision.fields(prefs), ("12", "1 December 2026"))
            page_prefs(Path(tmp), {"revision": 12, "date": "1 Dec"})
            with self.assertRaisesRegex(ValueError, r"preferences.json\[main_upper\]: date '1 Dec' is not YYYY-MM-DD"):
                map_revision.fields(prefs)
            page_prefs(Path(tmp), {"date": "2026-12-01"})
            with self.assertRaisesRegex(ValueError, "no revision"):
                map_revision.fields(prefs)
            (Path(tmp) / "preferences.json").write_text(json.dumps({"_sections": True, "staging": {}}))
            with self.assertRaisesRegex(ValueError, "no section 'main_upper'"):
                map_revision.fields(prefs)
            (Path(tmp) / "sheet.preferences.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "move its keys there"):
                map_revision.page_prefs(Path(tmp))


class MapRevisionCopy(unittest.TestCase):
    """A temp copy of the files map_revision owns, plus one archive page, to change freely."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        self.www = tmp / "www"
        rels = ["data/crew.json", "data/publications.json", "crew/maps/archive/west-yard/index.html"]
        rels += [f"crew/maps/{m['id']}/index.html" for m in CREW["maps"]]
        for rel in rels:
            (self.www / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / "www" / rel, self.www / rel)
        self.prefs = page_prefs(tmp, {"revision": 99, "date": "2026-12-01"})   # a revision no sheet has yet

    def test_new_revision_is_drift_until_applied(self):
        archive = (self.www / "crew/maps/archive/west-yard/index.html").read_text()
        stale = map_revision.drift(self.www, self.prefs)
        self.assertEqual(len(stale), 2 + len(CREW["maps"]))
        self.assertEqual(sorted(map_revision.apply(self.www, self.prefs)), sorted(stale))
        self.assertEqual(map_revision.drift(self.www, self.prefs), [])
        self.assertIn(">Publication SM-02 · Revision 99 · Effective 1 December 2026</p>",
                      (self.www / "crew/maps/west-yard/index.html").read_text())
        crew = json.loads((self.www / "data/crew.json").read_text())
        self.assertEqual((crew["schematic"]["revision"], crew["schematic"]["effective"]), ("99", "1 December 2026"))
        self.assertEqual(crew["maps"][0]["revision"], CREW["maps"][0]["revision"])   # archive field untouched
        self.assertEqual((self.www / "crew/maps/archive/west-yard/index.html").read_text(), archive)

    def test_apply_writes_crew_json_as_build_crew_json_does(self):
        """crew.json has one writer: after a revision bump, apply() leaves it as build_crew_json would write it."""
        (self.www / "data/crew.json").write_text("{}\n")              # whatever was there is replaced, not patched
        map_revision.apply(self.www, self.prefs)
        built = self.built()
        self.assertEqual((self.www / "data/crew.json").read_text(encoding="utf-8"), built)
        self.assertIn('"revision": "99"', built)

    def built(self):
        """What build_crew_json.py would write with the temp title block."""
        with mock.patch.object(build_crew_json, "fields", lambda: map_revision.fields(self.prefs)):
            return build_crew_json.build()

    def test_apply_recreates_a_missing_crew_json(self):
        (self.www / "data/crew.json").unlink()
        self.assertIn(self.www / "data/crew.json", map_revision.apply(self.www, self.prefs))
        self.assertEqual((self.www / "data/crew.json").read_text(encoding="utf-8"), self.built())

    def fallback(self, **patch):
        """planned() with crew_master's MASTER or INDUSTRIES patched: (crew.json's planned text, the warning)."""
        before = json.loads((self.www / "data/crew.json").read_text())
        err = io.StringIO()
        with mock.patch.multiple(crew_master, **patch), contextlib.redirect_stderr(err):
            changed = map_revision.apply(self.www, self.prefs)     # the schematic step still publishes
        self.assertEqual(len(changed), 2 + len(CREW["maps"]))
        crew = json.loads((self.www / "data/crew.json").read_text())
        before["schematic"].update(revision="99", effective="1 December 2026")
        self.assertEqual(crew, before)                               # only the revision and date set
        return err.getvalue()

    def test_a_broken_master_falls_back_to_the_revision_and_date(self):
        bad = json.loads(crew_master.MASTER.read_text())
        bad["colors"].append(dict(bad["colors"][0]))                 # a duplicate color id: a schema problem
        master = self.www.parent / "crew-master.json"
        master.write_text(json.dumps(bad))
        warning = self.fallback(MASTER=master)
        self.assertIn("map_revision: warning: the crew master does not build: " + str(master.resolve()), warning)
        self.assertIn("the crew master has problems", warning)
        self.assertIn("crew-json", warning)
        self.assertEqual(warning.count("\n"), 1)                    # one line

    def test_a_master_that_is_not_json_falls_back(self):
        master = self.www.parent / "crew-master.json"
        master.write_text("{")
        self.assertIn(f"{master.resolve()}: not JSON", self.fallback(MASTER=master))

    def test_a_missing_industries_csv_falls_back(self):
        missing = self.www.parent / "industries.csv"
        self.assertIn(f"does not build: {missing}: No such file", self.fallback(INDUSTRIES=missing))

    def test_missing_publication_entry_stops(self):
        path = self.www / "data/publications.json"
        pubs = json.loads(path.read_text())
        pubs["items"] = [i for i in pubs["items"] if i.get("pub") != "SM-06"]
        path.write_text(json.dumps(pubs))
        with self.assertRaisesRegex(ValueError, "crew/maps/barn/index.html"):
            map_revision.planned(self.www, self.prefs)


if __name__ == "__main__":
    unittest.main()
