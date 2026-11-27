"""Extra East answer key: answers.html is current with run.html, every question is read without running the game's
code, the game and the key share one data module, and the game and the study deck use the same section names. Runs
build_exam_answers.js with node; skipped when node is missing."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

WWW = Path(__file__).resolve().parents[2]
SCRIPT = WWW / "scripts" / "build_exam_answers.js"
RUN = WWW / "exam" / "run.js"          # the game's core; the runs and pools are in RUN_FILES
RUN_FILES = [RUN] + [WWW / "exam" / f for f in ("run-tto.js", "run-1949.js", "run-modern.js", "run-signals.js", "run-yard.js")]


def run_source() -> str:
    """The game's scripts as one text: every ask({ call the key reads."""
    return "\n".join(f.read_text() for f in RUN_FILES)
RUN_PAGE = WWW / "exam" / "run.html"
INDEX = WWW / "exam" / "index.html"
DATA = WWW / "exam" / "run-data.js"


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
                self.assertNotRegex(field, r"\[\w+\.[\w.\[\]]*\]|NaN|\[object", f"{q['file']} line {q['line']}")

    def files(self, body="", modern="", yard="", pool=""):
        """Minimal scripts for extract: run.js, the pools, and one file per run."""
        return [
            {"file": "run.js", "where": "1949 run", "src": body},
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
        # the figure is drawn by the data module's semSvg, the one the game draws with
        self.assertIn('aria-label="Semaphore, blade at 0 degrees"', q[1]["extra"])
        self.assertEqual([(x["file"], x["line"]) for x in q][:2], [("run.js", 1), ("run-modern.js", 1)])

    def test_bad_question_names_its_file(self):
        with self.assertRaisesRegex(AssertionError, "run-yard.js line 2: question has no why"):
            self.mini(yard='\nask({sec:"def",title:"t",body:"b",right:"r",wrong:[["w"]]});')

    def test_getters_and_play_time_values_read_as_slots(self):
        q = self.mini('ask({sec:"def",src:"SC",title:"Too close to "+p.tr.name,get body(){return `at ${STATIONS[j].n}`;},'
                      'right:`${Math.max(0,p.by)} min`,wrong:[[fmt(t)],["b",{marks:1},"c"]],why:"y",'
                      'after:o=>{s.x=o.replace(/[)}"`]/g,"")}});')[0]
        self.assertEqual((q["title"], q["body"], q["right"]), ("Too close to [train]", "at [station]", "[n] min"))
        self.assertEqual(q["wrong"], [{"t": "[time]", "why": ""}, {"t": "b", "why": "c"}])

    def test_code_in_a_shown_field_stops_the_build(self):
        cases = {
            'body:(()=>"b")()': "a function",
            'body:"b".toUpperCase()': "cannot read .toUpperCase of a value",
            "body:String(x)": "uses String",
            'body:"a"-1': 'cannot read "-"',
            "get body(){x();return 1}": "a getter that does more than return one value",
            "...extra,body:1": "a spread or a computed key",
            'body:"a",body:"b"': "body is set twice",
            "body:Math.random()": "Math.random",
        }
        for field, err in cases.items():
            src = 'ask({sec:"def",src:"SC",title:"t",%s,right:"r",wrong:[["w"]],why:"y"});' % field
            with self.subTest(field), self.assertRaisesRegex(AssertionError, re.escape(err)):
                self.mini(src)
        # a call on a play-time name is itself a play-time value
        self.assertEqual(self.mini(self.Q.replace('body:"b"', "body:run(1)") % "")[0]["body"], "[…]")

    def test_object_prototype_names_are_not_literals(self):
        # toString and constructor are not the key's literals: they stop the build like any global the key does not run,
        # and no longer come back as the function itself.
        for name in ("toString", "constructor", "hasOwnProperty"):
            src = self.Q.replace('body:"b"', f"body:{name}") % ""
            with self.subTest(name), self.assertRaisesRegex(AssertionError, f"uses {name}, which the key does not run"):
                self.mini(src)

    def test_slash_after_increment_is_division(self):
        # i++/2 must not start a regex literal that runs to a later slash or fails as unclosed
        q = self.mini(self.Q % ",after:o=>{s.a=i++/2}")
        self.assertEqual(len(q), 1)

    def test_unclosed_question_names_its_line(self):
        with self.assertRaisesRegex(AssertionError, "run.js line 2: no closing bracket"):
            self.mini('\nask({sec:"def",title:"t"')
        with self.assertRaisesRegex(AssertionError, "run.js line 1: string not closed"):
            self.mini('ask({sec:"def,title:"t"});')

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
            "const R=m.references();"
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

    def special(self, notes):
        return node(f"const m=require({json.dumps(str(SCRIPT))});"
                    f"console.log(m.specialInstructions({notes}))").strip()

    def test_special_instructions_come_from_the_sheet_notes(self):
        self.assertEqual(self.special('{tto:["One.","Two (Rule 5)."]}'), "<li>One.</li><li>Two (Rule 5).</li>")
        with self.assertRaisesRegex(AssertionError, "SHEET_NOTES.tto is not a list of special instructions"):
            self.special("{tto:[]}")
        with self.assertRaisesRegex(AssertionError, "SHEET_NOTES.tto is not a list"):
            self.special('{twc:["x"]}')
        with self.assertRaisesRegex(AssertionError, "no SHEET_NOTES"):
            self.special("undefined")

    def test_key_and_game_read_one_data_module(self):
        """The key's references come from run-data.js, and the page loads it before every run file."""
        out = json.loads(node(
            f"const m=require({json.dumps(str(SCRIPT))}),d=require({json.dumps(str(DATA))});"
            "const R=m.references();console.log(JSON.stringify({same:m.DATA===d,n:d.STATIONS.length,"
            "rows:(R.tt.html.match(/<tr><td>/g)||[]).length}))"
        ))
        self.assertTrue(out["same"])
        self.assertEqual(out["rows"], out["n"], "one time-table row per station in run-data.js")
        scripts = re.findall(r'<script src="([^"]+)"', RUN_PAGE.read_text())
        data_at = scripts.index("run-data.js")
        for f in RUN_FILES:
            self.assertLess(data_at, scripts.index(f.name), f"run.html loads run-data.js after {f.name}")
        self.assertLess(scripts.index("../js/game-engine.js"), data_at)

    def test_broken_data_stops_the_build(self):
        with self.assertRaisesRegex(AssertionError, "run-data.js: STATIONS is not a list.*; TWC_PLAN has no box5Lead"):
            node(f"const m=require({json.dumps(str(SCRIPT))});"
                 "m.references({...m.DATA,STATIONS:[{n:'A'}],TWC_PLAN:{warrants:{}}})")

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
        """Plays startSIG("speed") 300 times on a seeded stream, the run files' helpers stubbed, and collects the rule
        of every signal it draws: every aspect in signals.js shows up (289 Permissive on the Cobb to Dunmore manual
        block), and no other."""
        load = "".join(
            f"vm.runInContext(fs.readFileSync({json.dumps(str(WWW / f))},'utf8'),c,{{filename:{json.dumps(f)}}});"
            for f in ("js/game-engine.js", "exam/run-data.js", "exam/signals.js"))
        fakes = (
            "const G=window.GameEngine,D=window.ExtraEastData,asked=[],noop=()=>{},scene=()=>noop;"
            "const S={fmt:G.fmt,randSetup:()=>Math.random(),rnd:(a,b)=>G.rnd(a,b,Math.random),pick:a=>G.pick(a,Math.random),"
            "shuffle:a=>G.shuffle(a,Math.random),STATIONS:D.STATIONS,LAST:D.STATIONS.length-1,state:{},addTime:noop,"
            "renderMap:noop,leg:scene,finish:noop,push:noop,next:noop,log:noop,ask:o=>{asked.push(o);return noop},info:scene};"
            "window.ExtraEast={take:(f,names)=>Object.fromEntries(names.map(n=>{if(!(n in S))throw new Error(f+' takes '+n);"
            "return [n,S[n]]})),give:(f,o)=>Object.assign(window.ExtraEast,o)};"
            "let s=3;Math.random=()=>(s=(s*16807)%2147483647)/2147483647;this.asked=asked;"
        )
        out = node(
            "const vm=require('vm'),fs=require('fs');const c={};c.window=c;vm.createContext(c);" + load +
            f"vm.runInContext({json.dumps(fakes)},c);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(WWW / 'exam' / 'run-signals.js'))},'utf8'),c);"
            "for(let n=0;n<300;n++)c.window.ExtraEast.startSIG('speed');"
            "console.log(JSON.stringify({used:[...new Set(c.asked.filter(o=>o.gen==='speed').map(o=>o.src))],"
            "rules:vm.runInContext('ASPECTS.map(a=>a.r)',c)}))"
        )
        d = json.loads(out)
        used = {s.removeprefix("SC · Rule ") for s in d["used"]}
        self.assertEqual(used, set(d["rules"]))

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
        engine = WWW / "js" / "game-engine.js"  # both games take their section names from it
        got = json.loads(node(
            "const vm=require('vm'),fs=require('fs');const c={};vm.createContext(c);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(WWW / 'exam' / 'signals.js'))},'utf8'),c);"
            f"vm.runInContext(fs.readFileSync({json.dumps(str(WWW / 'exam' / 'deck-data.js'))},'utf8')+';this.S=SECTIONS',c);"
            f"console.log(JSON.stringify({{deck:Object.entries(c.S),game:Object.entries(require({json.dumps(str(engine))}).DECK_SECTIONS)}}))"
        ))
        self.assertEqual(got["deck"], got["game"], "game-engine.js DECK_SECTIONS must match the deck's SECTIONS")
        names = dict(got["deck"])
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
