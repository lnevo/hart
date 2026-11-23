(function(){
"use strict";
/* Extra East: HART Railroad. The engine is Extra East's (exam/run.js): a queue of scenes, each a
   decision with a source. The runs themselves are in runs.js; this file draws the island, keeps the
   clock and the record, and scores the shift. */
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let R=Math.random,RO=Math.random;
function seeded(str){let h=1779033703^str.length;for(let i=0;i<str.length;i++){h=Math.imul(h^str.charCodeAt(i),3432918353);h=h<<13|h>>>19}
  let a=h>>>0;return ()=>{a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
const today=()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0")};
const rnd=(a,b)=>a+Math.floor(R()*(b-a+1));
const pick=a=>a[Math.floor(R()*a.length)];
const shuffle=(a,r)=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(r()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
const fmt=m=>{m=Math.round(m);m=((m%1440)+1440)%1440;const h=Math.floor(m/60),mm=m%60;return h+":"+String(mm).padStart(2,"0")};
const store={get(k,d){try{const v=localStorage.getItem(k);return v?JSON.parse(v):d}catch(e){return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
const reduced=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches;

/* Sources. GC/YL point into the C&E study deck; PV is Mark Connolly's P&OV blog, linked post by post. */
const DECK="../exam/index.html";
const POV="../library/pittsburgh-ohio-valley-railway.html";
const SEC={gcor:"GCOR crew & speed",sig:"Signals & whistles",def:"Definitions",yl:"Yard limits",pov:"The P&OV jobs",
  sup:"Superiority & movement",to:"Train orders",sem:"Semaphores",twc:"Track warrants"};
const SRC={GC:"GCOR",YL:"Yard Limits guide",PV:"Mark Connolly's P&OV blog,",SC:"1949 Standard Code",TT:"TT&TO primer",SG:"Signals guide",SM:"Semaphores guide"};
const srcLabel=s=>s.replace(/^(?:(GC|YL|PV)\b( ·)?|(SC|TT|SG|SM)\b)/,(m,k,_,j)=>SRC[k||j]); // GC, YL and PV drop their dot; the Standard Code and guides keep it
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
let S=null;
function newState(id){return {run:id,pace:1,clock:0,start:0,marks:0,misses:[],log:[],ended:false,jobs:[],parAdd:0,par:0,units:{},lead:"",d:{},plants:[]}}

const placeName=()=>S.def.where?S.def.where(S):(LOC[S.units[S.lead]]?LOC[S.units[S.lead]].n:"");
function renderMap(){
  const box=$("xwMap");if(!S)return;
  if(S.def.map){box.innerHTML=S.def.map(S,H);return} // a road run draws its own line
  const W=600,k=box.clientWidth&&box.clientWidth<560?1.3:1,fs=n=>(n*k).toFixed(1);
  const where=placeName();
  let s=`<svg viewBox="0 0 ${W} 150" role="img" aria-label="Track sketch of the east end of Neville Island, ${esc(S.def.code)} at ${esc(where)}">`;
  s+=`<rect x="0" y="0" width="${W}" height="150" fill="var(--river)"/><rect x="0" y="11" width="${W}" height="129" fill="var(--land)"/>`;
  s+=`<text x="8" y="8" font-size="${fs(6.5)}" class="water">OHIO RIVER · MAIN CHANNEL</text><text x="${W-8}" y="148" font-size="${fs(6.5)}" text-anchor="end" class="water">BACK CHANNEL</text>`;
  s+=`<text x="${W-8}" y="8" font-size="${fs(6)}" text-anchor="end" class="water">${esc(S.def.year)}</text>`;
  // the road across the island at the main crossing
  s+=`<line x1="345" y1="11" x2="345" y2="140" stroke="var(--muted)" stroke-width="1" stroke-dasharray="3 3" opacity=".55"/>`;
  // running tracks
  s+=`<g fill="none" stroke="var(--ink)" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round">`;
  s+=`<path d="M10 40 H590"/>`; // north line: foundry, West Yard, coke plant, furnace lead, E1
  s+=`<path d="M16 140 L60 96 H576"/>`; // PC&Y off the bridge, Y Interchange, Gulf Crossing, South Runner, South Yard, ladles, Furnace Runner
  s+=`<path d="M220 96 L248 68 H400 L428 40"/>`; // the scale track: South Yard, S9, the scale, the main crossing, coke plant lead
  s+=`<path d="M100 96 L156 40"/>`; // West Yard ladder
  s+=`<path d="M270 96 L306 132 H440 L476 96"/>`; // East Runner along the back channel
  s+=`</g><g fill="none" stroke="var(--ink)" stroke-width="1.4" stroke-linecap="round">`;
  s+=`<path d="M190 40 L206 24"/><path d="M256 40 L272 24"/><path d="M436 40 L452 24"/><path d="M520 40 L540 20"/>`; // Stucki, chemical, dumper, F1
  s+=`<path d="M196 96 L204 104 H250 M204 104 L212 112 H250"/>`; // South Yard tracks
  s+=`<path d="M392 96 L408 112 H448"/>`; // East Yard and E9
  s+=`<path d="M120 40 L128 32 H170"/>`; // a West Yard track
  s+=`</g>`;
  // the scale, the Gulf Crossing, the bumping block, the plant
  s+=`<rect x="305" y="64.5" width="14" height="7" fill="none" stroke="var(--rust)" stroke-width="1.6"/>`;
  s+=`<line x1="80" y1="88" x2="80" y2="104" stroke="var(--muted)" stroke-width="1" stroke-dasharray="2 2"/>`;
  s+=`<line x1="579" y1="91" x2="579" y2="101" stroke="var(--ink)" stroke-width="2.5"/>`;
  s+=`<g fill="var(--muted)" opacity=".8"><rect x="472" y="46" width="32" height="8"/><rect x="528" y="12" width="7" height="14"/><rect x="532" y="80" width="7" height="10"/><rect x="350" y="107" width="5" height="10"/></g>`;
  s+=`<text x="359" y="116" font-size="${fs(6)}" class="lbl">${esc((S.def.cement||"cement").toUpperCase())}</text>`;
  if(S.def.foundryClosed)s+=`<text x="6" y="52" font-size="${fs(6)}" class="lbl">CLOSED</text>`;
  Object.values(LOC).forEach(L=>{if(L.t)s+=`<text x="${L.lx}" y="${L.ly}" font-size="${fs(6.8)}" text-anchor="${L.a||"middle"}" class="lbl">${esc(L.t)}</text>`});
  // the engines, the job's own lit
  Object.entries(S.units).forEach(([u,at])=>{const L=LOC[at];if(!L)return;const me=u===S.lead;
    s+=`<g transform="translate(${L.x} ${L.y})"><rect x="-11" y="-5" width="22" height="10" rx="2" fill="${me?"var(--green)":"var(--muted)"}" stroke="${me?"var(--glow)":"#fff"}" stroke-width="${me?1.4:.8}"/><text x="0" y="2.6" font-size="${fs(6.8)}" text-anchor="middle" fill="#fff" font-weight="700">${esc(u)}</text></g>`});
  box.innerHTML=s+`</svg>`;
}
function renderStatus(){
  if(!S)return;
  const end=S.def.end,left=end-S.clock;
  const where=placeName();
  $("xwStatus").innerHTML=`<span><span class="lbl">Job</span><b>${esc(S.def.code)}</b></span><span><span class="lbl">Clock</span><b>${fmt(S.clock)}</b></span><span><span class="lbl">Quits</span>${fmt(end)}${left<0?` <i class="over">+${Math.round(-left)} min</i>`:""}</span><span><span class="lbl">At</span>${esc(where)}</span><span class="marks"><span class="lbl">Marks</span><b>${S.marks}</b>/${MAXMARKS}</span>`;
  renderMap();
}
const MAXMARKS=5;

/* ---------- scene engine ---------- */
let queue=[];
function next(){if(S.ended)return;const f=queue.shift();if(f)f()}
function log(t){S.log.push(fmt(S.clock)+"  "+t);const li=document.createElement("li");li.textContent=fmt(S.clock)+"  "+t;$("xwLog").appendChild(li)}
function addTime(m){const t=Math.round(m*S.pace);S.clock+=t;return t} // a shift's minutes on the map are its pace times the move's own
function hereName(){if(S.def&&S.def.where)return S.def.where(S);const L=LOC[S.units[S.lead]];return L?L.n:"Neville Island"}
function scene(where,title,html){
  const el=$("xwScene");el.classList.remove("in");void el.offsetWidth;el.classList.add("in");
  el.innerHTML=`<div class="where"><span>${esc(where)}</span><span>${fmt(S.clock)}</span></div><h2>${esc(title)}</h2>${html}`;
  renderStatus();renderSheet();
  sceneIntoView(el);
  return el;
}
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
const srcHtml=o=>{const t=esc(srcLabel(o.src));return o.url?`<a href="${o.url.startsWith("http")?o.url:TUMBLR+o.url}" rel="noopener">${t}</a>`:t};
/* A decision. right = the answer; wrong = [[text, cost, why?]]; cost {min, marks, end, endText}. */
function ask(o){
  return ()=>{
    const r=S.daily?seeded(S.daily+"|"+o.title+"|"+o.right):RO;
    const opts=shuffle([{t:o.right,ok:true,c:o.ok||{}},...o.wrong.map(w=>({t:w[0],ok:false,c:w[1]||{min:5,marks:1},why:w[2]}))],r);
    const el=scene(o.where||hereName(),o.title,`<p>${o.body}</p>${o.extra||""}<div class="choices">${opts.map((x,i)=>`<button class="xw-btn opt" data-i="${i}">${esc(x.t)}</button>`).join("")}</div><div class="result" hidden></div>`);
    const box=el.querySelector(".choices");
    box.querySelectorAll(".opt").forEach(b=>b.onclick=()=>{
      const x=opts[+b.dataset.i];
      box.classList.add("done");box.querySelectorAll(".opt").forEach(z=>z.disabled=true);
      b.classList.add(x.ok?"right":"wrong");
      if(!x.ok)box.querySelectorAll(".opt").forEach((z,i)=>{if(opts[i].ok)z.classList.add("right")});
      const c=x.c||{};
      if(c.min)addTime(c.min);const cm=Math.round((c.min||0)*S.pace);
      if(c.marks)S.marks+=c.marks;
      const res=el.querySelector(".result");res.hidden=false;
      const cost=[];if(c.min)cost.push("+"+cm+" min");if(c.marks)cost.push("+"+c.marks+" mark"+(c.marks>1?"s":""));
      const why=(!x.ok&&x.why?x.why+" ":"")+o.why;
      const over=c.end||S.marks>=MAXMARKS;
      res.innerHTML=`<div class="verdict ${x.ok?"ok":"no"}">${x.ok?(o.okText||"Right."):(c.end?"Shift over.":"Not right.")}${cost.length?` <small>${cost.join(" · ")}</small>`:""}</div><p>${why}</p><div class="src">${srcHtml(o)}</div><div><button class="xw-btn primary" id="xwGo">${over?"See the record":"Continue"}</button></div>`;
      if(!x.ok||o.miss)S.misses.push({title:o.title,why:o.why,src:o.src,url:o.url,sec:o.sec,end:!!c.end}); // miss: right answer, but it records what the player had just done wrong
      log((x.ok?"✓ ":"✗ ")+o.title);
      if(o.after)o.after(x.ok);
      renderStatus();renderSheet();
      const go=$("xwGo");go.focus({preventScroll:true});
      go.onclick=()=>{
        if(c.end){finish(c.endText||"The trainmaster took you off the job.",true);return}
        if(S.marks>=MAXMARKS){finish("Five marks in one shift. The trainmaster took you off the job.",true);return}
        next();
      };
    });
  };
}
function info(where,title,html,btn,after){
  return ()=>{
    const el=scene(where||hereName(),title,`${html}<div><button class="xw-btn primary" id="xwGo">${esc(btn||"Continue")}</button></div>`);
    $("xwGo").onclick=()=>{if(after)after();next()};
    $("xwGo").focus({preventScroll:true});
  };
}
/* Move an engine (the job's own unless named) to a place, taking some minutes; par is the sum of the moves. */
const mv=(to,min,note,unit)=>()=>{S.units[unit||S.lead]=to;S.parAdd+=addTime(min);if(note)log(note);renderStatus();next()};
const wait=(min,note)=>()=>{S.parAdd+=addTime(min);if(note)log(note);renderStatus();next()};
const done=i=>()=>{S.jobs[i].done=true;renderSheet();next()};
/* What a road run (road-engine.js, road.js, passenger.js, pcy.js, pir.js) needs besides the island's helpers: put scenes at the front of the queue, draw its own
   scene, and list a question the player may meet only on some paths (key: no-op here, the answer key's build reads it). */
const front=(...f)=>queue.unshift(...f);
const key=()=>null;
const H={ask,info,mv,wait,done,rnd,pick,fmt,esc,log,addTime,front,scene,key,next,renderStatus,shuffle,srcHtml,finish,$,get S(){return S},get R(){return R}};

/* ---------- the switch list ---------- */
function renderSheet(){
  const el=$("xwSheet");if(!S){el.innerHTML="";return}
  const D=S.def;
  if(D.sheet){el.innerHTML=D.sheet(S,H);return} // a road run prints its own time-table and orders
  el.innerHTML=`<h3>Pittsburgh &amp; Ohio Valley</h3><div class="sub">Switching orders · ${esc(D.code)} ${esc(D.name)} · ${esc(D.dateLine)}</div>
    <div class="xw-orders"><b>Work</b>${S.jobs.map(j=>`<div class="ord${j.done?" done":""}">${j.done?"✓ ":""}${esc(j.t)}</div>`).join("")}</div>
    <div class="xw-si"><b>On the island, ${esc(D.year)}</b><ul>${D.plants.map(p=>`<li>${p}</li>`).join("")}</ul></div>
    <div class="xw-si"><b>Special instructions</b><ul>${D.si.map(p=>`<li>${p}</li>`).join("")}<li>Rules: GCOR.</li></ul></div>`;
}

/* ---------- the end ---------- */
function finish(text,failed){
  if(S.ended)return;S.ended=true;
  const D=S.def,time=S.clock-S.start;
  const par=S.par?Math.round(S.par-S.start):null;
  let verdict,cls="";
  if(failed)verdict="Taken off the job";
  else if(S.marks===0&&(par===null?S.clock<=D.end+15*S.pace:time<=par+15*S.pace)){verdict="Clean shift";cls="good"} // a road run has no par: it is on time if it is in before it quits
  else if(S.marks<=1){verdict="Good shift";cls="good"}
  else verdict="Marked up";
  const secs=[...new Set(S.misses.map(m=>m.sec))];
  const missHtml=S.misses.length?S.misses.map(m=>`<details${m.end?" open":""}><summary>${esc(m.title)}</summary><p>${esc(m.why)}</p><p class="src">${srcHtml(m)} · <a href="${studyHref(m.sec)}">${m.sec==="pov"?"Read: ":"Study: "}${esc(SEC[m.sec])}</a></p></details>`).join(""):"<p>No rules missed.</p>";
  const el=scene(failed?hereName():D.endPlace,failed?"The shift ends":"Tied up",
    `<span class="xw-stamp ${cls}">${verdict}</span><p>${esc(text)}</p>
     <div class="xw-end"><div class="score"><div><b>${failed?"—":fmt(S.clock)}</b><span>Tied up at</span></div><div><b>${Math.floor(time/60)}h ${String(time%60).padStart(2,"0")}</b><span>On the job</span></div>${par!==null&&!failed?`<div><b>${Math.floor(par/60)}h ${String(Math.round(par)%60).padStart(2,"0")}</b><span>The work, no mistakes</span></div>`:""}<div><b>${S.marks}</b><span>Marks</span></div></div>
     ${D.coda&&!failed?`<div class="xw-coda">${D.coda}</div>`:""}
     <h3 class="rec">Service record</h3><div class="miss">${missHtml}</div>
     ${secs.length?`<p class="study">Study next: ${secs.map(s=>`<a href="${studyHref(s)}">${esc(SEC[s])}</a>`).join(" · ")}</p>`:""}</div>
     <div class="choices row"><button class="xw-btn primary" id="again">${S.daily?"Replay today's shift":"Work it again"}</button><button class="xw-btn" id="home">Choose another job</button></div>`);
  const runs=store.get("ni_runs",[]);runs.unshift({run:S.run,when:Date.now(),marks:S.marks,time,failed,verdict,daily:S.daily});store.set("ni_runs",runs.slice(0,30));
  const id=S.run,daily=S.daily;
  if(daily){
    const key="ni_daily_"+daily+"_"+id,stored=store.get(key,null);
    const mine={id:S.attempt,verdict,marks:S.marks,time,failed};
    const first=stored&&stored.id!==S.attempt?stored:null;
    if(!first)store.set(key,mine);
    const rec=first||mine;
    const line=`Extra East: HART Railroad, ${daily}, ${D.code} ${D.name}: ${rec.verdict}, ${rec.marks} mark${rec.marks===1?"":"s"}${rec.failed?"":", "+Math.floor(rec.time/60)+"h "+String(rec.time%60).padStart(2,"0")+"m on the job"}. ${location.origin.startsWith("http")?location.origin+location.pathname:"hartrailroad.com/play/"}`;
    const box=document.createElement("div");box.className="xw-daily";
    box.innerHTML=`<p>${first?"Your first try at today's shift counts for the day; this replay does not change it.":"This is your result for today's shift. Replays are for practice and do not change it."}</p><div class="xw-share">${esc(line)}</div><div><button class="xw-btn" id="copy">Copy the result</button></div>`;
    el.querySelector(".xw-end").appendChild(box);
    $("copy").onclick=()=>{const ok=()=>{$("copy").textContent="Copied"};
      if(navigator.clipboard)navigator.clipboard.writeText(line).then(ok,()=>{$("copy").textContent="Select the text above to copy it"});else $("copy").textContent="Select the text above to copy it"};
  }
  $("again").onclick=()=>begin(id,daily);
  $("home").onclick=showStart;
}

/* ---------- start ---------- */
let RUNS={};
function begin(id,daily){
  daily=null; // no daily shift: the draws barely change from day to day (owner, 2026-11-22); the daily path is kept for a pool-based draw later
  if(daily===true)daily=today();
  if(daily){R=seeded("neville|"+daily+"|"+id+"|setup")}else R=RO=Math.random;
  S=newState(id);S.daily=daily||null;queue=[];
  if(daily){S.attempt=Date.now();const key="ni_daily_"+daily+"_"+id;if(!store.get(key,null))store.set(key,{id:S.attempt,verdict:"Did not finish",marks:0,time:0,failed:true})}
  $("xwLog").innerHTML="";
  const def=RUNS[id];S.def=def;S.pace=def.pace||1;S.clock=S.start=def.start;S.lead=def.engine;S.units=Object.assign({},def.units);
  const shift=def.build(H);S.jobs=shift.work.map(t=>({t,done:false}));
  queue=shift.steps.concat([()=>{S.par=shift.noPar?0:S.start+S.parAdd;const t=shift.end?shift.end():def.tieUp;log("Tied up");finish(t.replace("{t}",fmt(S.clock)),false)}]);
  $("xwStart").hidden=true;$("xwGame").hidden=false;
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
const SECTIONS=[["def","Definitions"],["sup","Superiority & movement"],["to","Train orders"],["sig","Signals & whistles"],
  ["sem","Semaphores"],["yl","Yard limits"],["twc","Track warrants"],["gcor","GCOR crew & speed"]];
const TAG={def:"Definitions",sup:"Superiority",to:"Train orders",sig:"Signals",sem:"Semaphores",yl:"Yard limits",twc:"Warrants",gcor:"GCOR"};
/* The start screen, built from the cards in index.html: each group is a tab, each card a row that opens on a tap to
   its story and its button, and a row of section chips shows only the runs that test that section. */
function renderCover(){
  const box=$("xwCover");if(!box)return;
  const groups=[...document.querySelectorAll(".xw-group")];if(!groups.length)return;
  // rows: the title, the kind line and the section tags stay in view; the story and the button open on a tap.
  // A summary holds phrasing content and one heading, so the kind line and the tags become spans.
  document.querySelectorAll(".xw-start .card").forEach(card=>{
    const b=card.querySelector("[data-run]"),def=b&&RUNS[b.dataset.run];if(!def)return;
    const det=document.createElement("details");det.className=card.className+" xw-run";det.dataset.secs=(def.covers||[]).join(" ");
    const sum=document.createElement("summary"),h=card.querySelector("h3"),k=card.querySelector(".kind");
    if(h)sum.appendChild(h);
    const meta=document.createElement("span");meta.className="xw-meta";
    if(k){meta.insertAdjacentHTML("beforeend",`<span class="kind">${k.innerHTML}</span>`);k.remove()}
    const tags=SECTIONS.filter(x=>(def.covers||[]).includes(x[0])).map(x=>`<span>${esc(TAG[x[0]])}</span>`).join("");
    if(tags)meta.insertAdjacentHTML("beforeend",`<span class="xw-tags">${tags}</span>`);
    sum.appendChild(meta);det.appendChild(sum);[...card.childNodes].forEach(n=>det.appendChild(n));
    card.replaceWith(det);
  });
  // one button per group; only the chosen group shows
  const tabs=document.createElement("div");tabs.className="xw-tabs";tabs.setAttribute("aria-label","Groups of runs");
  const pick=id=>{groups.forEach(g=>{g.hidden=g.id!==id});tabs.querySelectorAll("button").forEach(t=>t.setAttribute("aria-pressed",String(t.dataset.g===id)));store.set("ni_tab",id)};
  groups.forEach(g=>{
    const h=g.querySelector(".xw-group-h"),t=document.createElement("button");
    t.type="button";t.dataset.g=g.id;t.setAttribute("aria-controls",g.id);
    t.textContent=h?h.firstChild.textContent.trim():g.id;t.onclick=()=>{clear();pick(g.id)};tabs.appendChild(t);
  });
  groups[0].before(tabs);
  // section chips: All, then each section some run tests
  const used=SECTIONS.filter(([k])=>Object.values(RUNS).some(d=>(d.covers||[]).includes(k)));
  box.innerHTML=`<span class="lbl">Practice a section</span><div class="xw-chips">${[["","All"]].concat(used.map(([k])=>[k,TAG[k]])).map(([k,n])=>
    `<button type="button" data-sec="${k}" aria-pressed="${k===""}">${esc(n)}</button>`).join("")}</div>`;
  const chips=sec=>box.querySelectorAll("button").forEach(c=>c.setAttribute("aria-pressed",String(c.dataset.sec===sec)));
  function clear(){chips("");document.querySelectorAll(".xw-run").forEach(r=>{r.hidden=false});tabs.hidden=false}
  function filter(sec){
    if(!sec){clear();const t=store.get("ni_tab","");pick(groups.some(g=>g.id===t)?t:groups[0].id);return}
    chips(sec);tabs.hidden=true;
    document.querySelectorAll(".xw-run").forEach(r=>{r.hidden=!r.dataset.secs.split(" ").includes(sec)});
    groups.forEach(g=>{g.hidden=!g.querySelector(".xw-run:not([hidden])")});
  }
  box.querySelectorAll("button").forEach(c=>c.onclick=()=>filter(c.dataset.sec));
  // a link to a group (#gChartiers) or to a run's title (#rcoal) shows that group and opens that run
  function follow(){
    const el=location.hash.length>1&&document.getElementById(decodeURIComponent(location.hash.slice(1)));
    const g=el&&(el.classList.contains("xw-group")?el:el.closest(".xw-group"));if(!g)return;
    clear();pick(g.id);const run=el.closest(".xw-run");if(run){run.open=true;el.scrollIntoView({block:"start"})}
  }
  filter("");follow();window.addEventListener("hashchange",follow);
  box.hidden=false;
}
function showStart(){
  $("xwStart").hidden=false;$("xwGame").hidden=true;
  const runs=store.get("ni_runs",[]),d=today();
  document.querySelectorAll("[data-run]").forEach(b=>{
    if(!b.hasAttribute("data-daily"))return;
    const r=store.get("ni_daily_"+d+"_"+b.dataset.run,null);
    b.querySelector("small").textContent=r?`played: ${r.verdict}, ${r.marks} mark${r.marks===1?"":"s"}`:d;
  });
  const rt=$("reliefToday");if(rt)rt.textContent=reliefToday();
  const best=e=>{const r=runs.filter(x=>x.run===e&&!x.failed).sort((a,b)=>a.marks-b.marks||a.time-b.time)[0];return r?`${r.verdict}, ${r.marks} mark${r.marks===1?"":"s"}`:"none yet"};
  $("xwBest").textContent=runs.length?`Your best in this browser. ${Object.keys(RUNS).map(e=>RUNS[e].code+": "+best(e)).join(". ")}.`:"";
}

RUNS=window.NevilleRuns||{};
renderCover();
document.querySelectorAll("[data-run]").forEach(b=>b.onclick=()=>begin(b.dataset.run,b.hasAttribute("data-daily")));
showStart();
})();
