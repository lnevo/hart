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
RUN = WWW / "exam" / "run.js"          # the game's core; the runs and pools are in RUN_FILES
RUN_FILES = [RUN] + [WWW / "exam" / f for f in ("run-1949.js", "run-modern.js", "run-signals.js", "run-yard.js")]


def run_source() -> str:
    """The game's scripts as one text: every ask({ call the key reads."""
    return "\n".join(f.read_text() for f in RUN_FILES)
RUN_PAGE = WWW / "exam" / "run.html"
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
            "const src=m.readRun();"
            "const qs=m.extract(src);console.log(JSON.stringify({qs,generated:qs.generated}))"
        )
        data = json.loads(out)
        qs = data["qs"]
        calls = len(re.findall(r"\bask\(\{", run_source()))
        self.assertEqual(len(qs) + data["generated"], calls)
        self.assertGreater(data["generated"], 0, "the signals run's questions drawn at each signal")
        for q in qs:
            self.assertTrue(q["right"] and q["wrong"] and q["why"], q["title"])
            # Values filled in at play time must read as a friendly name, never a raw stub.
            for field in (q["title"], q["body"], q["right"], *(w["t"] for w in q["wrong"])):
                self.assertNotRegex(field, r"\[\w+\.[\w.\[\]]*\]|NaN|\[object", f"run.js line {q['line']}")

    def files(self, body="", modern="", yard="", pool=""):
        """Minimal scripts for extract: run.js with a figure helper, the pools, and one file per run."""
        return [
            {"file": "run.js", "where": "1949 run", "src": 'function semSvg(a){return "<svg>"+a+"</svg>"}' + body},
            {"file": "run-1949.js", "where": "1949 run", "src": "const ROAD_TTO=[];const STN_TTO=[];"},
            {"file": "run-modern.js", "where": "Modern run", "src": modern + "const ROAD_TWC=[" + pool + "];"},
            {"file": "run-yard.js", "where": "Yard job", "src": yard},
        ]

    def mini(self, body="", modern="", yard="", pool=""):
        return json.loads(node(
            f"const m=require({json.dumps(str(SCRIPT))});"
            f"console.log(JSON.stringify(m.extract({json.dumps(self.files(body, modern, yard, pool))})))"
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
        q = self.mini(self.Q % "", self.Q % ',extra:semSvg(0)', self.Q % "", "()=>" + self.Q % "")
        self.assertEqual([x["where"] for x in q], ["1949 run", "Modern run", "Modern run, on the road", "Yard job"])
        self.assertEqual(q[0]["src"], "GCOR · 6.13")
        self.assertEqual(q[1]["extra"], "<svg>0</svg>")
        self.assertEqual([(x["file"], x["line"]) for x in q][:2], [("run.js", 1), ("run-modern.js", 1)])

    def test_bad_question_names_its_file(self):
        with self.assertRaisesRegex(AssertionError, "run-yard.js line 2: question has no why"):
            self.mini(yard='\nask({sec:"def",title:"t",body:"b",right:"r",wrong:[["w"]]});')

    def test_pool_declared_twice_stops_the_build(self):
        with self.assertRaisesRegex(AssertionError, "pool ROAD_TWC is declared in 2 scripts, not one"):
            self.mini(yard="const ROAD_TWC=[];")

    def warrant(self, plan, name="w1"):
        return json.loads(node(
            f"const m=require({json.dumps(str(SCRIPT))});"
            f"console.log(JSON.stringify(m.warrant({plan},{json.dumps(name)})))"
        ))

    def test_warrant_from_the_plan(self):
        w = self.warrant('{box5Lead:12,warrants:{w1:{no:"101",at:"A",boxes:{2:["A","B","Main"],5:null},'
                         'draws:{hold:[{8:[]},{10:[]}]}}}}')
        self.assertEqual(w["boxes"], {"2": {"vals": ["A", "B", "Main"], "some": False}, "5": {"vals": None, "some": False},
                                      "8": {"vals": [], "some": True}, "10": {"vals": [], "some": True}})
        with self.assertRaisesRegex(AssertionError, "warrant 101 sets box 8 twice"):
            self.warrant('{warrants:{w1:{no:"101",at:"A",boxes:{8:[]},draws:{hold:[{8:[]},{10:[]}]}}}}')
        with self.assertRaisesRegex(AssertionError, "draw hold is not a pair of box sets"):
            self.warrant('{warrants:{w1:{no:"101",at:"A",boxes:{},draws:{hold:[{8:[]}]}}}}')
        with self.assertRaisesRegex(AssertionError, "TWC_PLAN has no warrant w9"):
            self.warrant('{warrants:{}}', "w9")

    def test_questions_needing_the_sheet_have_a_reference(self):
        out = node(
            f"const m=require({json.dumps(str(SCRIPT))});"
            "const src=m.readRun();"
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
        # Box 5 is set at play time; Box 6 is on every run; 8 and 10 depend on the run.
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

    def test_signal_stories_vary_without_repeats(self):
        signals = WWW / "exam" / "signals.js"
        out = node(
            "const vm=require('vm'),fs=require('fs');const c={};vm.createContext(c);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(signals))},'utf8')+';this.p=pickStories',c);"
            "let seed=1;const rand=()=>(seed=(seed*16807)%2147483647)/2147483647;"
            "const keys=['clear','approach','stopnum','meet'],fixed=[null,'clear','stopnum',null,'pplate','granite','cp',null];"
            "const runs=[];for(let n=0;n<400;n++)runs.push(c.p(fixed,i=>i===2?keys:keys,['meet'],rand));"
            "console.log(JSON.stringify(runs))"
        )
        runs = json.loads(out)
        fixed = [None, "clear", "stopnum", None, "pplate", "granite", "cp", None]
        counts = {}
        for r in runs:
            for i, k in enumerate(r):
                if fixed[i] is not None:
                    self.assertEqual(k, fixed[i], "a set piece keeps its story")
                    continue
                self.assertNotEqual(k, r[i - 1] if i else None, f"leg {i} repeats the leg before: {r}")
                if i + 1 < len(r) and fixed[i + 1] is not None:
                    self.assertNotEqual(k, fixed[i + 1], f"leg {i} repeats the set piece after it: {r}")
                counts[k] = counts.get(k, 0) + 1
            self.assertLessEqual(r.count("meet"), 1, f"two meets in one run: {r}")
        self.assertLess(counts.get("clear", 0) / sum(counts.values()), 0.5, counts)
        # a clash rule keeps a leg off any story that shows the same signals as the set piece after it
        out = node(
            "const vm=require('vm'),fs=require('fs');const c={};vm.createContext(c);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(signals))},'utf8')+';this.p=pickStories',c);"
            "let seed=7;const rand=()=>(seed=(seed*16807)%2147483647)/2147483647;const clash=(a,b)=>a===b||(a==='ahead1'&&b==='hollisM')||(b==='ahead1'&&a==='hollisM');"
            "const r=[];for(let n=0;n<200;n++)r.push(c.p([null,'hollisM'],()=>['clear','ahead1','restrict'],[],rand,clash)[0]);console.log(JSON.stringify(r))"
        )
        self.assertNotIn("ahead1", json.loads(out))

    def test_speed_run_can_show_every_aspect(self):
        run = (WWW / "exam" / "run-signals.js").read_text()
        body = run[run.index("function startSIG("):]
        used = set(re.findall(r'"(2[89][0-9][A-C]?)"', body))  # every quoted rule number in startSIG
        signals = (WWW / "exam" / "signals.js").read_text()
        rules = set(re.findall(r'\{r:"([0-9]{3}[A-C]?)"', signals))
        # every aspect the run names exists, and every one is named (289 Permissive on the Cobb to Dunmore manual block)
        self.assertLessEqual(used, rules, f"unknown aspects: {used - rules}")
        self.assertEqual(rules - used, set())

    def test_game_and_deck_load_the_shared_signals(self):
        for page in (RUN_PAGE, INDEX):
            self.assertIn('<script src="signals.js" defer></script>', page.read_text(), page.name)

    def test_right_answer_not_always_first(self):
        html = (WWW / "exam" / "answers.html").read_text()
        lists = re.findall(r'<ul class="xa-opts">(.*?)</ul>', html)
        first_ok = sum(1 for ul in lists if ul.startswith('<li class="ok">'))
        self.assertLess(first_ok, len(lists) * 0.6)


class SectionNames(unittest.TestCase):
    def test_guide_game_and_cards_share_sections(self):
        index = INDEX.read_text()
        cards = re.search(r"const SECTIONS=(\{[^}]*\})", (WWW / "exam" / "deck-data.js").read_text()).group(1)
        pairs = lambda text: re.findall(r'(\w+):"([^"]+)"', text)  # the source may wrap the literal
        engine = WWW / "js" / "game-engine.js"  # both games take their section names from it
        game = json.loads(node(f"console.log(JSON.stringify(Object.entries(require({json.dumps(str(engine))}).DECK_SECTIONS)))"))
        self.assertEqual(pairs(cards), [tuple(p) for p in game], "game-engine.js DECK_SECTIONS must match the deck's SECTIONS")
        names = dict(pairs(cards))
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
