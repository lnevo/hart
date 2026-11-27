/* Extra East: the game's core: helpers, the railroad, the map, the event draws, the end screen and the start screen.
   The runs are in run-tto.js (the 1949 run; its event pools in run-1949.js), run-modern.js, run-signals.js and
   run-yard.js; the title screen's pixel art in run-title.js.
   Each of run.js, run-tto.js, run-1949.js, run-modern.js, run-signals.js and run-yard.js runs inside its own function. run.js
   puts its helpers and the run's state on window.ExtraEast; each later file takes the names it uses with X.take and
   hands back its own with X.give (see "the interface with the run files" at the end). run.html loads them in that
   order. */
(function(){
"use strict";
const X=window.ExtraEast={}; // the names the six files share; the later files give theirs
/* ---------- helpers ---------- */
const {esc,store,MAX_MARKS,srcLabel,DECK_SECTIONS:SEC}=window.GameEngine; // shared with play (js/game-engine.js)
const fmt=m=>window.GameEngine.fmt(m); // a 24-hour clock: a minute past midnight reads 0:01, as in play
const $=id=>document.getElementById(id);
/* Random streams: one sets up the run, one writes the train orders, one orders the answers. */
let randSetup=Math.random,randOrders=Math.random,randChoices=Math.random;
const rnd=(a,b,r=randSetup)=>window.GameEngine.rnd(a,b,r);
const pick=(a,r=randSetup)=>window.GameEngine.pick(a,r);
const shuffle=(a,r=randSetup)=>window.GameEngine.shuffle(a,r);
const reduced=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches;
/* the runs: labels for the status line and best list */
const RUNS={
  tto:{short:"1949",train:"Extra 812 East"},
  twc:{short:"Modern",train:"KV 812 East"},
  yard:{short:"Yard job",train:"Ironton yard job"},
  sigs:{short:"Speed signals",train:"Extra 812 East"},
  sigr:{short:"Route signals",train:"KV 812 East"}};

/* ---------- the railroad ---------- */
/* The railroad's tables and the semaphore picture: run-data.js, which the answer key reads too. */
const {STATIONS,SHEET_NOTES,semSvg}=window.ExtraEastData;
const LAST=STATIONS.length-1;

/* The run: one object for the page's life, which begin() empties and refills, so the other files can hold it. */
const state=/** @type {ExamRun} */({});

/**
 * One run: the engine's RunState (js/game-engine.js) plus the railroad's own fields. Each era's start function adds
 * the fields it needs (tt, meet, box5, pools and others).
 * @typedef {import("../js/game-engine.js").RunState & {
 *   era:"tto"|"twc"|"yard"|"sigs"|"sigr", pos:number, start:number, fus:number, torp:number, used:Set<string>,
 *   inSiding:boolean, orders:Object[], legs:number, par:number, startedAt:number, yloc:string,
 *   jobs:{done:boolean}[], ytrack:number, parAdd:number, passed:number[], moving?:string, tt?:Object
 * }} ExamRun
 */
/** @param {ExamRun["era"]} era @returns {ExamRun} */
function newState(era){
  return {era,clock:360,pos:0,marks:0,misses:[],log:[],fus:0,torp:0,ended:false,start:360,
    used:new Set(),inSiding:true,orders:[],legs:0,par:0,startedAt:Date.now(),yloc:"eng",jobs:[],ytrack:4,parAdd:0,
    passed:[]};
}

/* ---------- scene engine ---------- */
const ENGINE=window.GameEngine.createEngine({
  state:()=>state,
  render:()=>{
    renderStatus();
    renderSheet();
  },
  hereName:()=>hereName(),
  addTime:m=>addTime(m),
  costMinutes:c=>c.min,
  choiceRandom:()=>randChoices,
  srcHtml:o=>esc(srcLabel(o.src)),
  finish:(t,f)=>finish(t,f),
  lockGo:true,
  words:{endVerdict:"Run over.",endText:"The run ended here.",
    marksText:"Five marks on the record. You are pulled from service.",
    smallTag:"<small style='font-size:14px;font-family:var(--mono)'>"}});
const {push,front,next,log,scene,ask,info}=ENGINE;
function addTime(m){
  state.clock+=m;
}
function hereName(){
  if(state.era==="yard")return X.YLOC[state.yloc].n;
  return state.moving?state.moving:STATIONS[state.pos].n;
}

/* ---------- map ---------- */
let MW=600; // map width in SVG units; narrower on phones so the labels stay readable
const MX=mp=>24+(mp-100)/46*(MW-48);
let trainMp=100;
function renderMap(){
  if(state.era==="yard"){
    X.renderYardMap();
    return;
  }
  const box=$("xwMap");
  MW=box.clientWidth&&box.clientWidth<560?340:600;
  const W=MW,y=52,trainX=MX(trainMp);
  let s=`<svg viewBox="0 0 ${W} 94" role="img" aria-label="Line map, Ashby to Ironton, train at ${esc(hereName())}">`;
  // yard limits
  s+=`<rect x="${MX(100)-12}" y="${y-16}" width="${W>400?32:22}" height="32" fill="#e8dfc4"/><rect `+
    `x="${MX(146)-(W>400?20:10)}" y="${y-16}" width="${W>400?32:22}" height="32" fill="#e8dfc4"/>`;
  if(W>400){
    s+=`<text x="${MX(100)+3}" y="${y-20}" font-size="8.5" text-anchor="middle" fill="#5d5a4e">YARD `+
      `LIMITS</text><text x="${MX(146)-3}" y="${y-20}" font-size="8.5" text-anchor="middle" `+
      `fill="#5d5a4e">YARD LIMITS</text>`;
  }
  s+=`<line x1="${MX(100)-10}" y1="${y}" x2="${MX(146)+10}" y2="${y}" stroke="#1d2733" stroke-width="2.5"/>`;
  s+=`<path d="M${MX(140)+(W>400?30:18)} ${y} L${MX(140)+(W>400?38:24)} ${y+5} L${MX(146)+10} ${y+5}" `+
    `fill="none" stroke="#1d2733" stroke-width="2"/>`;
  STATIONS.forEach((st,i)=>{
    const x=MX(st.mp);
    const sw=W>400?26:15;
    if(st.sd){
      s+=`<path d="M${x-sw} ${y} L${x-sw+7} ${y-9} L${x+sw-7} ${y-9} L${x+sw} ${y}" fill="none" `+
        `stroke="#1d2733" stroke-width="1.6"/>`;
    }
    s+=`<line x1="${x}" y1="${y+5}" x2="${x}" y2="${y+11}" stroke="#1d2733" stroke-width="1.2"/>`;
    s+=`<text x="${x}" y="${y+24}" font-size="13" font-weight="${i===state.pos&&!state.moving?700:400}" `+
      `text-anchor="middle">${st.n[0]}</text>`;
    if(st.off)s+=`<text x="${x}" y="${y+35}" font-size="8" text-anchor="middle" fill="#a3302b">D</text>`;
  });
  s+=`<g id="xwTrain" transform="translate(${trainX} 0)"><rect x="-13" `+
    `y="${y-(state.inSiding&&!state.moving?15:6)}" width="26" height="10" rx="2" fill="#a3302b"/><text `+
    `x="0" y="${y-(state.inSiding&&!state.moving?7:-2)}" font-size="7.5" text-anchor="middle" `+
    `fill="#fff" font-weight="700">812</text></g>`;
  s+=`</svg>`;
  $("xwMap").innerHTML=s;
}
function animateTo(idx,done){
  $("xwScene").querySelectorAll("button").forEach(b=>b.disabled=true);
  const x0=trainMp,x1=STATIONS[idx].mp;
  if(reduced){
    trainMp=x1;
    renderMap();
    done();
    return;
  }
  const t0=performance.now(),dur=Math.min(1800,350+Math.abs(x1-x0)*80);
  state.inSiding=false;
  let over=false;
  const end=()=>{
    if(over)return;
    over=true;
    trainMp=x1;
    done();
  };
  function step(t){
    if(over)return;
    const k=Math.min(1,(t-t0)/dur),e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
    trainMp=x0+(x1-x0)*e;
    const g=document.getElementById("xwTrain");
    if(g)g.setAttribute("transform",`translate(${MX(trainMp)} 0)`);
    else renderMap();
    if(k<1)requestAnimationFrame(step);
    else end();
  }
  renderMap();
  requestAnimationFrame(step);
  setTimeout(end,dur+400); // animation frames pause in hidden tabs; the run must not
}
/* A stretch from station `from` to `to` for the runs that go a station at a time (modern, signals): the scenes that
   events() returns as the train leaves, then the run to `to`, its running time and the log. */
function leg(from,to,events){
  return ()=>{
    state.moving=STATIONS[from].n+" and "+STATIONS[to].n;
    state.inSiding=false;
    front(...events(),()=>animateTo(to,()=>{
      addTime(runTime(from,to));
      state.pos=to;
      state.moving=null;
      log("At "+STATIONS[to].n);
      next();
    }));
    next();
  };
}
/* Running time from station k to j on this run's leg times. */
function runTime(k,j){
  let m=0;
  for(let i=k;i<j;i++)m+=state.tt.leg[i];
  return m;
}

/* ---------- status ---------- */
function renderStatus(){
  let at;
  if(state.era==="yard")at=(/Ironton/.test(X.YLOC[state.yloc].n)?"":"Ironton, ")+X.YLOC[state.yloc].n;
  else if(state.moving)at="between "+state.moving;
  else at=STATIONS[state.pos].n+(state.inSiding&&state.pos>0&&state.pos<LAST?" (siding)":"");
  let h=`<span><span class="lbl">Time</span><b>${fmt(state.clock)}</b></span><span><span `+
    `class="lbl">At</span>${esc(at)}</span><span><span `+
    `class="lbl">${state.era==="yard"?"Job":"Train"}</span>${RUNS[state.era].train}</span><span `+
    `class="marks"><span class="lbl">Marks</span><b>${state.marks}</b>/${MAX_MARKS}</span>`;
  if(state.era==="tto")h+=`<span><span class="lbl">Caboose</span>${state.fus} fusees · ${state.torp} torpedoes</span>`;
  $("xwStatus").innerHTML=h;
  renderMap();
}

/* ---------- events on the road and at stations ---------- */
function drawRoad(){
  return drawFrom("road",state.era==="tto"?X.ROAD_TTO:X.ROAD_TWC,.7);
}
function drawStation(){
  return drawFrom("stn",state.era==="tto"?X.STN_TTO:[],.6);
}
function drawFrom(key,pool,p){
  if(!pool.length)return null;
  // Each kind of draw has its own stream, so the n-th draw does not depend on how many draws of other kinds came first.
  state.pools=state.pools||{};
  const st=state.pools[key]=state.pools[key]||{r:Math.random,left:[]};
  if(st.r()>p)return null;
  if(!st.left.length)st.left=shuffle(pool.map((_,i)=>i),st.r);
  const i=st.left.pop();
  return pool[i]();
}

/* ---------- the end ---------- */
function finish(text,failed){
  if(state.ended)return;
  state.ended=true;
  const time=state.clock-state.start;
  if(state.era==="tto"&&!failed)state.par=X.solvePar();
  const par=state.par&&isFinite(state.par)?state.par-state.start:null;
  let verdict,cls="";
  if(failed){
    verdict="Pulled from service";
  }else if(state.marks===0&&(par===null||time<=par+15+(state.hotDelay||0))){
    verdict="Clean run";
    cls="good";
  }else if(state.marks<=1){
    verdict="Good run";
    cls="good";
  }else verdict="Marked up";
  const secs=[...new Set(state.misses.map(m=>m.sec))];
  const missHtml=state.misses.length?state.misses.map(m=>`<details${m.end?" open":""}><summary>${esc(m.title)}</summary><p>${esc(m.why)}</p><p `+
      `class="src">${esc(srcLabel(m.src))} · <a href="index.html#learn-${m.sec}">Study: `+
      `${esc(SEC[m.sec])}</a></p></details>`).join(""):"<p>No rules missed.</p>";
  scene(failed?hereName():"Ironton",
    failed?"The run ends":state.era==="yard"?"Tied up at Ironton":"In at Ironton",
    `<span class="xw-stamp ${cls}">${verdict}</span><p>${esc(text)}</p>
     <div class="xw-end"><div class="score"><div><b>${failed?"—":fmt(state.clock)}</b><span>${state.era==="yard"?"Tied up at":"In at"}</span></div><div><b>${Math.floor(time/60)}h ${String(time%60).padStart(2,"0")}</b><span>${state.era==="yard"?"On the job":"On the road"}</span></div>${par!==null&&!failed?`<div><b>${Math.floor(par/60)}h ${String(Math.round(par)%60).padStart(2,"0")}</b><span>Fastest legal run${state.hotDelay?", no hot box":""}</span></div>`:""}<div><b>${state.marks}</b><span>Marks</span></div>${state.era==="tto"?`<div><b>${state.fus}/${state.torp}</b><span>Fusees/torpedoes left</span></div>`:""}</div>
     <h3 style="font-family:var(--font-display);margin:10px 0 4px;font-size:20px">Service record</h3><div style="display:flex;flex-direction:column;gap:6px">${missHtml}</div>
     ${secs.length?`<p style="margin-top:8px">Study next: ${secs.map(s=>`<a href="index.html#learn-${s}">${esc(SEC[s])}</a>`).join(" · ")}</p>`:""}</div>
     <div class="choices" style="flex-direction:row;flex-wrap:wrap"><button class="xw-btn primary" id="again">Run it again</button><button class="xw-btn" id="home">Choose another run</button></div>`);
  const runs=store.get("xw_runs",[]);
  runs.unshift({era:state.era,when:Date.now(),marks:state.marks,time,failed,verdict});
  store.set("xw_runs",runs.slice(0,20));
  const era=state.era;
  $("again").onclick=()=>begin(era);
  $("home").onclick=showStart;
}

/* ---------- the time-table and orders panel ---------- */
const notesHtml=items=>`<div class="xw-si"><b>Special instructions</b><ul>${items.map(t=>`<li>${t}</li>`).join("")}</ul></div>`;
/* A sheet's list box: a heading and one line per item, or `none` when there are none. */
const listHtml=(head,items,none)=>`<div class="xw-orders"><b>${head}</b>`+
  `${items.length?items.map(t=>`<div class="ord">${t}</div>`).join(""):none}</div>`;
const SHEET_HEAD="<h3>Kestrel Valley · Second Subdivision</h3>";
const hereRow=i=>i===state.pos&&!state.moving?"here":"";

function sheetSignals(){
  const sp=state.era==="sigs";
  const manual=sp?["Automatic block signals, except manual block "+STATIONS[2].n+" to "+STATIONS[3].n+", worked by "+
    "the operators.","Block signals govern trains in the same direction (Rule 251)."]:[];
  return SHEET_HEAD+`<div class="sub">${sp?"Automatic block signals · Standard Code speed signals":
      "Route signals · CP Hollis worked by a control operator"}</div>`+
    listHtml("Signals passed",state.passed.slice(-8).map(esc),'<div class="ord">None yet</div>')+
    notesHtml([...manual,...SHEET_NOTES.signals]);
}
function sheetYard(){
  return `<h3>Ironton yard job</h3><div class="sub">Engine KV 1502 · yardmaster on duty</div>`+
    listHtml("Work list",state.jobs.map(j=>`${j.done?"✓ ":""}${esc(j.t)}`),"")+notesHtml(SHEET_NOTES.yard);
}
/* The 1949 time-table: the regular trains (westward first), the meet's extra once ordered, and the extra's running
   times. A train an order made late shows its new time in red. */
function sheetTTO(){
  const tr=state.tt.trains.filter(t=>!t.hidden&&!t.meetOnly);
  const cols=[...tr.filter(t=>t.dir==="W"),...tr.filter(t=>t.dir==="E")];
  if(state.meet&&!state.meet.tr.hidden)cols.push(state.meet.tr);
  const short={"First class":"1st","Second class":"2nd","Extra":"extra"};
  const cell=(t,i)=>{
    if(t.meetOnly)return `<td>${i===6?"meet":""}</td>`;
    const known=state.orders.some(o=>o.tr===t);
    return `<td>${known&&t.late&&t.lateAt&&t.lateAt[i]?
      `<span class="late"><s>${fmt(t.t[i])}</s><b>${fmt(t.t[i]+t.late)}</b></span>`:fmt(t.t[i])}</td>`;
  };
  const rows=STATIONS.map((st,i)=>`<tr class="${hereRow(i)}"><td class="stn">${esc(st.n)}<small>MP `+
    `${st.mp.toFixed(1)}${st.off?" · D":""}${st.sd?"":" · no siding"}</small></td>`+
    cols.map(t=>cell(t,i)).join("")+`<td class="pencil">${i<LAST?state.tt.leg[i]:""}</td></tr>`).join("");
  let h=SHEET_HEAD+`<div class="sub">Time-table No 12 · single track, double Hollis to Ironton · D = open `+
    `office</div><div class="xw-tt" tabindex="0"><table><thead><tr><th>Station</th>`+
    cols.map(t=>`<th>${esc(t.name)}<small>${t.dir==="W"?"West":"East"} · ${esc(short[t.cls]||t.cls)}</small></th>`).join("")+
    `<th>X 812 E<small>run min</small></th></tr></thead><tbody>${rows}</tbody></table></div>`+notesHtml(SHEET_NOTES.tto);
  if(state.orders.length){
    h+=listHtml("Orders held",state.orders.map(o=>`No ${o.no}: ${esc(o.text)}<span class="ok">OK</span>`),"");
  }
  return h;
}
/* The modern run's station list: sidings, notes and the train's running times. */
function sheetTWC(){
  const note=(st,i)=>st.yl?"yard limits":i===4?"tunnel":i===7?"double track east":"";
  const rows=STATIONS.map((st,i)=>`<tr class="${hereRow(i)}"><td class="stn">${esc(st.n)}<small>MP `+
    `${st.mp.toFixed(1)}</small></td><td>${st.sd?"yes":"no"}</td><td>${note(st,i)}</td><td `+
    `class="pencil">${i<LAST?state.tt.leg[i]:""}</td></tr>`).join("");
  return SHEET_HEAD+`<div class="sub">Track warrant control · dark territory · double track Hollis to Ironton</div>`+
    `<div class="xw-tt" tabindex="0"><table><thead><tr><th>Station</th><th>Siding</th><th>Notes</th><th>KV 812 `+
    `E<small>run min</small></th></tr></thead><tbody>${rows}</tbody></table></div>`+notesHtml(SHEET_NOTES.twc);
}
const SHEETS={tto:sheetTTO,twc:sheetTWC,yard:sheetYard,sigs:sheetSignals,sigr:sheetSignals};
function renderSheet(){
  const el=$("xwSheet");
  if(!state.tt){
    el.innerHTML="";
    return;
  }
  const sheet=SHEETS[state.era];
  if(!sheet)throw new Error("Extra East: no train sheet for run "+state.era);
  el.innerHTML=sheet();
}

/* ---------- start ---------- */
/* Each era's start function, given by its run file. */
const STARTS={tto:()=>X.startTTO(),yard:()=>X.startYARD(),sigs:()=>X.startSIG("speed"),sigr:()=>X.startSIG("route"),
  twc:()=>X.startTWC()};
function begin(era){
  if(!Object.hasOwn(STARTS,era))throw new Error("Extra East: no run "+era);
  randSetup=randOrders=randChoices=Math.random;
  for(const k of Object.keys(state))delete state[k];
  Object.assign(state,newState(era));
  ENGINE.reset();
  $("xwLog").innerHTML="";
  trainMp=100;
  $("xwStart").hidden=true;
  $("xwGame").hidden=false;
  renderStatus();
  renderSheet();
  window.scrollTo({top:$("xw").getBoundingClientRect().top+scrollY-80,behavior:reduced?"auto":"smooth"});
  STARTS[era]();
}
function showStart(){
  $("xwStart").hidden=false;
  $("xwGame").hidden=true;
  $("sigSys").closest(".xw-switch").classList.toggle("on",$("sigSys").checked);
  $("sigRules").textContent=sigEra()==="sigr"?"Rulebook: the Signals guide (route signals and plates)":
    "Rulebook: 1949 Standard Code Rules 281 to 292, with the Signals guide's plates";
  const runs=store.get("xw_runs",[]);
  const best=e=>{
    const r=runs.filter(x=>x.era===e&&!x.failed).sort((a,b)=>a.marks-b.marks||a.time-b.time)[0];
    return r?`${r.verdict}, ${r.marks} mark${r.marks===1?"":"s"}, ${Math.floor(r.time/60)}h `+
      `${String(r.time%60).padStart(2,"0")}`:"none yet";
  };
  $("xwBest").textContent=runs.length?
    `Your best in this browser. ${Object.keys(RUNS).map(e=>RUNS[e].short+": "+best(e)).join(". ")}.`:"";
}
const sigEra=()=>$("sigSys").checked?"sigr":"sigs";
$("sigSys").checked=store.get("xw_sigsys","sigs")==="sigr";
$("sigSys").onchange=()=>{
  store.set("xw_sigsys",sigEra());
  showStart();
};
document.querySelectorAll("[data-era]").forEach(b=>b.onclick=()=>begin(b.dataset.era==="sig"?sigEra():b.dataset.era));
showStart();

/* ---------- the interface with the run files ---------- */
/* SHARED: what run.js shares. Each run file takes its names with X.take (an unshared name stops the page). GIVES:
   what run.js reads back from each run file, which hands them over with X.give. */
const SHARED={state,$,fmt,esc,rnd,pick,shuffle,randSetup:()=>randSetup(),randOrders:()=>randOrders(),reduced,STATIONS,
  LAST,addTime,renderMap,animateTo,leg,renderStatus,renderSheet,runTime,drawRoad,drawStation,semSvg,finish,push,front,
  next,log,scene,ask,info};
const GIVES={"run-tto.js":["startTTO","solvePar"],"run-1949.js":["ROAD_TTO","STN_TTO"],
  "run-modern.js":["startTWC","ROAD_TWC","warrantForm"],
  "run-signals.js":["startSIG"],
  "run-yard.js":["YLOC","renderYardMap","startYARD"]};
function take(file,names){
  const missing=names.filter(n=>!Object.hasOwn(SHARED,n));
  if(missing.length)throw new Error(`${file} takes ${missing.join(", ")}, which run.js does not share`);
  return Object.fromEntries(names.map(n=>[n,SHARED[n]]));
}
function give(file,names){ // exactly the names GIVES lists for the file, each defined
  const want=GIVES[file],got=Object.keys(names);
  if(!want)throw new Error(`run.js reads nothing from ${file}`);
  if(want.some(n=>names[n]===undefined)||got.some(n=>!want.includes(n)))
    throw new Error(`${file} gives ${got.join(", ")}; run.js reads ${want.join(", ")}`);
  Object.assign(X,names);
}
Object.assign(X,SHARED,{take,give});
})();
