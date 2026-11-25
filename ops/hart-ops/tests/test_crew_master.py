"""The crew master ops/hart-ops/data/crew.json: its schema check, the site view and the docx views (ADR-039, L5)."""
import copy
import json
import sys
import unittest
from pathlib import Path

PUB = Path(__file__).resolve().parents[1] / "publications"
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PUB))

import build_crew_json  # noqa: E402
import crew_master as cm  # noqa: E402
from crew_schema import problems  # noqa: E402

MASTER = cm.load()
INDUSTRIES = cm.read_industries()


class RealMaster(unittest.TestCase):
    def test_master_is_sound(self):
        self.assertEqual(problems(MASTER, INDUSTRIES), [])

    def test_site_file_is_built_from_the_master(self):
        self.assertEqual((REPO / "www/data/crew.json").read_text(encoding="utf-8"), build_crew_json.build(),
                         "run python3 ops/hart-ops/publications/build_crew_json.py")


class Schema(unittest.TestCase):
    def broken(self, edit) -> list[str]:
        m = copy.deepcopy(MASTER)
        edit(m)
        return problems(m, INDUSTRIES)

    def test_duplicate_color_id(self):
        out = self.broken(lambda m: m["colors"].append(dict(m["colors"][0])))
        self.assertIn("colors: id 'blue' is given twice", out)

    def test_job_names_a_missing_color_and_map(self):
        def edit(m):
            cm.job(m, "d749")["colors"].append("teal")
            cm.job(m, "d749")["maps"].append("nowhere")
        out = self.broken(edit)
        self.assertIn("job 'd749': color 'teal' is no color", out)
        self.assertIn("job 'd749': map 'nowhere' is no map", out)

    def test_spot_sheet_industry_must_be_in_industries_csv(self):
        out = self.broken(lambda m: m["spotsheet"]["industries"][0].update(industry_id="acme"))
        self.assertIn("spot sheet industry 'acme': not in ops/hart-ops/data/industries.csv", out)

    def test_spot_sheet_name_comes_from_industries_csv(self):
        out = self.broken(lambda m: m["spotsheet"]["industries"][0].update(name="Aristech"))
        self.assertIn("spot sheet industry 'aristech': name must come from industries.csv, not the crew master", out)

    def test_docx_object_holds_only_known_fields(self):
        out = self.broken(lambda m: cm.job(m, "d749").setdefault("docx", {}).update(intorduction="x"))
        self.assertTrue(any("job 'd749': docx holds intorduction" in p for p in out), out)

    def test_schematic_revision_stays_out(self):
        out = self.broken(lambda m: m["schematic"].update(revision="1"))
        self.assertTrue(any(p.startswith("schematic: revision and effective") for p in out), out)

    def test_lineup_row_needs_a_route(self):
        out = self.broken(lambda m: cm.job(m, "dispatcher")["lineup"][0].update(route=""))
        self.assertIn("job 'dispatcher' row '1': a lineup row needs route and action", out)

    def test_build_stops_on_a_problem(self):
        bad = copy.deepcopy(MASTER)
        bad["colors"].append(dict(bad["colors"][0]))
        orig = cm.load
        cm.load = lambda path=cm.MASTER: bad
        try:
            with self.assertRaises(SystemExit):
                build_crew_json.build()
        finally:
            cm.load = orig


class SiteView(unittest.TestCase):
    def view(self, master=MASTER):
        return cm.site_view(master, INDUSTRIES, ("7", "1 January 2027"))

    def test_docx_fields_are_left_out(self):
        self.assertNotIn('"docx"', json.dumps(self.view()))
        self.assertNotIn("_about", self.view())

    def test_spot_sheet_takes_name_and_anchor_from_industries(self):
        ind = INDUSTRIES["stucki"]
        site = next(i for i in self.view()["spotsheet"]["industries"] if i["id"] == ind["slug"])
        self.assertEqual(site["name"], ind["name"])
        self.assertEqual(list(site)[:2], ["id", "name"])

    def test_rules_join_the_summary_and_routes_lead_the_action(self):
        jobs = {j["id"]: j for j in self.view()["jobs"]}
        ym = cm.job(MASTER, "yardmaster")
        self.assertEqual(jobs["yardmaster"]["summary"], " ".join([ym["summary"], *ym["rules"]]))
        self.assertNotIn("rules", jobs["yardmaster"])
        row = cm.job(MASTER, "dispatcher")["lineup"][0]
        self.assertEqual(jobs["dispatcher"]["lineup"][0]["action"], f"{row['route']} {row['action']}")

    def test_schematic_fields_come_from_the_title_block(self):
        sc = self.view()["schematic"]
        self.assertEqual((sc["revision"], sc["effective"]), ("7", "1 January 2027"))


class DocxViews(unittest.TestCase):
    def test_hex6(self):
        self.assertEqual(cm.hex6("#fff"), "FFFFFF")
        self.assertEqual(cm.hex6("#0000CD"), "0000CD")

    def test_heading_case(self):
        self.assertEqual(cm.heading_case("2.1 Preparing the scale"), "2.1 Preparing the Scale")
        self.assertEqual(cm.heading_case("1.1 Pre-scale alignment & approach"), "1.1 Pre-Scale Alignment & Approach")

    def test_color_key_uses_the_short_interchange_names(self):
        offline, island = cm.color_key(MASTER)
        self.assertEqual(offline, [("0000CD", "Demmler / McKeesport"), ("FFA500", "Scully / McKees Rocks")])
        self.assertEqual(island[0], ("FFFF00", "Aristech Plastics"))

    def test_yard_sequence_ends_in_its_color_names(self):
        seq = dict((n, a) for n, _t, a in cm.yard_sequence(MASTER))
        self.assertTrue(seq["2"].endswith("(Yellow, Green, Purple, Red, Pink)"), seq["2"])

    def test_crew_engine_line_spacing(self):
        d749 = next(c for c in cm.crews(MASTER) if c["train"] == "D749")
        self.assertEqual(d749["engine"], "CR 1993  ·  GE B23-7")
        self.assertEqual(d749["file"], "Neville_Island_Crew_D749.docx")


if __name__ == "__main__":
    unittest.main()
