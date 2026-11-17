"""Extra East answer key: answers.html is current with run.html, every question is read, and the game and the
study deck use the same section names. Runs build_exam_answers.js with node; skipped when node is missing."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

WWW = Path(__file__).resolve().parents[2]
SCRIPT = WWW / "scripts" / "build_exam_answers.js"
RUN = WWW / "exam" / "run.html"
INDEX = WWW / "exam" / "index.html"


def node(code):
    r = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise AssertionError(r.stdout + r.stderr)
    return r.stdout


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ExamAnswers(unittest.TestCase):
    def test_answers_page_is_current(self):
        r = subprocess.run(["node", str(SCRIPT), "--check"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_question_read_with_answers(self):
        out = node(
            f"const m=require({json.dumps(str(SCRIPT))});"
            f"const src=require('fs').readFileSync({json.dumps(str(RUN))},'utf8');"
            "const qs=m.extract(src);console.log(JSON.stringify({qs,generated:qs.generated}))"
        )
        data = json.loads(out)
        qs = data["qs"]
        calls = len(re.findall(r"\bask\(\{", RUN.read_text()))
        self.assertEqual(len(qs) + data["generated"], calls)
        self.assertGreater(data["generated"], 0, "the signals run's questions drawn at each signal")
        for q in qs:
            self.assertTrue(q["right"] and q["wrong"] and q["why"], q["title"])
            # Values filled in at play time must read as a friendly name, never a raw stub.
            for field in (q["title"], q["body"], q["right"], *(w["t"] for w in q["wrong"])):
                self.assertNotRegex(field, r"\[\w+\.[\w.\[\]]*\]|NaN|\[object", f"run.html line {q['line']}")

    # A minimal run.html: the pools, the modern-run markers, the source names and a figure helper.
    FRAME = (
        'const SRC={SC:"1949 Standard Code",GC:"GCOR"};function semSvg(a){return "<svg>"+a+"</svg>"}'
        "const ROAD_TTO=[];const STN_TTO=[];const ROAD_TWC=[];{BODY}const TW_SEL={};{MODERN}function startSIG(){}function startYARD(){{YARD}}function finish(){}"
    )

    def mini(self, body="", modern="", yard=""):
        src = self.FRAME.replace("{BODY}", body).replace("{MODERN}", modern).replace("{YARD}", yard)
        return json.loads(node(
            f"const m=require({json.dumps(str(SCRIPT))});"
            f"console.log(JSON.stringify(m.extract({json.dumps(src)})))"
        ))

    Q = 'ask({sec:"def",src:"GC · 6.13",title:"t",body:"b",right:"r",wrong:[["w"]],why:"y"%s});'

    def test_bad_question_stops_the_build(self):
        with self.assertRaisesRegex(AssertionError, "no why"):
            self.mini('ask({sec:"def",title:"t",body:"b",right:"r",wrong:[["w"]]});')

    def test_shown_text_chosen_at_play_time_stops_the_build(self):
        with self.assertRaisesRegex(AssertionError, "right chosen at play time"):
            self.mini('ask({sec:"def",src:"SC",title:"t",body:"b",right:hold?"a":"b",wrong:[["w"]],why:"y"});')
        # Fields the key does not show may still depend on the run.
        self.assertEqual(len(self.mini(self.Q % ',ok:can?{}:{marks:1},after:o=>{if(o&&can)x()}')), 1)

    def test_comments_and_nested_templates_are_skipped(self):
        q = self.mini(
            'ask({sec:"def",src:"SC",title:"t",// don\'t shuffle }\n'
            "body:`a ${`b ${1+1}`} c`,/* ) */right:\"r\",wrong:[[\"w\"]],why:\"y\"});"
        )
        self.assertEqual(q[0]["body"], "a b 2 c")

    def test_modern_run_label_source_names_and_figures(self):
        q = self.mini(self.Q % "", self.Q % ',extra:semSvg(0)', self.Q % "")
        self.assertEqual([x["where"] for x in q], ["1949 run", "Modern run", "Yard job"])
        self.assertEqual(q[0]["src"], "GCOR · 6.13")
        self.assertEqual(q[1]["extra"], "<svg>0</svg>")

    def test_questions_needing_the_sheet_have_a_reference(self):
        out = node(
            f"const m=require({json.dumps(str(SCRIPT))});"
            f"const src=require('fs').readFileSync({json.dumps(str(RUN))},'utf8');"
            "const R=m.references(src);"
            "console.log(JSON.stringify({qs:m.extract(src).filter(q=>q.ref).map(q=>[q.title,q.ref]),"
            "refs:Object.fromEntries(Object.entries(R).map(([k,v])=>[k,v.html]))}))"
        )
        data = json.loads(out)
        refs = {t: r for t, r in data["qs"]}
        # The four questions whose facts the game shows only on its train sheet or warrant form.
        self.assertEqual(refs.get("Same class, opposite ways"), "tt")
        self.assertEqual(refs.get("Box 5"), "w101")
        self.assertEqual(refs.get("Box 7"), "w102")
        self.assertTrue(any(r == "order" for t, r in data["qs"] if t.startswith("Order No")))
        html = data["refs"]
        self.assertIn("Westward trains are superior to eastward trains of the same class", html["tt"])
        # Box 5 is set at play time; Box 6 is set after the literal on every run; 8 and 10 depend on the run.
        self.assertIn("Not in effect until <b>[time]</b>", html["w101"])
        self.assertIn("arrival of <b>2211 West</b> at <b>Dunmore</b>", html["w102"])
        self.assertIn("expires at <b>9:00</b></td>", html["w102"])
        self.assertIn('Hold main track at last named point <small class="xa-some">some runs</small>', html["w102"])
        self.assertIn("No 1 run 20 mins late Ironton to Ashby", html["order"])
        self.assertIn("at least 12 minutes later", html["w101"])
        for k, v in html.items():
            self.assertNotRegex(v, r"\{\w+\}", k)

    def test_warrant_box_value_count_must_match_its_blanks(self):
        with self.assertRaisesRegex(AssertionError, "box 5 has 2 values for 1 blanks"):
            node(
                f"const m=require({json.dumps(str(SCRIPT))});"
                "m.warrantHtml({no:'1',at:'A',boxes:{5:{vals:['6:20','7:00'],some:false}}},[[5,'Not in effect until {time}']])"
            )

    def test_unknown_reference_stops_the_build(self):
        with self.assertRaisesRegex(AssertionError, 'unknown reference "nope"'):
            node(
                f"const m=require({json.dumps(str(SCRIPT))});"
                "m.render([{line:1,sec:'def',src:'',title:'t',body:'b',right:'r',wrong:[],why:'y',ref:'nope',extra:''}],{def:'D'},{})"
            )

    def test_signal_tables_cover_the_signals_run(self):
        out = node(
            f"const m=require({json.dumps(str(SCRIPT))});const S=m.loadSignals();const g=m.generatedHtml(S);"
            "console.log(JSON.stringify({n:g.n,a:S.ASPECTS.length,r:new Set(S.ROUTE.map(x=>x.heads)).size,p:Object.keys(S.PLATES).filter(k=>k!=='none').length,"
            "badW:S.ASPECTS.filter(a=>a.w.length!==3||a.w.some(r=>!S.ASPECTS.find(x=>x.r===r))).map(a=>a.r)}))"
        )
        d = json.loads(out)
        self.assertEqual(d["badW"], [])
        # one entry per aspect, per distinct route-signal look, and per plate the game draws
        self.assertEqual(d["n"], d["a"] + d["r"] + d["p"])
        html = (WWW / "exam" / "answers.html").read_text()
        self.assertIn('id="signals"', html)
        for rule in ("Rule 281", "Rule 292", "A plate at Stop", "SA plate at Stop", "carries an SA plate"):
            self.assertIn(rule, html)

    def test_game_and_deck_load_the_shared_signals(self):
        for page in (RUN, INDEX):
            self.assertIn('<script src="signals.js"></script>', page.read_text(), page.name)

    def test_right_answer_not_always_first(self):
        html = (WWW / "exam" / "answers.html").read_text()
        lists = re.findall(r'<ul class="xa-opts">(.*?)</ul>', html)
        first_ok = sum(1 for ul in lists if ul.startswith('<li class="ok">'))
        self.assertLess(first_ok, len(lists) * 0.6)


class SectionNames(unittest.TestCase):
    def test_guide_game_and_cards_share_sections(self):
        index = INDEX.read_text()
        cards = re.search(r"const SECTIONS=(\{[^}]*\})", index).group(1)
        game = re.search(r"const SEC=(\{[^}]*\})", RUN.read_text()).group(1)
        self.assertEqual(cards, game, "run.html SEC must match the deck's SECTIONS")
        names = dict(re.findall(r'(\w+):"([^"]+)"', cards))
        guide = re.findall(r'<article id="learn-(\w+)" data-sec="\1" data-short="([^"]+)">\s*<h3>\d+\. ([^<]+)</h3>', index)
        self.assertEqual([k for k, _, _ in guide], list(names), "study guide sections follow the card order")
        for k, short, h3 in guide:
            want = names[k].replace("&", "&amp;")
            self.assertEqual((short, h3), (want, want), k)

    def test_guide_notes_link_the_answer_key(self):
        notes = INDEX.read_text().split('id="view-notes"', 1)[1].split("</section>", 1)[0]
        self.assertIn('href="answers.html"', notes)


if __name__ == "__main__":
    unittest.main()
