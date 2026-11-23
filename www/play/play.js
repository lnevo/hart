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
/* The next stop on a road run, from the run's own position (a run gives next(S)). Nothing on a run where the player chooses the next stop. */
function nextName(){
  const D=S.def;
  if(D.next)return D.next(S)||"";
  return "";
}
/* The way out of a run: a link in the status bar that asks first, in the page, then goes back to the start screen. */
const exitHtml=()=>S.ended?"":S.leaving
  ?`<span class="xw-exit" role="group" aria-label="Leave this run"><span>Leave this run? It is not saved.</span><button type="button" class="xw-link" data-exit="yes">Leave</button><button type="button" class="xw-link xw-stay" data-exit="no">Stay</button></span>`
  :`<span class="xw-exit"><button type="button" class="xw-link xw-ask" data-exit="ask">Choose another run</button></span>`;
function exitClick(e){
  const b=e&&e.target&&e.target.closest&&e.target.closest("[data-exit]");if(!b||!S)return;
  const a=b.dataset.exit;
  if(a==="yes"){S.ended=true;S.leaving=false;queue=[];showStart();window.scrollTo({top:$("xw").getBoundingClientRect().top+scrollY-80,behavior:"auto"});
    // the first control still on screen: the section chip's clear link, the start-here link, or the first Start button
    const f=document.querySelector&&["#xwClear","#xwHint a","[data-run]"].flatMap(q=>[...document.querySelectorAll(q)]).find(e=>e.offsetParent!==null);if(f&&f.focus)f.focus();return}
  S.leaving=a==="ask";renderStatus();
  const f=$("xwStatus").querySelector(S.leaving?".xw-stay":".xw-ask");if(f)f.focus();
}
function renderStatus(){
  if(!S)return;
  const end=S.def.end,left=end-S.clock;
  const where=placeName(),nx=nextName();
  $("xwStatus").innerHTML=`<span><span class="lbl">Job</span><b>${esc(S.def.code)}</b></span><span><span class="lbl">Clock</span><b>${fmt(S.clock)}</b></span><span><span class="lbl">Quits</span>${fmt(end)}${left<0?` <i class="over">+${Math.round(-left)} min</i>`:""}</span><span><span class="lbl">At</span>${esc(where)}</span>${nx?`<span><span class="lbl">Next</span>${esc(nx)}</span>`:""}<span class="marks"><span class="lbl">Marks</span><b>${S.marks}</b>/${MAXMARKS}</span>${exitHtml()}`;
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
/* On a phone the verdict, the why and Continue can sit below the screen once a choice is made, with the choices above them.
   When Continue is below the screen or the verdict above it, scroll so the verdict sits near the top. Same breakpoint as sceneIntoView. */
function resultIntoView(res,go){
  const vh=window.innerHeight||0;if(!vh||!(window.matchMedia&&matchMedia("(max-width:860px)").matches))return;
  const r=res.getBoundingClientRect(),g=go.getBoundingClientRect();
  if(r.top>=0&&g.bottom<=vh-8)return;
  window.scrollTo({top:r.top+scrollY-70,behavior:reduced?"auto":"smooth"});
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
      resultIntoView(res,go);
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
/* The sheet is drawn again at every scene: keep a table's sideways scroll, and when the table runs wider than the sheet show
   a fade at the right edge and a "more trains" line above it until the last column is in view. */
let cue=null; // redraws the current table's fade and hint; the window calls it on resize
if(typeof window.addEventListener==="function")window.addEventListener("resize",()=>{if(cue)cue()});
function renderSheet(){
  const el=$("xwSheet"),old=S&&el.querySelector(".xw-tt"),sl=old&&old.scrollLeft||0;
  paintSheet();
  const tt=S&&el.querySelector(".xw-tt");if(!tt||!tt.insertAdjacentElement)return;
  const hint=document.createElement("p");hint.className="xw-more";hint.textContent="More trains: scroll sideways \u2192";
  tt.insertAdjacentElement("beforebegin",hint);
  tt.scrollLeft=sl;
  const upd=()=>{const over=tt.scrollWidth>tt.clientWidth+2&&tt.scrollLeft+tt.clientWidth<tt.scrollWidth-2;hint.hidden=!over;tt.classList.toggle("fade",over)};
  tt.addEventListener("scroll",upd,{passive:true});upd();cue=upd;
}
function paintSheet(){
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
  if(D.verdicts)verdict=D.verdicts[verdict]||verdict; // a run may name its own verdicts (the qualifying trip)
  const secs=[...new Set(S.misses.map(m=>m.sec))];
  const slip=par!==null&&!failed?Math.round(time-par):0; // minutes the misses added to the work, so the tie-up time and the last scene's clock agree
  const missHtml=S.misses.length?S.misses.map(m=>`<details${m.end?" open":""}><summary>${esc(m.title)}</summary><p>${esc(m.why)}</p><p class="src">${srcHtml(m)} · <a href="${studyHref(m.sec)}">${m.sec==="pov"?"Read: ":"Study: "}${esc(SEC[m.sec])}</a></p></details>`).join(""):"<p>No rules missed.</p>";
  const nr=suggest(secs);
  const el=scene(failed?hereName():D.endPlace,failed?"The shift ends":"Tied up",
    `<span class="xw-stamp ${cls}">${verdict}</span><p>${esc(text)}</p>
     <div class="xw-end"><div class="score"><div><b>${failed?"—":fmt(S.clock)}</b><span>Tied up at</span></div><div><b>${Math.floor(time/60)}h ${String(time%60).padStart(2,"0")}</b><span>On the job</span></div>${par!==null&&!failed?`<div><b>${Math.floor(par/60)}h ${String(Math.round(par)%60).padStart(2,"0")}</b><span>The work, no mistakes</span></div>`:""}${slip>0?`<div><b>+${slip} min</b><span>from misses</span></div>`:""}<div><b>${S.marks}</b><span>Marks</span></div></div>
     ${D.coda&&!failed?`<div class="xw-coda">${D.coda}</div>`:""}
     <h3 class="rec">Service record</h3><div class="miss">${missHtml}</div>
     <p class="study">${secs.length?`Study next: ${secs.map(s=>`<a href="${studyHref(s)}">${esc(SEC[s])}</a>`).join(" · ")}`:`Every rule is in the <a href="${DECK}">C&amp;E study deck</a>.`} · <a href="answers.html">Answer key</a></p></div>
     <div class="choices row"><button class="xw-btn primary" id="again">${S.daily?"Replay today's shift":"Work it again"}</button>${nr?`<button class="xw-btn" id="nextRun">Try ${esc(RUNS[nr].code)}, ${esc(RUNS[nr].name)}${secs.some(x=>(RUNS[nr].covers||[]).includes(x))?"<small>tests what you missed</small>":""}</button>`:""}<button class="xw-btn" id="home">Choose another job</button></div>`);
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
const suggest=secs=>nextRun(RUNS,S.run,new Set(store.get("ni_runs",[]).filter(r=>!r.failed).map(r=>r.run)),secs);
/* Which cards the start screen shows: covers is the run's list of sections, sec the chip that is on ("" for All). */
const rowShown=(covers,sec)=>!sec||covers.includes(sec); // a card shows with no section chip on, or when its run tests that section
window.PlayLogic={nextRun,rowShown};

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
  $("xwStart").hidden=true;$("xwGame").hidden=false;$("xw").classList.remove("on-start");
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
/* How long a run is, for its card: the typical number of questions over many draws (play_through_test.js prints the means). */
const LEN={j105:"about 10 questions",j110:"about 13 questions",j205:"about 8 questions",j305:"about 7 questions",j115:"about 8 questions",extra:"about 6 questions",ym:"about 8 questions",
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
    const h=card.querySelector("h3");if(h&&!b.querySelector(".xw-vh"))b.insertAdjacentHTML("beforeend",`<span class="xw-vh"> ${esc(h.textContent)}</span>`);
  });
  // section chips: All, then each section some run tests
  const used=SECTIONS.filter(([k])=>Object.values(RUNS).some(d=>(d.covers||[]).includes(k)));
  box.innerHTML=`<div class="xw-coverhead"><span class="lbl" id="xwCoverLbl">Practice a section</span><a class="xw-keylink" href="answers.html">Answer key: every question</a></div><div class="xw-chips" role="group" aria-labelledby="xwCoverLbl">${[["","All"]].concat(used.map(([k])=>[k,TAG[k]])).map(([k,n])=>
    `<button type="button" data-sec="${k}" aria-pressed="false">${esc(n)}</button>`).join("")}</div><p class="xw-showing" id="xwShowing" role="status" hidden></p>`;
  const chips=[...box.querySelectorAll(".xw-chips button")],showing=$("xwShowing");
  let sec="";
  function show(){
    cards.forEach(c=>{c.hidden=!rowShown((c.dataset.secs||"").split(" "),sec)});
    groups.forEach(g=>{g.hidden=!g.querySelector(".card:not([hidden])");const n=g.querySelector(".xw-group-note");if(n)n.hidden=!!sec});
    chips.forEach(c=>c.setAttribute("aria-pressed",String(c.dataset.sec===sec)));
    if(sec){
      const n=cards.filter(c=>!c.hidden).length;
      showing.innerHTML=`Showing ${n} run${n===1?"":"s"} that test${n===1?"s":""} ${esc(TAG[sec])} · <button type="button" class="xw-link" id="xwClear">clear</button>`;
      showing.hidden=false;$("xwClear").onclick=()=>{const was=sec;sec="";show();const c=chips.find(x=>x.dataset.sec===was);if(c)c.focus()};
    }else showing.hidden=true;
  }
  chips.forEach(c=>c.onclick=()=>{sec=c.dataset.sec;show()});
  // a link to a section (#gChartiers) or to a run's title (#rcoal) clears a filter that hides it and scrolls to it
  function follow(){
    if($("xwStart").hidden)return; // a link followed during a run leaves the start screen's filter alone
    const el=location.hash.length>1&&document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if(!el||!el.closest(".xw-group"))return;
    if(el.closest("[hidden]")){sec="";show()}
    (el.closest(".card")||el).scrollIntoView({block:"start"}); // cards and sections keep clear of the sticky header (scroll-margin-top)
  }
  show();follow();window.addEventListener("hashchange",follow);
  const hint=$("xwHint");if(hint){const a=hint.querySelector("a");if(a)a.addEventListener("click",()=>setTimeout(follow,0))}
  box.hidden=false;
}
function showStart(){
  $("xwStart").hidden=false;$("xwGame").hidden=true;$("xw").classList.add("on-start");
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

/* ---------- title screen: the coke works at dusk, in pixel art ---------- */
function title(){
  const cv=$("xwTitleCv");if(!cv)return;
  let g=cv.getContext("2d");const W=cv.width,H=cv.height;
  const C={sky:["#1b1830","#2c2142","#4a2a48","#7a3a3f","#b5573a","#e08a3c"],river:"#22263a",riverHi:"#e08a3c",riverHi2:"#8a4a3a",
    plant:"#141319",plant2:"#1f1d26",glow:"#ffb347",glow2:"#ff7a2a",ink:"#0e0d12",rail:"#3a3640",ground:"#262229",
    green:"#2f6b3f",green2:"#3f8a52",cream:"#efe6cf",smoke:"150,130,130",hopper:"#4a3b33",ore:"#7a3b2a"};
  const FONT={A:"01110100011000111111100011000110001",B:"11110100011000111110100011000111110",C:"01111100001000010000100001000001111",
    D:"11110100011000110001100011000111110",E:"11111100001000011110100001000011111",F:"11111100001000011110100001000010000",
    G:"01111100001000010111100011000101111",H:"10001100011000111111100011000110001",I:"11111001000010000100001000010011111",
    K:"10001100101010011000101001001010001",L:"10000100001000010000100001000011111",N:"10001110011010110011100011000110001",
    O:"01110100011000110001100011000101110",P:"11110100011000111110100001000010000",R:"11110100011000111110101001001010001",
    S:"01111100001000001110000010000111110",T:"11111001000010000100001000010000100",U:"10001100011000110001100011000101110",
    V:"10001100011000110001100010101000100",W:"10001100011000110101101011010101010",X:"10001100010101000100010101000110001",
    Y:"10001100010101000100001000010000100","&":"01100100101010001000101011001001100",
    "0":"01110100011001110101110011000101110","1":"00100011000010000100001000010001110","2":"01110100010000100010001000100011111",
    "4":"00010001100101010010111110001000010","5":"11111100001111000001000011000101110","7":"11111000010001000100010000100001000",
    "8":"01110100011000101110100011000101110","9":"01110100011000101111000010001001100","-":"00000000000000011111000000000000000",
    "·":"00000000000000000100000000000000000"," ":"00000000000000000000000000000000000"};
  function text(str,x,y,sc,col,shadow){
    const w=str.length*6*sc-sc;if(x==="c")x=Math.round((W-w)/2);
    for(const pass of shadow?[[shadow,1],[col,0]]:[[col,0]]){
      g.fillStyle=pass[0];[...str].forEach((ch,i)=>{const f=FONT[ch]||FONT[" "];for(let r=0;r<7;r++)for(let c=0;c<5;c++)if(f[r*5+c]==="1")g.fillRect(x+pass[1]+(i*6+c)*sc,y+pass[1]+r*sc,sc,sc)});
    }
  }
  const bg=document.createElement("canvas");bg.width=W;bg.height=H;const b=bg.getContext("2d");
  // dusk sky in dithered bands, darkest at the top
  const bands=[0,20,34,46,56,64];
  C.sky.forEach((c,i)=>{b.fillStyle=c;b.fillRect(0,bands[i],W,(bands[i+1]||72)-bands[i])});
  bands.slice(1).forEach((y,i)=>{b.fillStyle=C.sky[i];for(let x=0;x<W;x+=2)b.fillRect(x+((x/2)%2),y,1,1)});
  b.fillStyle="#f4d9a0";for(let i=0;i<14;i++)b.fillRect((i*53+17)%W,(i*29+3)%18,1,1); // first stars
  // the far shore: Pittsburgh hills, upstream on the right
  b.fillStyle="#3a2738";for(let x=0;x<W;x++){const h=Math.round(6+4*Math.sin(x*.05)+3*Math.sin(x*.13+1));b.fillRect(x,66-h,1,h+6)}
  // the plant: coke battery with its ovens, the quench tower, B furnace and its stoves, stacks
  const P=(c,x,y,w,h)=>{b.fillStyle=c;b.fillRect(x,y,w,h)};
  P(C.plant,8,58,90,14);P(C.plant2,10,54,86,4); // coke battery
  for(let x=12;x<94;x+=4){P(C.glow2,x,61,2,3)} // oven doors glowing
  P(C.plant,22,30,3,24);P(C.plant,40,26,3,28);P(C.plant,58,32,3,22); // battery stacks
  P(C.plant,100,40,12,32);P(C.plant2,102,36,8,4); // quench tower
  P(C.plant,150,22,10,50);P(C.plant,147,34,16,4);P(C.plant,152,14,6,8); // B furnace
  for(const x of [166,176,186])P(C.plant,x,36,8,36); // hot-blast stoves
  P(C.plant,200,44,30,28);P(C.plant2,205,40,6,4); // cast house
  P(C.plant,236,28,4,44);P(C.plant,244,34,3,38); // far stacks
  P(C.glow,150,60,10,3); // the cast, lit from inside
  // the river and its reflections
  P(C.river,0,72,W,12);
  for(let x=0;x<W;x+=3){const y=74+(x*7%9);b.fillStyle=(x>140&&x<170)||(x>8&&x<98&&x%6===0)?C.riverHi:C.riverHi2;b.fillRect(x,y,2,1)}
  // ground and the track along the bank
  P(C.ground,0,84,W,H-84);P(C.rail,0,101,W,1);
  b.fillStyle="#3c3640";for(let x=0;x<W;x+=4)b.fillRect(x,103,2,1);
  // a pole line
  b.fillStyle="#3a3438";for(let x=14;x<W;x+=56){b.fillRect(x,84,1,17);b.fillRect(x-3,85,7,1)}
  // the lettering sits on its own layer, drawn over the smoke
  const fg=document.createElement("canvas");fg.width=W;fg.height=H;
  {const keep=g;g=fg.getContext("2d");
    text("PITTSBURGH & CHARTIERS VALLEY","c",4,1,"#f4d9a0","#1b1830");
    text("EXTRA EAST","c",14,3,C.cream,"#7a2a24");
    text("HART RAILROAD","c",39,1,C.glow,"#1b1830");
    g=keep}
  // smoke and steam, drawn each frame
  function smoke(t){
    const puffs=[[23,30],[41,26],[59,32],[106,36],[155,14],[237,28]];
    puffs.forEach(([x,y],k)=>{for(let i=0;i<5;i++){const p=((t/180)+i*2.2+k*1.3)%11;const a=(1-p/11)*.55;
      g.fillStyle=k===3?`rgba(230,225,230,${a})`:`rgba(${C.smoke},${a})`;g.fillRect(Math.round(x-p*2.6),Math.round(y-2-p*1.6),2+(p>>2),2+(p>>2))}});
  }
  // the ore drag: SW9 #4 shoving ten hoppers is too long for the frame, so four hoppers and the engine
  function train(x,f){
    const Rr=(c,a,y,w,h)=>{g.fillStyle=c;g.fillRect(Math.round(x+a),y,w,h)};
    // SW9 on the west end, long hood leading west, cab coupled to the drag: it shoves east (right)
    Rr(C.green,0,90,24,10);Rr(C.green2,0,90,24,1);Rr(C.green,24,86,8,14);Rr(C.cream,26,88,4,3);Rr(C.ink,24,85,8,1);
    Rr(C.glow,-2,92,2,2); // headlight on the long hood end
    Rr(C.ink,3,100,4,2);Rr(C.ink,21,100,4,2);
    Rr(C.cream,8,93,1,3);Rr(C.cream,10,93,3,1);Rr(C.cream,10,95,3,1); // a 4 on the hood
    for(let k=0;k<4;k++){const o=34+k*18;Rr(C.hopper,o,92,16,8);Rr(C.ore,o+1,90,14,2);Rr(C.ink,o+2,100,3,2);Rr(C.ink,o+11,100,3,2)}
    for(let i=0;i<3;i++){const p=(f+i*3)%9;g.fillStyle=`rgba(60,55,60,${(1-p/9)*.6})`;g.fillRect(Math.round(x+12-p*1.5),88-p*2,2,2)}
  }
  function draw(t){
    g.drawImage(bg,0,0);smoke(t);g.drawImage(fg,0,0);
    const span=W+120,x=still?96:((t/45)%span)-110;
    train(x,Math.floor(t/140));
    // the cast flickers
    g.fillStyle=`rgba(255,179,71,${.35+.25*Math.sin(t/220)})`;g.fillRect(146,58,18,6);
  }
  const still=reduced;
  if(still){draw(0);return}
  let raf=0;const loop=t=>{draw(t);raf=requestAnimationFrame(loop)};
  const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting&&!raf)raf=requestAnimationFrame(loop);else if(!e.isIntersecting&&raf){cancelAnimationFrame(raf);raf=0}})});
  io.observe(cv);draw(0);
}

RUNS=window.NevilleRuns||{};
renderCover();
{const st=$("xwStatus");if(st)st.onclick=exitClick}
title();
document.querySelectorAll("[data-run]").forEach(b=>b.onclick=()=>begin(b.dataset.run,b.hasAttribute("data-daily")));
showStart();
})();
