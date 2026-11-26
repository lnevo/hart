(function(){
"use strict";
/* Extra East: HART Railroad. The scene engine (js/game-engine.js) is shared with Extra East: a queue of scenes,
   each a decision with a source. The runs themselves are in runs.js; this file draws the island, keeps the
   clock and the record, and scores the shift. */
const $=id=>document.getElementById(id);
const {esc,seeded,store,MAX_MARKS}=window.GameEngine; // the engine both games share (js/game-engine.js)
let randSetup=Math.random,randChoices=Math.random;
const today=()=>{const d=new Date();
  return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0")};
const rnd=(a,b)=>window.GameEngine.rnd(a,b,randSetup);
const pick=a=>window.GameEngine.pick(a,randSetup);
const shuffle=(a,r)=>window.GameEngine.shuffle(a,r);
const fmt=m=>window.GameEngine.fmt(m);
const reduced=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches;

/* Sources. GC/YL point into the C&E study deck; PV is Mark Connolly's P&OV blog, linked post by post. */
const DECK="../exam/index.html";
const POV="../library/pittsburgh-ohio-valley-railway.html";
const SEC=window.GameEngine.SECTIONS; // the section and source names both games share (js/game-engine.js)
const srcLabel=s=>window.GameEngine.srcLabel(s,window.GameEngine.PLAY_DOTLESS); // "GCOR 6.3", no dot
const studyHref=sec=>sec==="pov"?POV:DECK+"#learn-"+sec;
const TUMBLR="https://www.tumblr.com/pittsburghohiovalleyrailroad/";

/* ---------- the island ---------- */
/* A sketch, not a survey: west on the left, the Ohio's main channel along the top, the back channel along
   the bottom. Places come from the blog's captions (see the P&OV page's Track and place names). */
/* Four rows, west to east: the north line (y 40) from the foundry to E1, the scale track (y 68), the south line
   (y 96) from the PC&Y to the Furnace Runner's bumping block, and the East Runner (y 132) along the back channel.
   Every connection is at 45 degrees. x,y is where an engine stands; t is the label, drawn at lx,ly. */
const LOC={
  foundry:{x:22,y:40,n:"toward the foundry",t:"← FOUNDRY",lx:6,ly:33,a:"start"},
  yint:{x:36,y:120,n:"Y Interchange",t:"Y INT · PC&Y",lx:46,ly:131,a:"start"},
  gulf:{x:80,y:96,n:"Gulf Crossing",t:"GULF X",lx:80,ly:109,a:"middle"},
  wyard:{x:140,y:40,n:"West Yard",t:"WEST YARD",lx:150,ly:24,a:"middle"},
  stucki:{x:206,y:24,n:"Stucki",t:"STUCKI",lx:206,ly:17,a:"middle"},
  srun:{x:150,y:96,n:"South Runner",t:"S RUNNER",lx:150,ly:109,a:"middle"},
  shed:{x:212,y:112,n:"track gang shed by S1",t:"",lx:0,ly:0},
  syard:{x:232,y:96,n:"South Yard",t:"SOUTH YARD",lx:232,ly:124,a:"middle"},
  chem:{x:272,y:24,n:"chemical plant",t:"CHEMICAL",lx:272,ly:17,a:"middle"},
  s9:{x:278,y:68,n:"S9, by the scale",t:"S9",lx:278,ly:60,a:"middle"},
  scale:{x:312,y:68,n:"the yard office scale",t:"SCALE",lx:312,ly:60,a:"middle"},
  xing:{x:345,y:68,n:"the main crossing",t:"",lx:0,ly:0},
  cokelead:{x:414,y:54,n:"coke plant lead",t:"",lx:0,ly:0},
  dumper:{x:452,y:24,n:"car dumper, E2",t:"DUMPER E2",lx:452,ly:17,a:"middle"},
  coke:{x:488,y:40,n:"coke battery",t:"COKE OVENS",lx:488,ly:64,a:"middle"},
  eyard:{x:428,y:112,n:"East Yard",t:"EAST YARD",lx:426,ly:105,a:"middle"},
  e9:{x:440,y:112,n:"E9, the heat track",t:"",lx:0,ly:0},
  ladle:{x:494,y:96,n:"ladle house",t:"LADLES",lx:494,ly:109,a:"middle"},
  flead:{x:520,y:40,n:"furnace lead",t:"",lx:0,ly:0},
  f1:{x:540,y:20,n:"F1, at the furnace",t:"F1 · B",lx:552,ly:23,a:"start"},
  pig:{x:540,y:96,n:"A furnace pig machine",t:"A · PIG",lx:540,ly:109,a:"middle"},
  bump:{x:576,y:96,n:"Furnace Runner, by the bumping block",t:"",lx:0,ly:0},
  e1:{x:580,y:40,n:"E1, the barge track",t:"E1",lx:592,ly:33,a:"end"},
  erunner:{x:330,y:132,n:"East Runner",t:"EAST RUNNER",lx:380,ly:127,a:"middle"},
  cement:{x:352,y:132,n:"the cement tower",t:"",lx:0,ly:0}
};
/** @type {PlayRun|null} */
let state=null;
/**
 * One shift or road run: the engine's RunState (js/game-engine.js) plus the island's own fields.
 * @typedef {import("../js/game-engine.js").RunState & {
 *   run:string, pace:number, start:number, jobs:{done:boolean}[], parAdd:number, par:number,
 *   units:Object<string,string>, lead:string, d:Object, plants:string[], def?:Object, daily?:(string|null),
 *   leaving?:boolean
 * }} PlayRun
 */
/** @param {string} id @returns {PlayRun} */
function newState(id){return {run:id,pace:1,clock:0,start:0,marks:0,misses:[],log:[],ended:false,jobs:[],parAdd:0,par:0,
  units:{},lead:"",d:{},plants:[]}}

const placeName=()=>state.def.where?state.def.where(state):(LOC[state.units[state.lead]]?LOC[state.units[state.lead]].n:"");
function renderMap(){
  const box=$("xwMap");if(!state)return;
  if(state.def.map){box.innerHTML=state.def.map(state,H);return} // a road run draws its own line
  const W=600,k=box.clientWidth&&box.clientWidth<560?1.3:1,fs=n=>(n*k).toFixed(1);
  const where=placeName();
  let s=`<svg viewBox="0 0 ${W} 150" role="img" aria-label="Track sketch of the east end of Neville Island, `+
      `${esc(state.def.code)} at ${esc(where)}">`;
  s+=`<rect x="0" y="0" width="${W}" height="150" fill="var(--river)"/><rect x="0" y="11" width="${W}" `+
      `height="129" fill="var(--land)"/>`;
  s+=`<text x="8" y="8" font-size="${fs(6.5)}" class="water">OHIO RIVER · MAIN CHANNEL</text><text `+
      `x="${W-8}" y="148" font-size="${fs(6.5)}" text-anchor="end" class="water">BACK CHANNEL</text>`;
  s+=`<text x="${W-8}" y="8" font-size="${fs(6)}" text-anchor="end" class="water">${esc(state.def.year)}</text>`;
  // the road across the island at the main crossing
  s+=`<line x1="345" y1="11" x2="345" y2="140" stroke="var(--muted)" stroke-width="1" `+
      `stroke-dasharray="3 3" opacity=".55"/>`;
  // running tracks
  s+=`<g fill="none" stroke="var(--ink)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round">`;
  s+=`<path d="M10 40 H590"/>`; // north line: foundry, West Yard, coke plant, furnace lead, E1
  s+=`<path d="M16 140 L60 96 H576"/>`;
    // PC&Y off the bridge, Y Interchange, Gulf Crossing, South Runner, South Yard, ladles, Furnace Runner
  s+=`<path d="M220 96 L248 68 H400 L428 40"/>`;
    // the scale track: South Yard, S9, the scale, the main crossing, coke plant lead
  s+=`<path d="M100 96 L156 40"/>`; // West Yard ladder
  s+=`<path d="M270 96 L306 132 H440 L476 96"/>`; // East Runner along the back channel
  s+=`</g><g fill="none" stroke="var(--ink)" stroke-width="1.4" stroke-linecap="round">`;
  s+=`<path d="M190 40 L206 24"/><path d="M256 40 L272 24"/><path d="M436 40 L452 24"/><path d="M520 40 L540 20"/>`;
    // Stucki, chemical, dumper, F1
  s+=`<path d="M196 96 L204 104 H250 M204 104 L212 112 H250"/>`; // South Yard tracks
  s+=`<path d="M392 96 L408 112 H448"/>`; // East Yard and E9
  s+=`<path d="M120 40 L128 32 H170"/>`; // a West Yard track
  s+=`</g>`;
  // the scale, the Gulf Crossing, the bumping block, the plant
  s+=`<rect x="305" y="64.5" width="14" height="7" fill="none" stroke="var(--rust)" stroke-width="1.6"/>`;
  s+=`<line x1="80" y1="88" x2="80" y2="104" stroke="var(--muted)" stroke-width="1" stroke-dasharray="2 2"/>`;
  s+=`<line x1="579" y1="91" x2="579" y2="101" stroke="var(--ink)" stroke-width="2.5"/>`;
  s+=`<g fill="var(--muted)" opacity=".8"><rect x="472" y="46" width="32" height="8"/><rect x="528" `+
      `y="12" width="7" height="14"/><rect x="532" y="80" width="7" height="10"/><rect x="350" y="107" `+
      `width="5" height="10"/></g>`;
  s+=`<text x="359" y="116" font-size="${fs(6)}" class="lbl">${esc((state.def.cement||"cement").toUpperCase())}</text>`;
  if(state.def.foundryClosed)s+=`<text x="6" y="52" font-size="${fs(6)}" class="lbl">CLOSED</text>`;
  Object.values(LOC).forEach(L=>{if(L.t)s+=`<text x="${L.lx}" y="${L.ly}" font-size="${fs(6.8)}" text-anchor="${L.a||"middle"}" `+
      `class="lbl">${esc(L.t)}</text>`});
  // the engines, the job's own lit
  Object.entries(state.units).forEach(([u,at])=>{const L=LOC[at];if(!L)return;const me=u===state.lead;
    s+=`<g transform="translate(${L.x} ${L.y})"><rect x="-11" y="-5" width="22" height="10" rx="2" `+
        `fill="${me?"var(--green)":"var(--muted)"}" stroke="${me?"var(--glow)":"#fff"}" `+
        `stroke-width="${me?1.4:.8}"/><text x="0" y="2.6" font-size="${fs(6.8)}" text-anchor="middle" `+
        `fill="#fff" font-weight="700">${esc(u)}</text></g>`});
  box.innerHTML=s+`</svg>`;
}
/* The next stop on a road run, from the run's own position (a run gives next(state)). Nothing on a run where the player chooses the next stop. */
function nextName(){
  const D=state.def;
  if(D.next)return D.next(state)||"";
  return "";
}
/* The way out of a run: a link in the status bar that asks first, in the page, then goes back to the start screen. */
const exitHtml=()=>state.ended?"":state.leaving
  ?`<span class="xw-exit" role="group" aria-label="Leave this run"><span>Leave this run? It is not `+
      `saved.</span><button type="button" class="xw-link" data-exit="yes">Leave</button><button `+
      `type="button" class="xw-link xw-stay" data-exit="no">Stay</button></span>`
  :`<span class="xw-exit"><button type="button" class="xw-link xw-ask" data-exit="ask">Choose another `+
      `run</button></span>`;
function exitClick(e){
  const b=e&&e.target&&e.target.closest&&e.target.closest("[data-exit]");if(!b||!state)return;
  const a=b.dataset.exit;
  if(a==="yes"){state.ended=true;state.leaving=false;ENGINE.reset();showStart();
    window.scrollTo({top:$("xw").getBoundingClientRect().top+scrollY-80,behavior:"auto"});
    // the first control still on screen: the section chip's clear link, the first-shift link, or the first Start button
    const f=document.querySelector&&["#xwClear","#xwNewJob","#xwRandom",
      "[data-run]"].flatMap(q=>[...document.querySelectorAll(q)]).find(e=>e.offsetParent!==null);
      if(f&&f.focus)f.focus();return}
  state.leaving=a==="ask";renderStatus();
  const f=$("xwStatus").querySelector(state.leaving?".xw-stay":".xw-ask");if(f)f.focus();
}
function renderStatus(){
  if(!state)return;
  const end=state.def.end,left=end-state.clock;
  const where=placeName(),nx=nextName();
  $("xwStatus").innerHTML=`<span><span class="lbl">Job</span><b>${esc(state.def.code)}</b></span><span><span `+
      `class="lbl">Clock</span><b>${fmt(state.clock)}</b></span><span><span `+
      `class="lbl">Quits</span>${fmt(end)}${left<0?` <i class="over">+${Math.round(-left)} min</i>`:""}</span><span><span `+
      `class="lbl">At</span>${esc(where)}</span>${nx?`<span><span class="lbl">Next</span>${esc(nx)}</span>`:""}<span `+
      `class="marks"><span class="lbl">Marks</span><b>${state.marks}</b>/${MAX_MARKS}</span>${exitHtml()}`;
  renderMap();
}

/* ---------- scene engine ---------- */
function addTime(m){const t=Math.round(m*state.pace);state.clock+=t;
  return t} // a shift's minutes on the map are its pace times the move's own
function hereName(){if(state.def&&state.def.where)return state.def.where(state);const L=LOC[state.units[state.lead]];
  return L?L.n:"Neville Island"}
/* On a phone the sheet sits under the scene (the .xw-grid breakpoint, 860px), so a player who was reading the
   time-table would not see the next scene. When its top is above the screen or low on it, scroll to the status bar,
   which keeps the clock, the marks and the map in view with the scene under them. Not on a wide screen, not for a
   run's first scene (begin() scrolls), and not when the scene is already in view, e.g. while the map is being read. */
let firstScene=false;
function sceneIntoView(el){
  if(firstScene){firstScene=false;return}
  const vh=window.innerHeight||0;if(!vh||!(window.matchMedia&&matchMedia("(max-width:860px)").matches))return;
  const top=el.getBoundingClientRect().top-(reduced?0:6); // the xw-in animation starts 6px low
  if(top>=0&&top<=vh*.6)return;
  window.scrollTo({top:$("xwStatus").getBoundingClientRect().top+scrollY-70,behavior:reduced?"auto":"smooth"});
}
/* On a phone the verdict, the why and Continue can sit below the screen once a choice is made, with the choices above them.
   When Continue is below the screen or the verdict above it, scroll so the verdict sits near the top. Same breakpoint as sceneIntoView. */
function resultIntoView(res,go){
  const vh=window.innerHeight||0;if(!vh||!(window.matchMedia&&matchMedia("(max-width:860px)").matches))return;
  const r=res.getBoundingClientRect(),g=go.getBoundingClientRect();
  if(r.top>=0&&g.bottom<=vh-8)return;
  window.scrollTo({top:r.top+scrollY-70,behavior:reduced?"auto":"smooth"});
}
const srcHtml=o=>{const t=esc(srcLabel(o.src));
  return o.url?`<a href="${o.url.startsWith("http")?o.url:TUMBLR+o.url}" rel="noopener">${t}</a>`:t};
const ENGINE=window.GameEngine.createEngine({
  state:()=>state,render:()=>{renderStatus();renderSheet()},hereName:()=>hereName(),addTime:m=>addTime(m),
  costMinutes:c=>Math.round(c.min*state.pace),srcHtml:o=>srcHtml(o),finish:(t,f)=>finish(t,f),
    lockGo:false,
  choiceRandom:o=>state.daily?seeded(state.daily+"|"+o.title+"|"+o.right):randChoices,
  afterScene:el=>sceneIntoView(el),afterResult:(res,go)=>resultIntoView(res,go),
  words:{endVerdict:"Shift over.",endText:"The trainmaster took you off the job.",
    marksText:"Five marks in one shift. The trainmaster took you off the job.",smallTag:"<small>"}});
const {front,next,log,scene,ask,info}=ENGINE;
/* Move an engine (the job's own unless named) to a place, taking some minutes; par is the sum of the moves. */
const mv=(to,min,note,unit)=>()=>{state.units[unit||state.lead]=to;state.parAdd+=addTime(min);if(note)log(note);
  renderStatus();next()};
const wait=(min,note)=>()=>{state.parAdd+=addTime(min);if(note)log(note);renderStatus();next()};
const done=i=>()=>{state.jobs[i].done=true;renderSheet();next()};
/* What a road run (road-engine.js, road.js, passenger.js, pcy.js, pir.js) needs besides the island's helpers: put scenes at the front of the queue, draw its own
   scene, and list a question the player may meet only on some paths (key: no-op here, the answer key's build reads it). */
const key=()=>null;
const H={ask,info,mv,wait,done,rnd,pick,fmt,esc,log,addTime,front,scene,key,next,renderStatus,shuffle,srcHtml,finish,$,
  get S(){return state},get R(){return randSetup}};

/* ---------- the switch list ---------- */
/* The sheet is drawn again at every scene: keep a table's sideways scroll, and when the table runs wider than the sheet show
   a fade at the right edge and a "more trains" line above it until the last column is in view. */
let cue=null; // redraws the current table's fade and hint; the window calls it on resize
if(typeof window.addEventListener==="function")window.addEventListener("resize",()=>{if(cue)cue()});
function renderSheet(){
  const el=$("xwSheet"),old=state&&el.querySelector(".xw-tt"),sl=old&&old.scrollLeft||0;
  paintSheet();
  const tt=state&&el.querySelector(".xw-tt");if(!tt||!tt.insertAdjacentElement)return;
  const hint=document.createElement("p");hint.className="xw-more";
    hint.textContent="More trains: scroll sideways \u2192";
  tt.insertAdjacentElement("beforebegin",hint);
  tt.scrollLeft=sl;
  const upd=()=>{const over=tt.scrollWidth>tt.clientWidth+2&&tt.scrollLeft+tt.clientWidth<tt.scrollWidth-2;
    hint.hidden=!over;tt.classList.toggle("fade",over)};
  tt.addEventListener("scroll",upd,{passive:true});upd();cue=upd;
}
function paintSheet(){
  const el=$("xwSheet");if(!state){el.innerHTML="";return}
  const D=state.def;
  if(D.sheet){el.innerHTML=D.sheet(state,H);return} // a road run prints its own time-table and orders
  el.innerHTML=`<h3>Pittsburgh &amp; Ohio Valley</h3><div class="sub">Switching orders · ${esc(D.code)} ${esc(D.name)} · ${esc(D.dateLine)}</div>
    <div class="xw-orders"><b>Work</b>${state.jobs.map(j=>`<div class="ord${j.done?" done":""}">${j.done?"✓ ":""}${esc(j.t)}</div>`).join("")}</div>
    <div class="xw-si"><b>On the island, ${esc(D.year)}</b><ul>${D.plants.map(p=>`<li>${p}</li>`).join("")}</ul></div>
    <div class="xw-si"><b>Special instructions</b><ul>${D.si.map(p=>`<li>${p}</li>`).join("")}<li>Rules: GCOR.</li></ul></div>`;
}

/* ---------- the end ---------- */
function finish(text,failed){
  if(state.ended)return;state.ended=true;
  const D=state.def,time=state.clock-state.start;
  const par=state.par?Math.round(state.par-state.start):null;
  let verdict,cls="";
  if(failed)verdict="Taken off the job";
  else if(state.marks===0&&(par===null?state.clock<=D.end+15*state.pace:time<=par+15*state.pace)){verdict="Clean shift";
    cls="good"} // a road run has no par: it is on time if it is in before it quits
  else if(state.marks<=1){verdict="Good shift";cls="good"}
  else verdict="Marked up";
  if(D.verdicts)verdict=D.verdicts[verdict]||verdict;
    // a run may name its own verdicts (the new conductor's first shift)
  const secs=[...new Set(state.misses.map(m=>m.sec))];
  const slip=par!==null&&!failed?Math.round(time-par):0;
    // minutes the misses added to the work, so the tie-up time and the last scene's clock agree
  const missHtml=state.misses.length?state.misses.map(m=>`<details${m.end?" open":""}><summary>${esc(m.title)}</summary><p>${esc(m.why)}</p><p `+
      `class="src">${srcHtml(m)} · <a `+
      `href="${studyHref(m.sec)}">${m.sec==="pov"?"Read: ":"Study: "}${esc(SEC[m.sec])}</a></p></details>`).join(""):"<p>No rules missed.</p>";
  const nr=suggest(secs);
  const el=scene(failed?hereName():D.endPlace,failed?"The shift ends":"Tied up",
    `<span class="xw-stamp ${cls}">${verdict}</span><p>${esc(text)}</p>
     <div class="xw-end"><div class="score"><div><b>${failed?"—":fmt(state.clock)}</b><span>Tied up at</span></div><div><b>${Math.floor(time/60)}h ${String(time%60).padStart(2,"0")}</b><span>On the job</span></div>${par!==null&&!failed?`<div><b>${Math.floor(par/60)}h ${String(Math.round(par)%60).padStart(2,"0")}</b><span>The work, no mistakes</span></div>`:""}${slip>0?`<div><b>+${slip} min</b><span>from misses</span></div>`:""}<div><b>${state.marks}</b><span>Marks</span></div></div>
     ${D.coda&&!failed?`<div class="xw-coda">${D.coda}</div>`:""}
     <h3 class="rec">Service record</h3><div class="miss">${missHtml}</div>
     <p class="study">${secs.length?`Study next: ${secs.map(s=>`<a href="${studyHref(s)}">${esc(SEC[s])}</a>`).join(" · ")}`:`Every rule is in the <a href="${DECK}">C&amp;E study deck</a>.`} · <a href="answers.html">Answer key</a></p></div>
     <div class="choices row"><button class="xw-btn primary" id="again">${state.daily?"Replay today's shift":"Work it again"}</button>${nr?`<button class="xw-btn" id="nextRun">Try ${esc(RUNS[nr].code)}, ${esc(RUNS[nr].name)}${secs.some(x=>(RUNS[nr].covers||[]).includes(x))?"<small>tests what you missed</small>":""}</button>`:""}<button class="xw-btn" id="home">Choose another job</button></div>`);
  const runs=store.get("ni_runs",[]);
    runs.unshift({run:state.run,when:Date.now(),marks:state.marks,time,failed,verdict,daily:state.daily});
    store.set("ni_runs",runs.slice(0,30));
  const id=state.run,daily=state.daily;
  if(daily){
    const key="ni_daily_"+daily+"_"+id,stored=store.get(key,null);
    const mine={id:state.attempt,verdict,marks:state.marks,time,failed};
    const first=stored&&stored.id!==state.attempt?stored:null;
    if(!first)store.set(key,mine);
    const rec=first||mine;
    const line=`Extra East: HART Railroad, ${daily}, ${D.code} ${D.name}: ${rec.verdict}, ${rec.marks} `+
        `mark${rec.marks===1?"":"s"}${rec.failed?"":", "+Math.floor(rec.time/60)+"h "+String(rec.time%60).padStart(2,"0")+"m on the job"}. `+
        `${location.origin.startsWith("http")?location.origin+location.pathname:"hartrailroad.com/play/"}`;
    const box=document.createElement("div");box.className="xw-daily";
    box.innerHTML=`<p>${first?"Your first try at today's shift counts for the day; this replay does not change it.":"This is your result for today's shift. Replays are for practice and do not change it."}</p><div `+
        `class="xw-share">${esc(line)}</div><div><button class="xw-btn" id="copy">Copy the `+
        `result</button></div>`;
    el.querySelector(".xw-end").appendChild(box);
    $("copy").onclick=()=>{const ok=()=>{$("copy").textContent="Copied"};
      if(navigator.clipboard)navigator.clipboard.writeText(line).then(ok,
        ()=>{$("copy").textContent="Select the text above to copy it"});
        else $("copy").textContent="Select the text above to copy it"};
  }
  $("again").onclick=()=>begin(id,daily);
  if($("nextRun"))$("nextRun").onclick=()=>begin(nr);
  $("home").onclick=showStart;
}
/* The run to suggest next, going down the list from this one: a run that tests a section the player missed, else one not finished in this browser, else the next in the list. */
function nextRun(runs,current,done,secs){
  const keys=Object.keys(runs),i=keys.indexOf(current);
  const order=keys.slice(i+1).concat(keys.slice(0,Math.max(i,0))).filter(k=>k!==current);
  const rank=k=>(secs.length&&!secs.some(x=>(runs[k].covers||[]).includes(x))?2:0)+(done.has(k)?1:0);
  return order.map((k,j)=>[rank(k),j,k]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]).map(x=>x[2])[0]||"";
}
const suggest=secs=>nextRun(RUNS,state.run,new Set(store.get("ni_runs",[]).filter(r=>!r.failed).map(r=>r.run)),secs);
/* Which cards the start screen shows: covers is the run's list of sections, sec the chip that is on ("" for All). */
const rowShown=(covers,sec)=>!sec||covers.includes(sec);
  // a card shows with no section chip on, or when its run tests that section
window.PlayLogic={nextRun,rowShown};

/* ---------- start ---------- */
let RUNS={};
function begin(id,daily){
  daily=null;
    // no daily shift: the draws barely change from day to day (owner, 2026-11-22); the daily path is kept for a pool-based draw later
  if(daily===true)daily=today();
  if(daily){randSetup=seeded("neville|"+daily+"|"+id+"|setup")}else randSetup=randChoices=Math.random;
  state=newState(id);state.daily=daily||null;ENGINE.reset();
  if(daily){state.attempt=Date.now();const key="ni_daily_"+daily+"_"+id;
    if(!store.get(key,null))store.set(key,{id:state.attempt,verdict:"Did not finish",marks:0,time:0,failed:true})}
  $("xwLog").innerHTML="";
  const def=RUNS[id];state.def=def;state.pace=def.pace||1;state.clock=state.start=def.start;state.lead=def.engine;
    state.units=Object.assign({},def.units);
  const shift=def.build(H);state.jobs=shift.work.map(t=>({t,done:false}));
  ENGINE.reset(shift.steps.concat([()=>{state.par=shift.noPar?0:state.start+state.parAdd;
    const t=shift.end?shift.end():def.tieUp;log("Tied up");finish(t.replace("{t}",fmt(state.clock)),false)}]));
  $("xwStart").hidden=true;$("xwGame").hidden=false;$("xw").classList.remove("on-start");
    if($("xwCover"))$("xwCover").hidden=true;
  renderStatus();renderSheet();
  window.scrollTo({top:$("xw").getBoundingClientRect().top+scrollY-80,behavior:reduced?"auto":"smooth"});
  firstScene=true;next();
}
const DAYS=["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
function reliefToday(){
  const d=new Date().getDay(),n=DAYS[d];
  if(d===1||d===2)return `Today is ${n}: #115 works the midnight trick, the night #305 has off.`;
  if(d===3)return `Today is ${n}: #115 works the second trick, while #205 is off.`;
  if(d===0||d===6)return `Today is ${n}: #115 is the daylight crew, with #105 and #110 off.`;
  return `Today is ${n}: #115 has the day off.`;
}
/* The deck's eight sections in its order; each run lists the ones it asks (covers, checked against its questions by
   test_play_answers.py). TAG is the short name on a run's row. */
const SECTIONS=Object.entries(window.GameEngine.DECK_SECTIONS);
const TAG={def:"Definitions",sup:"Superiority",to:"Train orders",sig:"Signals",sem:"Semaphores",yl:"Yard limits",
  twc:"Warrants",gcor:"GCOR"};
/* How long a run is, for its card: the typical number of questions over many draws (play_through_test.js prints the means). */
const LEN={j105:"about 10 questions",j110:"about 13 questions",j205:"about 8 questions",j305:"about 7 questions",
  j115:"about 8 questions",extra:"about 6 questions",ym:"about 8 questions",
  coal:"about 15 questions",passenger:"about 20 questions",pcy:"about 18 questions",pir:"about 19 questions"};
/* The start screen, built from the cards in index.html: each run is a topic card in its section (the site's own
   section and card styles) with its icon, kind line, title, one-line story, section tags, length and Start. The section
   chips hide the cards whose run does not test that section, and a section with no card left; All shows every card. */
function renderCover(){
  const box=$("xwCover");if(!box)return;
  const groups=[...document.querySelectorAll(".xw-group")];if(!groups.length)return;
  // each run is a topic card, as on the rest of the site: kind line, title, story, the sections it tests and its length, Start
  const cards=[...document.querySelectorAll(".xw-group .card")];
  cards.forEach(card=>{
    const b=card.querySelector("[data-run]"),def=b&&RUNS[b.dataset.run];if(!def)return;
    card.dataset.secs=(def.covers||[]).join(" ");
    const tags=SECTIONS.filter(x=>(def.covers||[]).includes(x[0])).map(x=>`<span>${esc(TAG[x[0]])}</span>`).join("");
    const meta=document.createElement("p");meta.className="xw-tags";
    meta.innerHTML=tags+(LEN[b.dataset.run]?`<span class="xw-len">${esc(LEN[b.dataset.run])}</span>`:"");
    card.insertBefore(meta,card.querySelector(".xw-go"));
    const h=card.querySelector("h3");
      if(h&&!b.querySelector(".xw-vh"))b.insertAdjacentHTML("beforeend",
      `<span class="xw-vh"> ${esc(h.textContent)}</span>`);
  });
  // section chips: All, then each section some run tests
  const used=SECTIONS.filter(([k])=>Object.values(RUNS).some(d=>(d.covers||[]).includes(k)));
  // the section filter sits under the title like the site's "On this page" row (nav.jump)
  box.innerHTML=`<p class="jump-label" id="xwCoverLbl">Practice a section</p><ul class="xw-chips" aria-labelledby="xwCoverLbl">${[["","All"]].concat(used.map(([k])=>[k,TAG[k]])).map(([k,n])=>
    `<li><button type="button" data-sec="${k}" aria-pressed="false">${esc(n)}</button></li>`).join("")}</ul><p class="xw-showing" id="xwShowing" role="status" hidden></p>`;
  const chips=[...box.querySelectorAll("button[data-sec]")],showing=$("xwShowing");
  // Take a call off the extra board: a random run among the cards showing, so it follows the section filter
  const rnd=$("xwRandom");if(rnd)rnd.hidden=false;
    if(rnd)rnd.onclick=()=>{const ids=cards.filter(c=>!c.hidden).map(c=>c.querySelector("[data-run]").dataset.run).filter(id=>RUNS[id]);
    if(ids.length)begin(ids[Math.floor(Math.random()*ids.length)])};
  let sec="";
  function show(){
    cards.forEach(c=>{c.hidden=!rowShown((c.dataset.secs||"").split(" "),sec)});
    groups.forEach(g=>{g.hidden=!g.querySelector(".card:not([hidden])");const n=g.querySelector(".xw-group-note");
      if(n)n.hidden=!!sec});
    chips.forEach(c=>c.setAttribute("aria-pressed",String(c.dataset.sec===sec)));
    if(sec){
      const n=cards.filter(c=>!c.hidden).length;
      showing.innerHTML=`Showing ${n} run${n===1?"":"s"} that test${n===1?"s":""} ${esc(TAG[sec])} · <button type="button" `+
          `class="xw-link" id="xwClear">clear</button>`;
      showing.hidden=false;
        $("xwClear").onclick=()=>{const was=sec;sec="";show();const c=chips.find(x=>x.dataset.sec===was);
        if(c)c.focus()};
    }else showing.hidden=true;
  }
  chips.forEach(c=>c.onclick=()=>{sec=c.dataset.sec;show()});
  // a link to a section (#gChartiers) or to a run's title (#rcoal) clears a filter that hides it and scrolls to it
  function follow(){
    if($("xwStart").hidden)return; // a link followed during a run leaves the start screen's filter alone
    const el=location.hash.length>1&&document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if(!el||!el.closest(".xw-group"))return;
    if(el.closest("[hidden]")){sec="";show()}
    (el.closest(".card")||el).scrollIntoView({block:"start"});
      // cards and sections keep clear of the sticky header (scroll-margin-top)
  }
  show();follow();window.addEventListener("hashchange",follow);
  const nj=$("xwNewJob");if(nj&&RUNS.j105)nj.onclick=e=>{e.preventDefault();begin("j105")};
    // the new conductor's first shift; without the script the link goes to its card
  box.hidden=false;
}
function showStart(){
  $("xwStart").hidden=false;$("xwGame").hidden=true;$("xw").classList.add("on-start");
    if($("xwCover")&&$("xwCover").innerHTML)$("xwCover").hidden=false;
  const runs=store.get("ni_runs",[]),d=today();
  document.querySelectorAll("[data-run]").forEach(b=>{
    if(!b.hasAttribute("data-daily"))return;
    const r=store.get("ni_daily_"+d+"_"+b.dataset.run,null);
    b.querySelector("small").textContent=r?`played: ${r.verdict}, ${r.marks} mark${r.marks===1?"":"s"}`:d;
  });
  const rt=$("reliefToday");if(rt)rt.textContent=reliefToday();
  const best=e=>{const r=runs.filter(x=>x.run===e&&!x.failed).sort((a,b)=>a.marks-b.marks||a.time-b.time)[0];
    return r?`${r.verdict}, ${r.marks} mark${r.marks===1?"":"s"}`:"none yet"};
  $("xwBest").textContent=runs.length?`Your best in this browser. ${Object.keys(RUNS).map(e=>RUNS[e].code+": "+best(e)).join(". ")}.`:"";
}

RUNS=window.NevilleRuns||{};
renderCover();
{const st=$("xwStatus");if(st)st.onclick=exitClick}
document.querySelectorAll("[data-run]").forEach(b=>b.onclick=()=>begin(b.dataset.run,b.hasAttribute("data-daily")));
showStart();
})();
