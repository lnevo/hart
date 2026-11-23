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
    // the first control still on screen: the section chip's clear link, the first-shift link, or the first Start button
    const f=document.querySelector&&["#xwClear","#xwNewJob","#xwRandom","[data-run]"].flatMap(q=>[...document.querySelectorAll(q)]).find(e=>e.offsetParent!==null);if(f&&f.focus)f.focus();return}
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
  if(D.verdicts)verdict=D.verdicts[verdict]||verdict; // a run may name its own verdicts (the new conductor's first shift)
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
  $("xwStart").hidden=true;$("xwGame").hidden=false;$("xw").classList.remove("on-start");if($("xwCover"))$("xwCover").hidden=true;
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
  // the section filter sits under the title like the site's "On this page" row (nav.jump)
  box.innerHTML=`<p class="jump-label" id="xwCoverLbl">Practice a section</p><ul class="xw-chips" aria-labelledby="xwCoverLbl">${[["","All"]].concat(used.map(([k])=>[k,TAG[k]])).map(([k,n])=>
    `<li><button type="button" data-sec="${k}" aria-pressed="false">${esc(n)}</button></li>`).join("")}</ul><p class="xw-showing" id="xwShowing" role="status" hidden></p>`;
  const chips=[...box.querySelectorAll("button[data-sec]")],showing=$("xwShowing");
  // Take a call off the extra board: a random run among the cards showing, so it follows the section filter
  const rnd=$("xwRandom");if(rnd)rnd.hidden=false;if(rnd)rnd.onclick=()=>{const ids=cards.filter(c=>!c.hidden).map(c=>c.querySelector("[data-run]").dataset.run).filter(id=>RUNS[id]);if(ids.length)begin(ids[Math.floor(Math.random()*ids.length)])};
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
  const nj=$("xwNewJob");if(nj&&RUNS.j105)nj.onclick=e=>{e.preventDefault();begin("j105")}; // the new conductor's first shift; without the script the link goes to its card
  box.hidden=false;
}
function showStart(){
  $("xwStart").hidden=false;$("xwGame").hidden=true;$("xw").classList.add("on-start");if($("xwCover")&&$("xwCover").innerHTML)$("xwCover").hidden=false;
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
{const st=$("xwStatus");if(st)st.onclick=exitClick}
document.querySelectorAll("[data-run]").forEach(b=>b.onclick=()=>begin(b.dataset.run,b.hasAttribute("data-daily")));
showStart();
})();
