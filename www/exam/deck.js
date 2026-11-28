(function(){
const store={get(k,d){try{const v=localStorage.getItem(k);return v?JSON.parse(v):d}catch(e){return d}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};
const esc=HARTOps.esc;
const hash=s=>{let h=5381;for(const ch of s)h=((h<<5)+h+ch.charCodeAt(0))|0;return (h>>>0).toString(36)};
CARDS.forEach(c=>c.id=hash(c.f));QS.forEach(q=>q.id=hash(q.q));
const shuffle=a=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
const srcLabel=s=>s.replace(/^(SC|GC|TT|YL|TW|SG|SM)\b/,m=>SRC[m]||m);
const keys=Object.keys(SECTIONS);

/* tabs */
const views={learn:"view-learn",cards:"view-cards",quiz:"view-quiz",notes:"view-notes"};
let view="learn";
function show(v){if(!views[v])v="learn";view=v;document.querySelectorAll(".tabs [role=tab]").forEach(b=>b.setAttribute("aria-selected",b.dataset.view===v));
  for(const k in views)document.getElementById(views[k]).hidden=k!==v}
document.querySelectorAll(".tabs [role=tab]").forEach(b=>b.onclick=()=>{show(b.dataset.view);if(location.hash)history.replaceState(null,"","#"+(view==="learn"&&frame>=0?frames[frame].id:view))});
HARTA11y.tabs(document.querySelector(".tabs[role=tablist]")); // arrows, Home and End select a tab; only the selected one takes Tab

/* chips */
function chips(el,counts,sel,onChange){
  el.innerHTML="";
  const all=document.createElement("button");all.className="ce-chip";all.textContent="All";
  all.setAttribute("aria-pressed",sel.size===keys.length);all.onclick=()=>{if(sel.size===keys.length)sel.clear();else keys.forEach(k=>sel.add(k));onChange()};
  el.appendChild(all);
  keys.forEach(k=>{const b=document.createElement("button");b.className="ce-chip";b.setAttribute("aria-pressed",sel.has(k));
    b.innerHTML=esc(SECTIONS[k])+' <span class="n">'+(counts[k]||0)+'</span>';
    b.onclick=()=>{sel.has(k)?sel.delete(k):sel.add(k);onChange()};el.appendChild(b)});
}
const count=arr=>arr.reduce((m,x)=>(m[x.s]=(m[x.s]||0)+1,m),{});

/* ---------- flashcards ---------- */
let boxes=store.get("ce_boxes",{});
const validSel=v=>Array.isArray(v)?v.filter(k=>SECTIONS[k]):keys;
const cardSel=new Set(validSel(store.get("ce_cardSel",keys)));
let queue=[],cur=null,flipped=false,roundSeen=0;
function renderCardChips(){chips(document.getElementById("cardChips"),count(CARDS),cardSel,()=>{store.set("ce_cardSel",[...cardSel]);deal()})}
function deal(){
  renderCardChips();
  const pool=CARDS.filter(c=>cardSel.has(c.s));
  const byBox={};pool.forEach(c=>{const b=boxes[c.id]||0;(byBox[b]=byBox[b]||[]).push(c)});
  queue=[];Object.keys(byBox).sort((a,b)=>a-b).forEach(b=>queue.push(...shuffle(byBox[b])));
  roundSeen=0;next();
}
function next(){cur=queue.shift()||null;flipped=false;renderCard()}
function renderCard(){
  const pool=CARDS.filter(c=>cardSel.has(c.s));
  const learned=pool.filter(c=>(boxes[c.id]||0)>=3).length, learning=pool.filter(c=>{const b=boxes[c.id]||0;return b>0&&b<3}).length;
  const pct=n=>pool.length?(100*n/pool.length).toFixed(1):0;
  document.getElementById("cardMeter").innerHTML=`<span>${learned} learned · ${learning} learning · ${pool.length-learned-learning} new</span><span class="bar"><i class="m" style="width:${pct(learned)}%"></i><i class="l" style="width:${pct(learning)}%"></i></span><span>${queue.length+(cur?1:0)} left this round</span>`;
  const el=document.getElementById("card");
  const btns=[document.getElementById("bAgain"),document.getElementById("bGot")];
  if(!cur){
    el.innerHTML=pool.length?`<div class="top"><span class="sec">Round complete</span><span>${roundSeen} cards</span></div><div class="front">Round done. ${learned} of ${pool.length} learned.</div><p class="hint">Start a new round; cards you missed or haven't learned come first.</p><div class="row" style="background:var(--paper)"><button class="ce-btn primary" id="bRound">Start next round</button></div>`
      :`<div class="top"><span class="sec">No sections</span></div><div class="front">Pick at least one section above.</div>`;
    const r=document.getElementById("bRound");if(r)r.onclick=deal;
    btns.forEach(b=>b.disabled=true);return;
  }
  const box=boxes[cur.id]||0;
  btns.forEach(b=>b.disabled=!flipped);
  el.innerHTML=`<div class="top"><span class="sec">${esc(SECTIONS[cur.s])}</span><span>Box ${box} of 3</span></div>
   <div class="flipzone" id="flip" role="button" tabindex="0" aria-label="Flip card">
    <div class="front">${esc(cur.f)}</div>${figHtml(cur.fig)}
    ${flipped?`<div class="back">${esc(cur.b)}</div>${cur.note?`<div class="note">${esc(cur.note)}</div>`:""}<div class="src">${esc(srcLabel(cur.src))}</div>`:`<div class="hint">Say the answer out loud, then flip (Space).</div>`}
   </div>`;
  const f=document.getElementById("flip");f.onclick=flip;
}
function flip(){if(!cur)return;flipped=!flipped;renderCard()}
function grade(ok){
  if(!cur||!flipped)return;
  if(ok){boxes[cur.id]=Math.min(3,(boxes[cur.id]||0)+1)}
  else{boxes[cur.id]=0;queue.splice(Math.min(3,queue.length),0,cur)}
  store.set("ce_boxes",boxes);roundSeen++;next();
}
document.getElementById("bAgain").onclick=()=>grade(false);
document.getElementById("bGot").onclick=()=>grade(true);
document.getElementById("bShuffle").onclick=deal;
let resetArm=false;const bReset=document.getElementById("bReset");
bReset.onclick=()=>{if(!resetArm){resetArm=true;bReset.textContent="Click again to reset";setTimeout(()=>{resetArm=false;bReset.textContent="Reset progress"},3000);return}
  boxes={};store.set("ce_boxes",boxes);resetArm=false;bReset.textContent="Reset progress";deal()};

/* ---------- quiz ---------- */
const quizSel=new Set(validSel(store.get("ce_quizSel",keys)));
let qlen=store.get("ce_qlen",20);
const LENS=[10,20,40,"All"];
let test=null;
function renderSetup(){
  chips(document.getElementById("quizChips"),count(QS),quizSel,()=>{store.set("ce_quizSel",[...quizSel]);renderSetup()});
  const lc=document.getElementById("lenChips");lc.innerHTML="";
  LENS.forEach(n=>{const b=document.createElement("button");b.className="ce-chip";b.textContent=n==="All"?"All":n+" questions";b.setAttribute("aria-pressed",qlen===n);b.onclick=()=>{qlen=n;store.set("ce_qlen",n);renderSetup()};lc.appendChild(b)});
  const pool=QS.filter(q=>quizSel.has(q.s));
  document.getElementById("bStart").disabled=!pool.length;
  const h=store.get("ce_hist",[]);
  document.getElementById("history").textContent=h.length?"Recent: "+h.slice(-5).map(x=>x.p+"%").join(" · "):pool.length+" questions in the selected sections";
}
function startTest(list,record){
  const pool=list||QS.filter(q=>quizSel.has(q.s));
  const n=qlen==="All"||list?pool.length:Math.min(qlen,pool.length);
  test={retake:!!list&&!record,items:shuffle(pool).slice(0,n).map(q=>({q,order:shuffle([0,1,2,3]),pick:null})),i:0};
  document.getElementById("quizSetup").hidden=true;document.getElementById("quizDone").hidden=true;document.getElementById("quizRun").hidden=false;
  renderQ();
}
function renderQ(){
  const it=test.items[test.i],q=it.q;
  const right=test.items.filter(x=>x.pick===0).length,answered=test.items.filter(x=>x.pick!==null).length;
  document.getElementById("quizMeter").innerHTML=`<span>Question ${test.i+1} of ${test.items.length}</span><span class="bar"><i class="m" style="width:${100*answered/test.items.length}%"></i></span><span>${right}/${answered} right</span>`;
  const el=document.getElementById("qcard");
  const L="ABCD";
  el.innerHTML=`<div class="top"><span class="sec">${esc(SECTIONS[q.s])}</span><span>${esc(srcLabel(q.src))}</span></div>
   <div class="front">${esc(q.q)}</div>${figHtml(q.fig)}
   <div class="opts">${it.order.map((o,k)=>{let cls="";if(it.pick!==null){if(o===0)cls="right";else if(o===it.pick)cls="wrong"}
     return `<button class="opt ${cls}" data-o="${o}" ${it.pick!==null?"disabled":""}><span class="k">${L[k]}</span><span>${esc(q.opts[o])}</span></button>`}).join("")}</div>
   ${it.pick!==null?`<div class="why">${it.pick===0?'<b class="ok">Correct.</b>':'<b class="no">Not quite.</b> The answer is: '+esc(q.opts[0])+'.'} ${esc(q.why)}</div>`:""}`;
  el.querySelectorAll(".opt").forEach(b=>b.onclick=()=>answer(+b.dataset.o));
  document.getElementById("bNext").disabled=it.pick===null;
  document.getElementById("bNext").firstChild.textContent=test.i===test.items.length-1?"Finish":"Next";
}
function answer(o){const it=test.items[test.i];if(it.pick!==null)return;it.pick=o;renderQ()}
function nextQ(){if(!test)return;const it=test.items[test.i];if(it.pick===null)return;if(test.i<test.items.length-1){test.i++;renderQ()}else finish()}
function finish(){
  const done=test.items.filter(x=>x.pick!==null);
  const right=done.filter(x=>x.pick===0).length;
  const p=done.length?Math.round(100*right/done.length):0;
  if(done.length&&!test.retake){const h=store.get("ce_hist",[]);h.push({p,n:done.length,d:new Date().toISOString().slice(0,10)});store.set("ce_hist",h.slice(-30))}
  const per={};done.forEach(x=>{const s=x.q.s;per[s]=per[s]||[0,0];per[s][1]++;if(x.pick===0)per[s][0]++});
  const missed=done.filter(x=>x.pick!==0);
  const el=document.getElementById("quizDone");
  el.innerHTML=`<div class="flimsy"><div class="top"><span class="sec">Test result</span><span>${right} of ${done.length} right</span></div>
    <div class="score" style="background:var(--paper)">${p}%</div>
    <div class="ce-panel" style="background:var(--paper);gap:8px">${Object.keys(per).map(s=>{const [r,n]=per[s];return `<div class="secrow"><span>${esc(SECTIONS[s])}</span><span style="text-align:right;font-family:var(--f-mono);font-size:12px">${r}/${n}</span><span class="bar"><i class="m" style="width:${100*r/n}%"></i></span></div>`}).join("")}</div>
    <div class="row" style="background:var(--paper)">${missed.length?'<button class="ce-btn primary" id="bRetry">Retake the '+missed.length+' missed</button>':''}<button class="ce-btn" id="bAgainT">New test</button></div></div>
    ${missed.length?`<div class="missed"><span class="label">Missed questions</span>${missed.map(x=>`<details><summary>${esc(x.q.q)}</summary>${figHtml(x.q.fig)}<p><b>Answer:</b> ${esc(x.q.opts[0])}</p><p>You picked: ${esc(x.q.opts[x.pick])}</p><p>${esc(x.q.why)} <span class="src">${esc(srcLabel(x.q.src))}</span></p></details>`).join("")}</div>`:""}`;
  document.getElementById("quizRun").hidden=true;el.hidden=false;
  const r=document.getElementById("bRetry");if(r)r.onclick=()=>startTest(missed.map(x=>x.q));
  document.getElementById("bAgainT").onclick=()=>{test=null;el.hidden=true;document.getElementById("quizSetup").hidden=false;renderSetup()};
}
document.getElementById("bStart").onclick=()=>startTest();
document.getElementById("bNext").onclick=nextQ;
document.getElementById("bQuit").onclick=()=>{if(test)finish()};

/* keyboard */
document.addEventListener("keydown",e=>{
  if(e.target.closest("input,textarea,[role=tablist]")||e.metaKey||e.ctrlKey||e.altKey)return;
  if(view==="cards"){
    const own=e.target.closest("a,summary,select,[contenteditable]");
    if(e.key===" "&&!own){e.preventDefault();flip()}
    else if(e.key==="Enter"&&(e.target===document.body||e.target.id==="flip")){e.preventDefault();flip()}
    else if(e.key==="1")grade(false);else if(e.key==="2")grade(true);
  }else if(view==="quiz"&&test&&!document.getElementById("quizRun").hidden){
    const k=e.key.toUpperCase();const idx="ABCD".indexOf(k)>=0?"ABCD".indexOf(k):["1","2","3","4"].indexOf(e.key);
    if(idx>=0){const it=test.items[test.i];answer(it.order[idx])}
    else if(e.key==="Enter"&&!e.target.closest("button,a,summary")){e.preventDefault();nextQ()}
  }
});

/* study guide: practice buttons per section. They focus one section for this run only and leave the saved choices alone. */
const LAST_SEC=([...document.querySelectorAll("#view-learn article[data-sec]")].pop()||{dataset:{}}).dataset.sec; // the section whose row carries the game link
document.querySelectorAll("#view-learn article[data-sec]").forEach(a=>{
  const k=a.dataset.sec,go=a.querySelector(".learn-go");if(!go)return;
  go.innerHTML=`<span class="label">Practice ${esc(SECTIONS[k])}</span><button class="ce-btn" data-go="cards">Flashcards</button><button class="ce-btn" data-go="quiz">10-question test</button>`+(k===LAST_SEC?`<a class="ce-xw" href="run.html">Put these rules to use in Extra East</a>`:"");
  go.querySelector('[data-go="cards"]').onclick=()=>{cardSel.clear();cardSel.add(k);deal();show("cards");document.getElementById("view-cards").scrollIntoView()};
  go.querySelector('[data-go="quiz"]').onclick=()=>{
    if(test&&!document.getElementById("quizRun").hidden&&test.items.some(x=>x.pick!==null))finish(); // keep a running test's answers
    show("quiz");startTest(shuffle(QS.filter(q=>q.s===k)).slice(0,10),true);document.getElementById("view-quiz").scrollIntoView()};
});
/* study guide frames: one section shows at a time; the line of stops, Prev/Next, arrow keys and swipes move between them */
const frames=[...document.querySelectorAll("#view-learn .learn article")];
const line=document.getElementById("learnLine"),cap=document.getElementById("learnCap");
let frame=-1;
const fill=document.getElementById("learnFill");
line.parentNode.style.setProperty("--n",frames.length);
line.innerHTML=frames.map((a,i)=>`<li><button type="button" data-i="${i}" aria-label="${i?"Section "+i+": ":""}${esc(a.querySelector("h3").textContent.replace(/^\d+\.\s*/,""))}"><span class="dot">${i||"&#9679;"}</span><span class="name">${esc(a.dataset.short)}</span></button></li>`).join("");
line.querySelectorAll("button").forEach(b=>b.onclick=()=>goFrame(+b.dataset.i));
frames.forEach((a,i)=>{
  const nav=document.createElement("div");nav.className="learn-step";
  const p=frames[i-1],n=frames[i+1];
  nav.innerHTML=(p?`<button type="button" class="ce-btn pv"><small>&larr; Back</small>${esc(p.dataset.short)}</button>`:"")+(n?`<button type="button" class="ce-btn nx primary"><small>Next &rarr;</small>${esc(n.dataset.short)}</button>`:"");
  a.appendChild(nav);
  a.addEventListener("beforematch",()=>{show("learn");goFrame(i)}); // find-in-page reaches hidden sections
  if(p)nav.querySelector(".pv").onclick=()=>goFrame(i-1,true,true);
  if(n)nav.querySelector(".nx").onclick=()=>goFrame(i+1,true,true);
  a.querySelector("h3").tabIndex=-1;
});
function goFrame(i,toTop,focus){
  i=Math.max(0,Math.min(frames.length-1,i));
  const dir=i<frame?-1:1;
  frames.forEach((a,k)=>{if(k===i)a.removeAttribute("hidden");else a.setAttribute("hidden","until-found");a.classList.remove("in")});
  const a=frames[i];a.style.setProperty("--from",(dir*16)+"px");void a.offsetWidth;if(frame>=0&&frame!==i)a.classList.add("in");
  const first=frame<0;frame=i;
  line.querySelectorAll("button").forEach((b,k)=>{if(k===i)b.setAttribute("aria-current","step");else b.removeAttribute("aria-current");b.parentNode.classList.toggle("past",k<i)});
  fill.style.width=`calc(${i} * (100% / ${frames.length}))`;
  cap.textContent=i?`Section ${i} of ${frames.length-1}: ${a.dataset.short}`:"Overview";
  store.set("ce-learn",a.id);
  if(!first&&view==="learn"&&location.hash.slice(1)!==a.id)history.replaceState(null,"","#"+a.id);
  if(toTop){const nav=line.parentNode,hd=document.querySelector(".site-header");
    if(nav.getBoundingClientRect().top<(hd?hd.getBoundingClientRect().bottom:0))nav.scrollIntoView({behavior:matchMedia("(prefers-reduced-motion:reduce)").matches?"auto":"smooth"})}
  if(focus)a.querySelector("h3").focus({preventScroll:true});
}
document.addEventListener("keydown",e=>{
  if(view!=="learn"||e.metaKey||e.ctrlKey||e.altKey||e.shiftKey||e.target.closest("input,textarea,select,.learn-table,.ce-gloss,[role=tablist],[contenteditable]"))return;
  if(e.key==="ArrowRight"){e.preventDefault();goFrame(frame+1,true)}else if(e.key==="ArrowLeft"){e.preventDefault();goFrame(frame-1,true)}
});
let tx=null,ty=0;
const learnEl=document.querySelector("#view-learn .learn");
learnEl.addEventListener("touchstart",e=>{const x=e.touches[0].clientX;tx=e.target.closest(".learn-table,.ce-gloss")||e.touches.length>1||x<24||x>innerWidth-24?null:x;ty=e.touches[0].clientY},{passive:true});
learnEl.addEventListener("touchend",e=>{if(tx===null)return;const dx=e.changedTouches[0].clientX-tx,dy=e.changedTouches[0].clientY-ty;tx=null;
  if(Math.abs(dx)>70&&Math.abs(dx)>2*Math.abs(dy))goFrame(frame+(dx<0?1:-1),true)},{passive:true});
/* open on the study guide, or on the tab or guide section named in the link */
function fromHash(){const h=location.hash.slice(1);if(h==="glossary"){openGlossary();return}if(views[h])show(h);else if(h.startsWith("learn-")&&document.getElementById(h)){show("learn");const i=frames.findIndex(a=>a.id===h);if(i>=0)goFrame(i)}}
{const h=location.hash.slice(1),at=frames.findIndex(a=>a.id===h),last=frames.findIndex(a=>a.id===store.get("ce-learn",""));goFrame(at>=0?at:last>=0?last:0)}
window.addEventListener("hashchange",fromHash);
show("learn");renderSetup();deal();fromHash();
/* speed-signal table (Signals & whistles) and glossary (Definitions), drawn from ASPECTS and the term cards */
const GLOSS_SRC={"SC · Definitions":"Standard Code","GC · Glossary":"GCOR","YL · Definitions":"Yard Limits"};
function openGlossary(){const g=document.getElementById("glossary"),i=frames.findIndex(a=>a.id==="learn-def");
  if(!g||i<0)return;show("learn");goFrame(i);g.open=true;g.scrollIntoView({behavior:"smooth"})}
{
  const t=document.getElementById("speedTable");
  if(t)t.innerHTML=`<table><thead><tr><th>Aspect</th><th>Rule</th><th>Name</th><th>Indication</th></tr></thead><tbody>${ASPECTS.map(a=>`<tr><td>${sigFig(a.arms)}</td><td>${esc(a.r)}</td><td>${esc(a.name)}</td><td>${esc(a.ind)}</td></tr>`).join("")}</tbody></table>`;
  const list=document.getElementById("glossList"),count=document.getElementById("glossCount"),btn=document.getElementById("glossCards"),link=document.querySelector('#learn-def a[href="#glossary"]');
  if(list&&count){
    const terms=CARDS.filter(c=>c.s==="def"&&GLOSS_SRC[c.src]).map(c=>({c,t:c.f.replace(/^GCOR:\s*/,"").replace(/\s*\((?:Standard Code|Yard Limits guide)\)$/,""),from:GLOSS_SRC[c.src]}))
      .sort((a,b)=>a.t.localeCompare(b.t,"en",{sensitivity:"base"}));
    count.textContent=terms.length;
    list.innerHTML=terms.map(x=>`<dt>${esc(x.t)} <small>${x.from}</small></dt><dd>${esc(x.c.b).replace(/\n/g,"<br>")}</dd>`).join("");
  }
  if(btn)btn.onclick=()=>{cardSel.clear();cardSel.add("def");deal();show("cards");document.getElementById("view-cards").scrollIntoView()};
  if(link)link.onclick=e=>{e.preventDefault();openGlossary()};
}

})();
