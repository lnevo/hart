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

    def test_site_note_must_be_a_sentence(self):
        self.assertEqual(self.broken(lambda m: m["jobs"][0].update(site_note=" ")),
                         ["job 'd749': site_note must be a non-empty sentence"])

    def test_docx_object_holds_only_known_fields(self):
        out = self.broken(lambda m: cm.job(m, "d749").setdefault("docx", {}).update(intorduction="x"))
        self.assertTrue(any("job 'd749': docx holds intorduction" in p for p in out), out)

    def test_schematic_revision_stays_out(self):
        out = self.broken(lambda m: m["schematic"].update(revision="1"))
        self.assertTrue(any(p.startswith("schematic: revision and effective") for p in out), out)

    def test_every_map_needs_its_tracks(self):
        out = self.broken(lambda m: m["maps"][0].pop("tracks"))
        self.assertIn(f"map {MASTER['maps'][0]['id']!r}: no tracks (the map page lists them)", out)
        out = self.broken(lambda m: m["maps"][1]["tracks"][0].update(purpose="", map="nowhere"))
        mid, track = MASTER["maps"][1]["id"], MASTER["maps"][1]["tracks"][0]["track"]
        self.assertIn(f"map {mid!r}: track row 1 has no purpose", out)
        self.assertIn(f"map {mid!r}: track {track!r} links map 'nowhere', which is no map", out)

    def test_spot_sheet_needs_its_desk_notes(self):
        out = self.broken(lambda m: m["spotsheet"].pop("desk"))
        self.assertEqual(out, ["spot sheet: no desk notes (the spot sheet page ends with them)"])
        did = MASTER["spotsheet"]["desk"][0]["id"]
        out = self.broken(lambda m: m["spotsheet"]["desk"][0].update(tag="", lists=[{"label": "Jobs"}]))
        self.assertIn(f"spot sheet desk {did!r}: no tag", out)
        self.assertIn(f"spot sheet desk {did!r}: list 1 needs a label and items", out)
        out = self.broken(lambda m: m["spotsheet"]["desk"].append(dict(m["spotsheet"]["desk"][0])))
        self.assertIn(f"spot sheet: desk id {did!r} is given twice", out)

    def test_lineup_row_needs_a_route(self):
        out = self.broken(lambda m: cm.job(m, "dispatcher")["lineup"][0].update(route=""))
        self.assertIn("job 'dispatcher' row '1': a lineup row needs route and action", out)

    def test_jobs_need_what_their_docx_prints(self):
        out = self.broken(lambda m: (cm.job(m, "d749").pop("steps"), cm.job(m, "dispatcher").pop("priority")))
        self.assertIn("job 'd749': a crew job needs steps (its docx prints it)", out)
        self.assertIn("job 'dispatcher': a dispatcher job needs priority (its docx prints it)", out)

    def test_colors_and_timetable_hold_no_docx_object(self):
        out = self.broken(lambda m: (m["colors"][0].update(docx={"key_label": "x"}),
                                     m["timetable"].update(docx={"note": "x"})))
        self.assertIn("color 'blue': a color holds no docx object (the sheet prints the site wording)", out)
        self.assertIn("timetable: holds no docx object (the sheet prints the site wording)", out)

    def test_legend_extra_rows_need_their_fields(self):
        def edit(m):
            cm.job(m, "yardmaster")["legend_extra"][0].update(hex="white")
            del cm.job(m, "yardmaster")["legend_extra"][0]["dest"]
        out = self.broken(edit)
        self.assertIn("job 'yardmaster': legend_extra row 1 has no dest", out)
        self.assertIn("job 'yardmaster': legend_extra row 1: hex 'white' is not #rgb or #rrggbb", out)

    def test_legend_extra_rows_are_objects_with_known_fields_and_new_labels(self):
        ym = lambda m: cm.job(m, "yardmaster")
        self.assertIn("job 'yardmaster': legend_extra row 1 must be an object",
                      self.broken(lambda m: ym(m).update(legend_extra=["NONE"])))
        self.assertIn("job 'yardmaster': legend_extra row 1: unknown field 'fill'",
                      self.broken(lambda m: ym(m)["legend_extra"][0].update(fill="FFFFFF")))
        self.assertIn("job 'yardmaster': blocking list label 'NONE' is given twice",
                      self.broken(lambda m: ym(m)["legend_extra"].append(dict(ym(m)["legend_extra"][0]))))

    def test_yardmaster_lists_every_color(self):
        out = self.broken(lambda m: cm.job(m, "yardmaster")["colors"].remove("black"))
        self.assertTrue(any("colors must list every color" in p and "missing black" in p for p in out), out)

    def test_only_the_yardmaster_job_holds_legend_extra(self):
        out = self.broken(lambda m: cm.job(m, "d749").update(legend_extra=[]))
        self.assertIn("job 'd749': only a yardmaster job holds legend_extra", out)

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

    def test_yardmaster_legend_extra_reaches_the_site(self):
        jobs = {j["id"]: j for j in self.view()["jobs"]}
        self.assertEqual(jobs["yardmaster"]["legend_extra"], cm.job(MASTER, "yardmaster")["legend_extra"])
        self.assertEqual(jobs["yardmaster"]["legend_extra"][0]["label"], "NONE")

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

    def test_site_note_joins_the_site_summary_but_not_the_sheet(self):
        site = {j["id"]: j for j in self.view()["jobs"]}
        d749 = cm.job(MASTER, "d749")
        self.assertEqual(site["d749"]["summary"], f"{d749['summary']} {d749['site_note']}")
        self.assertNotIn("site_note", site["d749"])
        sheet = next(c for c in cm.crews(MASTER) if c["train"] == "D749")
        self.assertEqual(sheet["intro"], d749["summary"])

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

    def test_color_key_uses_the_sites_destinations(self):
        offline, island = cm.color_key(MASTER)
        self.assertEqual(offline, [("0000CD", "Demmler Yard; McKeesport"), ("FFA500", "Scully Yard; McKees Rocks")])
        self.assertEqual(island[0], ("FFFF00", "Aristech Plastics"))

    def test_yard_sequence_ends_in_its_color_names(self):
        seq = dict((n, a) for n, _t, a in cm.yard_sequence(MASTER))
        self.assertTrue(seq["2"].endswith("(Yellow, Green, Purple, Red, Pink)"), seq["2"])
        self.assertTrue(seq["3"].endswith("sort. (Black)"), seq["3"])  # owner, 2026-11-25: like rows 1, 2 and 4

    def test_blocking_list_follows_the_jobs_colors_then_the_extra_rows(self):
        ym = cm.job(MASTER, "yardmaster")
        labels = [row[0] for row in cm.block_legend(MASTER)]
        colors = {c["id"]: c["label"] for c in MASTER["colors"]}
        self.assertEqual(labels, [colors[i] for i in ym["colors"]] + [e["label"] for e in ym["legend_extra"]])
        self.assertEqual(labels[-1], "NONE")
        self.assertEqual(cm.block_legend(MASTER)[-1], ("NONE", "FFFFFF", "000000", "No card color", "Yard storage"))
        self.assertEqual(labels[:5], ["YELLOW", "GREEN", "PURPLE", "RED", "PINK"])  # the printed Rev E order

    def test_timetable_back_page_prints_the_site_wording(self):
        tt = MASTER["timetable"]
        self.assertEqual(cm.tt23_back_page(MASTER), {"subtitle": tt["subtitle"], "note": tt["note"]})

    def test_crew_engine_line_spacing(self):
        d749 = next(c for c in cm.crews(MASTER) if c["train"] == "D749")
        self.assertEqual(d749["engine"], "CR 1993  ·  GE B23-7")
        self.assertEqual(d749["file"], "Neville_Island_Crew_D749.docx")


if __name__ == "__main__":
    unittest.main()
