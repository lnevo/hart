/* Extra East: the game's core: helpers, the railroad, the map, the 1949 run, the end screen and
   the start screen. The 1949 event pools and the modern, signals and yard runs are in run-1949.js,
   run-modern.js, run-signals.js and run-yard.js.
   Each of run.js, run-1949.js, run-modern.js, run-signals.js and run-yard.js runs inside its own function; they
   share window.ExtraEast, which run.js fills with its helpers and the run's state and each later file adds to.
   run.html loads them in that order. */
(function(){
"use strict";
const X=window.ExtraEast={}; // the names the five files share; the later files add theirs
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
const RUNS={tto:{short:"1949",train:"Extra 812 East"},twc:{short:"Modern",train:"KV 812 East"},
  yard:{short:"Yard job",train:"Ironton yard job"},
  sigs:{short:"Speed signals",train:"Extra 812 East"},sigr:{short:"Route signals",train:"KV 812 East"}};

/* ---------- the railroad ---------- */
const STATIONS=[
  {n:"Ashby",mp:100.0,sd:1,yl:1,off:1},
  {n:"Birchwood",mp:106.0,sd:1},
  {n:"Cobb",mp:111.5,sd:1,off:1},
  {n:"Dunmore",mp:117.5,sd:1,off:1},
  {n:"Elk Gap",mp:123.0,sd:1},
  {n:"Fenwick",mp:128.5,sd:0},
  {n:"Granite",mp:134.0,sd:1,off:1},
  {n:"Hollis",mp:140.0,sd:1},
  {n:"Ironton",mp:146.0,sd:1,yl:1,off:1}];
const LAST=STATIONS.length-1;
const DOUBLE_TRACK_FROM=7; // double track from Hollis (index 7) to Ironton

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
  state:()=>state,render:()=>{renderStatus();renderSheet()},hereName:()=>hereName(),addTime:m=>addTime(m),
  costMinutes:c=>c.min,choiceRandom:()=>randChoices,srcHtml:o=>esc(srcLabel(o.src)),finish:(t,f)=>finish(t,f),
    lockGo:true,
  words:{endVerdict:"Run over.",endText:"The run ended here.",
    marksText:"Five marks on the record. You are pulled from service.",
    smallTag:"<small style='font-size:14px;font-family:var(--mono)'>"}});
const {push,front,next,log,scene,ask,info}=ENGINE;
function addTime(m){state.clock+=m}
function hereName(){if(state.era==="yard")return X.YLOC[state.yloc].n;
  return state.moving?state.moving:STATIONS[state.pos].n}

/* ---------- map ---------- */
let MW=600; // map width in SVG units; narrower on phones so the labels stay readable
const MX=mp=>24+(mp-100)/46*(MW-48);
let trainMp=100;
function renderMap(){
  if(state.era==="yard"){X.renderYardMap();return}
  const box=$("xwMap");MW=box.clientWidth&&box.clientWidth<560?340:600;
  const W=MW,y=52,trainX=MX(trainMp);
  let s=`<svg viewBox="0 0 ${W} 94" role="img" aria-label="Line map, Ashby to Ironton, train at ${esc(hereName())}">`;
  // yard limits
  s+=`<rect x="${MX(100)-12}" y="${y-16}" width="${W>400?32:22}" height="32" fill="#e8dfc4"/><rect `+
      `x="${MX(146)-(W>400?20:10)}" y="${y-16}" width="${W>400?32:22}" height="32" fill="#e8dfc4"/>`;
  if(W>400)s+=`<text x="${MX(100)+3}" y="${y-20}" font-size="8.5" text-anchor="middle" fill="#5d5a4e">YARD `+
      `LIMITS</text><text x="${MX(146)-3}" y="${y-20}" font-size="8.5" text-anchor="middle" `+
      `fill="#5d5a4e">YARD LIMITS</text>`;
  s+=`<line x1="${MX(100)-10}" y1="${y}" x2="${MX(146)+10}" y2="${y}" stroke="#1d2733" stroke-width="2.5"/>`;
  s+=`<path d="M${MX(140)+(W>400?30:18)} ${y} L${MX(140)+(W>400?38:24)} ${y+5} L${MX(146)+10} ${y+5}" `+
      `fill="none" stroke="#1d2733" stroke-width="2"/>`;
  STATIONS.forEach((st,i)=>{
    const x=MX(st.mp);
    const sw=W>400?26:15;
    if(st.sd)s+=`<path d="M${x-sw} ${y} L${x-sw+7} ${y-9} L${x+sw-7} ${y-9} L${x+sw} ${y}" fill="none" `+
        `stroke="#1d2733" stroke-width="1.6"/>`;
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
  if(reduced){trainMp=x1;renderMap();done();return}
  const t0=performance.now(),dur=Math.min(1800,350+Math.abs(x1-x0)*80);
  state.inSiding=false;
  let over=false;
  const end=()=>{if(over)return;over=true;trainMp=x1;done()};
  function step(t){
    if(over)return;
    const k=Math.min(1,(t-t0)/dur),e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
    trainMp=x0+(x1-x0)*e;
    const g=document.getElementById("xwTrain");if(g)g.setAttribute("transform",`translate(${MX(trainMp)} 0)`);
      else renderMap();
    if(k<1)requestAnimationFrame(step);else end();
  }
  renderMap();requestAnimationFrame(step);
  setTimeout(end,dur+400); // animation frames pause in hidden tabs; the run must not
}

/* ---------- status ---------- */
function renderStatus(){
  const at=state.era==="yard"?(/Ironton/.test(X.YLOC[state.yloc].n)?"":"Ironton, ")+X.YLOC[state.yloc].n:state.moving?("between "+state.moving):STATIONS[state.pos].n+(state.inSiding&&state.pos>0&&state.pos<LAST?" (siding)":"");
  let h=`<span><span class="lbl">Time</span><b>${fmt(state.clock)}</b></span><span><span `+
      `class="lbl">At</span>${esc(at)}</span><span><span `+
      `class="lbl">${state.era==="yard"?"Job":"Train"}</span>${RUNS[state.era].train}</span><span `+
      `class="marks"><span class="lbl">Marks</span><b>${state.marks}</b>/${MAX_MARKS}</span>`;
  if(state.era==="tto")h+=`<span><span class="lbl">Caboose</span>${state.fus} fusees · ${state.torp} torpedoes</span>`;
  $("xwStatus").innerHTML=h;
  renderMap();
}

/* ---------- 1949: time-table and train orders ---------- */
/* Regular trains. dir W runs Ironton→Ashby (index falling), E runs Ashby→Ironton.
   t[i] is the scheduled time at station i (one time = leaving time, Rule 5). act[i] is when the train actually passes. */
function makeTT(){
  const run=(mp0,mp1,f)=>Math.abs(mp1-mp0)*f;
  function sched(dir,startT,f){
    const t=new Array(STATIONS.length);
    if(dir==="W"){t[LAST]=startT;
      for(let i=LAST-1;i>=0;i--)t[i]=Math.round(t[i+1]+run(STATIONS[i+1].mp,STATIONS[i].mp,f))}
    else{t[0]=startT;for(let i=1;i<=LAST;i++)t[i]=Math.round(t[i-1]+run(STATIONS[i-1].mp,STATIONS[i].mp,f))}
    return t;
  }
  const no1={id:"1",name:"No 1",dir:"W",cls:"First class",t:sched("W",370+rnd(-4,8),2.6)};
  const no2={id:"2",name:"No 2",dir:"E",cls:"First class",t:sched("E",420+rnd(-6,6),2.6)};
  const no21={id:"21",name:"No 21",dir:"W",cls:"Second class",t:sched("W",470+rnd(-8,8),3.4)};
  [no1,no2,no21].forEach(tr=>{tr.act=tr.t.slice();tr.late=0});
  const trains=[no1,no21,no2];
  // No 2 runs in two sections on about half the runs: Second 2 is on the same schedule, about 10 minutes behind.
  if(randSetup()<.5){
    no2.signals=true;
    trains.push({id:"2nd2",name:"Second 2",dir:"E",cls:"First class",hidden:true,t:no2.t.slice(),
      act:no2.t.map(x=>x+10+rnd(0,4)),late:0});
  }
  // the extra's running times between stations
  const leg=[];for(let i=0;i<LAST;i++)leg[i]=Math.round(run(STATIONS[i].mp,STATIONS[i+1].mp,3.3))+rnd(-1,2);
  return {trains,leg};
}
const runTime=(k,j)=>{let m=0;for(let i=k;i<j;i++)m+=state.tt.leg[i];return m};
/* Check a move from k (leaving now, c) to j, arriving a. Returns the worst problem. */
function checkMove(k,j,c,a){
  const probs=[];
  for(const tr of state.tt.trains){
    if(tr.meetOnly){
      if(j<=tr.meetAt)continue; // it waits at the meeting point for us
      if(k<tr.meetAt){ // running through the meeting point: it must already be there
        if(tr.act[tr.meetAt]>c+runTime(k,tr.meetAt))probs.push({kind:"meet",tr});
        continue;
      }
    }
    if(tr.dir==="W"){
      if(tr.act[k]<=c)continue; // already past us
      if(k>=DOUBLE_TRACK_FROM)continue; // double track: opposing trains use the other main (Rule D-71)
      const jj=Math.min(j,DOUBLE_TRACK_FROM),aa=c+runTime(k,jj); // only the single-track part can meet them
      // head-on if it reaches jj before we do, and we leave k before it gets there
      if(c<tr.act[k]&&tr.act[jj]<aa)probs.push({kind:"headon",tr});
      else if(aa>tr.act[jj]-5&&!tr.meetOnly)probs.push({kind:"margin",tr,by:Math.round(tr.act[jj]-aa)});
    }else{
      if(tr.act[k]<=c)continue; // already ahead of us
      // Rule 86: clear at j by the time it is due to leave k, the station in its rear
      if(a>tr.act[k]){
        if(tr.act[j]<=a)probs.push({kind:"rear",tr});
        else probs.push({kind:"r86",tr,by:Math.round(a-tr.act[k])});
      }
    }
  }
  const rank={headon:3,rear:3,meet:3,margin:1,r86:1};
  probs.sort((x,y)=>rank[y.kind]-rank[x.kind]);
  return probs;
}
/* the best legal finish, for par */
function solvePar(){
  let best=Infinity;
  const seen=new Set(),office=state.officeOrders;
  function go(k,c,stopped){
    if(k===LAST){best=Math.min(best,c);return}
    const key=k+":"+c+":"+stopped;if(seen.has(key)||c>=best)return;seen.add(key);
    let n=0;
    for(let j=k+1;j<=LAST&&n<3;j++){ // the same three choices stationTTO offers
      if(!STATIONS[j].sd)continue;n++;
      const to=(!stopped&&office>k&&office<j)?office:j; // the board at the order office stops the train
      const a=c+runTime(k,to);
      if(!checkMove(k,to,c,a).length)go(to,a+(!stopped&&to===office?(state.clearFix||0):0),stopped||to===office);
        // the clearance fix happens at the office
    }
    const waits=state.tt.trains.map(tr=>tr.act[k]).filter(t=>t!==undefined&&t>c).sort((x,y)=>x-y);
    if(waits.length)go(k,waits[0],stopped||k===office);
    else if(c<state.start+720)go(k,c+10,stopped||k===office);
  }
  go(0,state.start+(state.hotDelay?3:0),false); // a hot box needs at least the 3-minute sign-out
  return best;
}

function startTTO(){
  state.tt=makeTT();
  state.par=0;
  state.officeOrders=pick([2,3]); // Cobb or Dunmore holds orders for us
  state.hotLeg=randSetup()<.75?rnd(1,5):-1;
  push(
    info("Ashby","Called for 6:00",
      "<p>You are the conductor of Extra 812 East, a freight extra from Ashby to Ironton. The time-table "+
        "on the right shows the regular trains on this subdivision. Westward trains are superior to eastward "+
        "trains of the same class, and your extra is inferior to every regular train (Rule 73).</p><p>Your "+
        "engineer has the train air tested. The caboose locker is short of flag equipment.</p>","Go to the caboose"),
    storeScene,
    ask({sec:"sup",src:"SC · Rule S-83",title:"Before leaving Ashby",
      body:"Ashby is your initial station and a register station. What must you find out before Extra 812 East leaves?",
      right:"Whether all superior trains that are due have arrived or left",
      wrong:[["That the block ahead shows clear"],["Whether all extras on the division have reported clear"],
      ["The dispatcher's OK on a track warrant"]],
      why:"Rule S-83: a train must not leave its initial station until it has been ascertained whether all "+
        "superior trains due have arrived or left. Register stations are designated by time-table, and the "+
        "train register there records the arrival and departure of trains."}),
    ask({sec:"sup",src:"SC · Rule 73",title:"Reading the time-table",
      body:"No 21 is a second-class freight. Your train is an extra. Which is superior?",
      right:"No 21: extra trains are inferior to regular trains",
      wrong:[["Your extra, since it has no schedule to keep"],["Neither; the first to reach a siding decides"],
      ["Your extra, being eastward"]],
      why:"Rule 73: extra trains are inferior to regular trains. Rule 72: first class is superior to second, "+
        "second to third."}),
    ask({sec:"sup",src:"SC · Rule 84",title:"Ready to go",
      body:"The register shows no superior train due. The engineer has steam up. When may he start the train?",
      right:"When a proper signal is given",
      wrong:[["As soon as the brake test is done"],["At once, since extras have no schedule"],
      ["After whistling — — o —"]],
      why:"Rule 84: a train must not start until a proper signal is given."}),
    ()=>{log("Extra 812 East ready at Ashby");stationTTO()}
  );
  next();
}
function storeScene(){
  let f=1,t=0;
  const el=scene("Ashby","The caboose locker",
    "<p>The locker holds "+f+" fusee and no torpedoes. Rule 99 calls for two torpedoes, lighted fusees when necessary, and a "+
      "lighted fusee left behind when the flagman is recalled. Each trip to the storeroom costs "+
      "time.</p><div class='choices' id='stb'></div>");
  const items=[
    {t:"Sign out 4 fusees and 4 torpedoes",s:"6 min",min:6,f:4,tp:4},
    {t:"Sign out 2 fusees and 2 torpedoes",s:"3 min",min:3,f:2,tp:2},
    {t:"Leave with what is in the locker",s:"no delay",min:0,f:0,tp:0}];
  $("stb").innerHTML=items.map((x,
    i)=>`<button class="xw-btn" data-i="${i}">${esc(x.t)}<small>${x.s}</small></button>`).join("");
  $("stb").querySelectorAll("button").forEach(b=>b.onclick=()=>{$("stb").querySelectorAll("button").forEach(z=>z.disabled=true);
    const x=items[+b.dataset.i];state.fus=f+x.f;state.torp=t+x.tp;addTime(x.min);
    log(`Caboose: ${state.fus} fusees, ${state.torp} torpedoes`);next()});
}

/* station decision */
function stationTTO(){
  const k=state.pos;
  if(k===LAST){endTTO();return}
  const el=scene(STATIONS[k].n,"At "+STATIONS[k].n+(state.inSiding&&k>0?", in the siding":""),
    `<p>${k===0?"Your train stands at Ashby, ready to leave.":"Extra 812 East is in the clear at "+STATIONS[k].n+"."} `+
        `Choose how far to run, or wait in the siding for the next train to pass. Use the time-table and `+
        `your running times.</p><div class="choices" id="dc"></div>`);
  const opts=[];
  let n=0;
  for(let j=k+1;j<=LAST&&n<3;j++){
    if(!STATIONS[j].sd)continue;n++;
    const via=[];for(let m=k+1;m<j;m++)via.push(STATIONS[m].n);
    opts.push({j,t:"Run to "+STATIONS[j].n,
      s:"arrive about "+fmt(state.clock+runTime(k,j))+(via.length?" · through "+via.join(", "):"")});
  }
  $("dc").innerHTML=opts.map((o,
    i)=>`<button class="xw-btn" data-i="${i}">${esc(o.t)}<small>${esc(o.s)}</small></button>`).join("")+
    `<button class="xw-btn" id="dw">Wait in the siding for the next `+
        `train<small>${k===0?"stay at Ashby":"hold at "+esc(STATIONS[k].n)}</small></button>`;
  const lock=f=>()=>{$("dc").querySelectorAll("button").forEach(z=>z.disabled=true);f()};
  $("dc").querySelectorAll("button[data-i]").forEach(b=>b.onclick=lock(()=>departTTO(opts[+b.dataset.i].j)));
  $("dw").onclick=lock(waitTTO);
}
function waitTTO(){
  const k=state.pos;
  const due=state.tt.trains.filter(tr=>tr.act[k]>state.clock).sort((a,b)=>a.act[k]-b.act[k]);
  if(!due.length){addTime(10);log("Waited 10 minutes at "+STATIONS[k].n);
    front(info(STATIONS[k].n,"Nothing comes",
      "<p>Ten minutes pass and no train comes by. No more regular trains are due at "+esc(STATIONS[k].n)+".</p>"),
      stationTTO);
      next();return}
  const tr=due[0];
  state.clock=Math.max(state.clock,tr.act[k]);
  if(tr.hidden)tr.hidden=false;
  let txt=`${tr.name} passes ${STATIONS[k].n} at ${fmt(tr.act[k])}`;
  if(tr.signals)txt+=", with two green flags on the front of the engine";
  if(tr.meetOnly)txt=`${tr.name} arrives at ${STATIONS[k].n} at ${fmt(tr.act[k])} and stops on the main track`;
  log(txt);
  const scenes=[info(STATIONS[k].n,tr.name+(tr.meetOnly?" arrives":" goes by"),"<p>"+esc(txt)+".</p>")];
  if(tr.signals&&!state.used.has("r20")){state.used.add("r20");
    scenes.push(ask({sec:"sup",src:"SC · Rule 20",title:"Two green flags",
    body:"No 2 went by with two green flags on the front of the engine. What do they tell you?",
    right:"Another section of No 2 follows on the same schedule",
    wrong:[["No 2 is running late"],["No 2 has right over all trains"],["The track ahead is clear for two blocks"]],
    why:"Rule 20: all sections except the last display two green flags, and two green lights at night. A "+
      "section is one of two or more trains running on the same schedule, so Second 2 runs on No 2's "+
      "schedule and you keep clear of it too. The time-table now shows it.",
        after:()=>{state.tt.trains.forEach(t=>{if(t.id==="2nd2")t.hidden=false})}}))}
  front(...scenes,stationTTO);next();
}
function departTTO(j){
  const k=state.pos;
  // a train order office with orders for us: the board shows stop and the train must stop there
  const office=(state.officeOrders>k&&state.officeOrders<j&&!state.used.has("orders"))?state.officeOrders:-1;
  const stopAt=office>0?office:j;
  const scenes=[];
  let delay=0,prot=null;
  const hotOk=!checkMove(k,stopAt,state.clock,
    state.clock+runTime(k,stopAt)+15).some(p=>p.kind==="headon"||p.kind==="margin");
  if(stopAt===LAST&&!state.used.has("d71")){
    state.used.add("d71");
    scenes.push(ask({sec:"sup",src:"SC · Rule D-71",title:"Onto double track",
      body:"East of Hollis the line is double track. On two or more tracks, how is a train superior?",
      right:"By right or class only; direction no longer counts",
      wrong:[["By right, class or direction, as on single track"],["By direction only"],["By class or direction"]],
      why:"Rule D-71: on two or more tracks a train is superior by right or class only. Right is conferred by "+
        "train order, class by time-table, and right is superior to class. The S- rules are the single-track versions."}));
  }else if(state.hotLeg>=0&&state.legs>=state.hotLeg&&!state.used.has("hot")&&hotOk){
    state.used.add("hot");delay=15;state.hotDelay=15;
    scenes.push(hotBox(k,stopAt,p=>{prot=p}));
  }else{
    const ev=drawRoad();if(ev)scenes.push(ev);
  }
  state.depAt=state.clock;
  scenes.push(()=>resolveMove(k,stopAt,delay,()=>prot));
  log("Leaves "+STATIONS[k].n+(stopAt!==j?" for "+STATIONS[j].n:""));
  state.legs++;state.inSiding=false;
  state.moving=STATIONS[k].n+" and "+STATIONS[stopAt].n;
  front(...scenes);next();
}
/* Wrong answers on the road cost time after arrival; only the hot box stop changes the move itself. */
function resolveMove(k,j,delay,getProt){
  const dep=state.depAt,extra=state.clock-dep;
  const a0=dep+runTime(k,j),a1=a0+delay;
  const fault=checkMove(k,j,dep,a0);
  // only what the hot box stop adds: Rule 99 protection covers a train that cannot clear in time (Rules 86, S-87)
  const fault2=delay?checkMove(k,j,dep,a1).filter(p=>!fault.some(f=>f.tr===p.tr)):[];
  const prot=getProt();
  const sev=fault.find(p=>p.kind==="headon"||p.kind==="rear"||p.kind==="meet");
  if(sev){animateTo(j,()=>crash(sev,k,j));return}
  const sev2=fault2.find(p=>p.kind==="headon"||p.kind==="rear");
  const notes=[];
  fault.filter(p=>p.kind==="margin").forEach(p=>notes.push(marginMiss(p,j)));
  fault.filter(p=>p.kind==="r86").forEach(p=>notes.push(r86Miss(p,j)));
  if(prot!=="ok")fault2.filter(p=>p.kind==="r86").forEach(p=>notes.push(r86Miss(p,j)));
  if(sev2){
    if(prot==="ok")notes.push(info(null,"Flagged",
      `<p>${esc(sev2.tr.name)} came up while you stood on the main. Your flagman stopped it, and it `+
        `followed you in at restricted speed.</p>`));
    else{animateTo(j,()=>crash(sev2,k,j,true));return}
  }
  animateTo(j,
    ()=>{state.clock=a1+extra;state.pos=j;state.moving=null;state.inSiding=STATIONS[j].sd&&j<LAST;arriveTTO(j,notes)});
}
function marginMiss(p,j){
  return ask({miss:true,sec:"sup",src:"SC · Rule S-87",title:"Too close to "+p.tr.name,
    body:`You got into the siding at ${STATIONS[j].n} only ${Math.max(0,p.by)} minutes ahead of `+
      `${p.tr.name}'s time there. By how much must an extra clear the time of an opposing regular train?`,
        right:"Not less than 5 minutes",
        wrong:[["Any margin, as long as it is in the clear"],["Not less than 2 minutes"],["Only to the leaving time"]],
        ok:{marks:1},okText:"Right, and you did not. +1 mark.",
        why:"Rule S-87: extras must clear the time of opposing regular trains by not less than 5 minutes unless "+
      "otherwise provided. The TT&TO primer quotes 10 minutes."});
}
function r86Miss(p,j){
  const note=p.tr.id==="2nd2"?"No 2's two green flags meant Second 2 was following on the same schedule (Rule 20).":"";
  return ask({miss:true,sec:"sup",src:"SC · Rule 86",title:p.tr.name+" was close behind",
    body:`${p.tr.name} was due to leave the station behind you before you were in the clear at `+
      `${STATIONS[j].n}. When must an inferior train running ahead of a superior train be clear?`,
        right:"When the superior train is due to leave the next station in the rear where time is shown",
        wrong:[["5 minutes before the superior train is due at the station ahead"],
        ["When the superior train comes in sight"],["At the superior train's arriving time at the station ahead"]],
        ok:{marks:1},okText:"Right, and you were not. +1 mark.",
        why:"Rule 86: unless otherwise provided, the inferior train must be clear at the time the superior "+
      "train is due to leave the next station in the rear where time is shown.",note});
}
function crash(p,k,j,stopped){
  const between=`between ${STATIONS[k].n} and ${STATIONS[j].n}`;
  if(p.kind==="meet"){const w="Extra 812 East ran past Granite before Extra 530 West arrived",
    y="Form S-A, as the TT&TO primer explains it: neither train may proceed past the meeting point until "+
      "both have arrived.";state.misses.push({title:"Meet order",why:y,src:"TT · Forms",sec:"to",end:true});log("✗ "+w);
        finish(w+". "+y,true);return}
  const what=p.kind==="headon"?`${p.tr.name} met Extra 812 East head-on ${between}`:`${p.tr.name} ran into the rear of Extra 812 East ${between}`;
  let why=p.kind==="headon"
    ?`You left ${STATIONS[k].n} at a time when you could not reach ${STATIONS[j].n} ahead of `+
        `${p.tr.name}. An extra must keep out of the way of opposing regular trains and clear their time by `+
        `5 minutes (Rule S-87), or be protected under Rule 99.`
    :`${p.tr.name} is superior and was following you. You had to be clear when it was due to leave the `+
        `station behind you (Rule 86).`;
  if(p.tr.id==="2nd2")why+=" The two green flags on No 2 meant Second 2 was following on the same schedule (Rule 20).";
  if(stopped)why=`The train stopped on the main with a hot box, and it was not protected. Rule 99: the flagman goes `+
      `back with two torpedoes and lighted fusees when necessary, and the front is protected the same way `+
      `when necessary.`;
  state.misses.push({title:"Collision",why,src:p.kind==="headon"?"SC · Rule S-87":stopped?"SC · Rule 99":"SC · Rule 86",
    sec:"sup",end:true});
  log("✗ "+what);
  finish(what+". "+why,true);
}
function hotBox(k,j,setProt){
  return ()=>{
    state.moving=STATIONS[k].n+" and "+STATIONS[j].n;
    const can=state.fus>=1&&state.torp>=2; // Rule 99: two torpedoes, and a lighted fusee left when recalled
    ask({sec:"sup",src:"SC · Rule 99",miss:!can,title:"Hot box",
      body:"Smoke from a journal on the ninth car. The engineer stops Extra 812 East on the main track to cool "+
          "and repack it, about 15 minutes. Trains may come up behind you or against you. What protection do "+
          "you give the train?",
      right:"Flagman goes back with two torpedoes and, when necessary, lighted fusees; the front is protected "+
          "the same way when necessary",
      wrong:[["Leave the marker lamps lit; that is protection enough",{marks:1}],
        ["No protection; the stop is short",{marks:1}],
        ["Flagman drops a lighted fusee while the train stands",{marks:1},
        "Dropping fusees at intervals protects a moving train."]],
      ok:can?{}:{marks:1},
      okText:can?"Right. The engineman whistles — o o o (Rule 14(c)) and the flagman goes back. (Uses 1 fusee and 2 torpedoes.)":"Right, but the caboose is short of flag equipment, so the train stands unprotected. +1 mark.",
      why:"Rule 99: a stopped train that may be overtaken is protected by the flagman going back with two "+
          "torpedoes and, when necessary, lighted fusees; when called in he leaves the torpedoes and a lighted "+
          "fusee. The front is protected the same way when necessary.",note:can?"":"Sign out enough at the start.",
      after:ok=>{if(ok&&can){state.fus-=1;state.torp-=2;setProt("ok")}else setProt("none")}})();
  };
}
function arriveTTO(j,notes){
  log("Arrives "+STATIONS[j].n);
  const scenes=[];
  if(j===LAST){front(...(notes||[]),stationTTO);next();return}
  if(j===state.officeOrders&&!state.used.has("orders")){state.used.add("orders");scenes.push(...orderBoard(j))}
  if(state.meet&&j===state.meet.at&&!state.used.has("s88")){state.used.add("s88");
    scenes.push(ask({sec:"sup",src:"SC · Rule S-88",title:"Meeting Extra 530 West",
    body:"Your order says Extra 812 East meet Extra 530 West at Granite. Westward trains are superior by "+
      "direction. Which extra takes the siding?",right:"Extra 812 East, the train in the inferior time-table direction",
        wrong:[["Extra 530 West, because it is the opposing train"],["Whichever arrives first"],
        ["The one with the higher engine number"]],
        why:"Rule S-88: when two extras meet, the train in the inferior time-table direction takes the siding, "+
      "unless otherwise provided. The TT&TO primer on Form S-A: neither train goes past Granite until both "+
      "have arrived."}))}
  if(!state.used.has("r104")&&j>0){state.used.add("r104");
    scenes.push(ask({sec:"sup",src:"SC · Rule 104",title:"The siding switch",
    body:"Your head brakeman lined the switch at "+STATIONS[j].n+" and the train pulled into the siding. Who is responsible for that switch now?",
    right:"You, the conductor: it must be lined back for the main track",
    wrong:[["The section foreman"],["The engineman"],["Nobody; leave it open for the next train"]],
    why:"Rule 104: conductors are responsible for the position of switches used by them and their crews, "+
      "except where switch tenders are stationed. A switch must not be left open for another train unless "+
      "a member of that train's crew is in charge of it."}))}
  else{const ev=drawStation();if(ev)scenes.push(ev)}
  front(...(notes||[]),...scenes,stationTTO);next();
}
function orderBoard(j){
  const out=[];
  out.push(ask({sec:"to",src:"SC · Rule 221",where:STATIONS[j].n,title:"The train order board",
    body:`Coming into ${STATIONS[j].n}, the semaphore at the open office shows its blade horizontal.`,extra:semSvg(0),
    right:"Stop: an operator is on duty, and you must not leave without a Clearance Form A",
    wrong:[["Slow down and take orders on the fly"],["Proceed: it is only a block signal"],
    ["Whistle — — and keep going"]],
    why:"Rule 221: the train order signal shows stop while an operator is on duty, and trains must not "+
      "leave without a Clearance Form A. The semaphore guide adds that a horizontal blade is always stop."}));
  // build the orders: a time order on a regular train still ahead of us, and sometimes a meet with an extra
  const n1=rnd(11,19,randOrders);
  const cand=state.tt.trains.filter(tr=>tr.dir==="W"&&!tr.hidden&&tr.act[j]>state.clock+10);
  const orders=[];
  if(cand.length){
    const tr=pick(cand,randOrders),L=pick([20,25,30,35],randOrders);
    orders.push({no:n1,text:`${tr.name} run ${L} mins late Ironton to Ashby`,
      apply:()=>{tr.late+=L;tr.lateAt=tr.act.map(x=>x>state.clock);tr.act=tr.act.map(x=>x>state.clock?x+L:x)},tr,L});
  }
  const meet=(randOrders()<.6||!cand.length)&&j<6;
  const meetAfter=rnd(30,50,randOrders);
  if(meet)orders.push({no:n1+(orders.length?1:0),text:"Extra 812 East meet Extra 530 West at Granite",apply:()=>{
    const t=new Array(STATIONS.length);t[LAST]=state.start+150+meetAfter;
      for(let i=LAST-1;i>=6;i--)t[i]=Math.round(t[i+1]+(STATIONS[i+1].mp-STATIONS[i].mp)*3.3);
    const tr={id:"530",name:"Extra 530 West",dir:"W",cls:"Extra",t:t.slice(),act:t,meetOnly:true,meetAt:6,late:0};
    state.tt.trains.push(tr);state.meet={at:6,tr};
  }});
  const nums=orders.map(o=>o.no);
  const wrongClear=randOrders()<.5;
  const shown=wrongClear?nums.map((x,i)=>i===nums.length-1?x+3:x):nums;
  const clearTxt=`CLEARANCE FORM A\nTo KV Extra 812 East  at ${STATIONS[j].n.toUpperCase()}\nI have ${shown.length} `+
      `order${shown.length>1?"s":""} for your train.\nNos ${shown.join(", ")}\nOK  ${fmt(state.clock+3)}  `+
      `RK, dispatcher`;
  const ordTxt=orders.map(o=>`<span class="no">Order No ${o.no}</span>\n${esc(o.text)}`).join("\n\n");
  out.push(info(STATIONS[j].n,"Orders",
    "<p>The operator hands up the orders and the clearance.</p><div class='xw-tele'>"+ordTxt+"</div><div class='xw-clear'>"+esc(clearTxt)+"</div>",
    "Check them"));
  if(wrongClear){
    out.push(ask({sec:"to",src:"SC · Rule 211",title:"Check the clearance",
      body:`The clearance lists Nos ${shown.join(", ")}, but you hold Nos ${nums.join(", ")}. What do you do?`,
      right:"Do not leave; have the operator correct it with the dispatcher",
      wrong:[["Leave; the orders in hand are what count"],["Cross out the number and write the right one in"],
      ["Leave and report it from the next office"]],
      why:"Rule 211: Clearance Form A is filled out without erasure or alteration, and conductors, enginemen "+
        "and firemen must see that its information matches the orders received.",
          after:()=>{addTime(6);state.clearFix=6;log("Clearance corrected (+6 min)")}}));
  }else{
    out.push(ask({sec:"to",src:"SC · Rule 211",title:"Check the clearance",
      body:`The clearance lists Nos ${shown.join(", ")} and you hold Nos ${nums.join(", ")}. Who on your crew `+
        `must check that they match?`,right:"The conductor, the engineman and the fireman",
          wrong:[["Only the conductor"],["Only the engineman"],["The operator alone"]],
          why:"Rule 211: conductors, enginemen and firemen, and trainmen when practicable, must see that the "+
        "information on Clearance Form A matches the train orders received."}));
  }
  const time=orders.find(o=>o.L);
  if(time)out.push(ask({sec:"to",src:"SC · Form E",ref:"order",title:"Order No "+time.no,
    body:`“${esc(time.text)}.” What does this order do for you?`,
    right:`Run with respect to ${time.tr.name}'s schedule ${time.L} minutes later`,
    wrong:[[`Ignore ${time.tr.name} until Ironton`],[`Wait at ${STATIONS[j].n} for ${time.tr.name}`],
    [`You now have right over ${time.tr.name}`]],
    why:"Form E, a time order: any train receiving it runs with respect to the later time exactly as it "+
      "would to the regular schedule. The time-table on the right now shows the new times in red."}));
  out.push(()=>{orders.forEach(o=>{o.apply();state.orders.push(o)});log("Orders "+nums.join(", ")+" received");next()});
  return out;
}
function endTTO(){
  push(
    ask({sec:"yl",src:"SC · Rule 93",where:"Ironton yard limits",title:"Into yard limits",
      body:"You pass the yard limit sign at Ironton. A switch engine may be working on the main. At what speed "+
        "do you run?",right:"Yard speed, unless the main track is known to be clear",
          wrong:[["Maximum authorized speed; you have no more trains to clear"],["Restricted speed, not over 20 MPH"],
          ["Any speed, with the bell ringing"]],
          why:"Standard Code Rule 93: within yard limits, protection against ____ class (left blank in the Code; "+
        "the TT&TO primer fills in second class), extra trains and engines is not required; they move at "+
        "yard speed unless the main track is known to be clear. The 20 MPH figure is GCOR 6.27, not the "+
        "Standard Code."}),
    ask({sec:"yl",src:"YL",where:"Ironton",title:"Who is in charge here?",
      body:"Inside the Ironton yard limits, who is in charge of the moves if a yardmaster is on duty?",
      right:"The yardmaster",
      wrong:[["The dispatcher"],["The conductor of the first train there"],["The engineer of the longest train"]],
      why:"Yard Limits guide: the yardmaster or agent if one is on duty; otherwise generally the conductor or "+
        "switch crew foreman of the first train there."}),
    ()=>finish("Extra 812 East is in the clear at Ironton at "+fmt(state.clock)+".",false)
  );
  next();
}

/* semaphore picture, angle in degrees (0 = horizontal, upper quadrant) */
function semSvg(a){
  const r=a*Math.PI/180;
  return `<svg viewBox="0 0 120 120" width="110" height="110" aria-label="Semaphore, blade at ${a} degrees" role="img" style="align-self:flex-start"><rect x="57" y="20" width="6" height="96" fill="#1d2733"/><circle cx="60" cy="16" r="5" fill="#1d2733"/><g transform="rotate(${-a} 60 40)"><rect x="60" y="34" width="52" height="11" fill="#a3302b" stroke="#1d2733" stroke-width="1.5"/><rect x="100" y="34" width="4" height="11" fill="#fff"/></g><circle cx="52" cy="40" r="6" fill="#f3ecbf" stroke="#1d2733" stroke-width="1.5"/></svg>`;
}

function drawRoad(){return drawFrom("road",state.era==="tto"?X.ROAD_TTO:X.ROAD_TWC,.7)}
function drawStation(){return drawFrom("stn",state.era==="tto"?X.STN_TTO:[],.6)}
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
  if(state.ended)return;state.ended=true;
  const time=state.clock-state.start;
  if(state.era==="tto"&&!failed)state.par=solvePar();
  const par=state.par&&isFinite(state.par)?state.par-state.start:null;
  let verdict,cls="";
  if(failed){verdict="Pulled from service"}
  else if(state.marks===0&&(par===null||time<=par+15+(state.hotDelay||0))){verdict="Clean run";cls="good"}
  else if(state.marks<=1){verdict="Good run";cls="good"}
  else verdict="Marked up";
  const secs=[...new Set(state.misses.map(m=>m.sec))];
  const missHtml=state.misses.length?state.misses.map(m=>`<details${m.end?" open":""}><summary>${esc(m.title)}</summary><p>${esc(m.why)}</p><p `+
      `class="src">${esc(srcLabel(m.src))} · <a href="index.html#learn-${m.sec}">Study: `+
      `${esc(SEC[m.sec])}</a></p></details>`).join(""):"<p>No rules missed.</p>";
  const el=scene(failed?hereName():"Ironton",
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
function renderSheet(){
  const el=$("xwSheet");
  if(!state.tt){el.innerHTML="";return}
  if(state.era==="sigs"||state.era==="sigr"){
    const sp=state.era==="sigs";
    el.innerHTML=`<h3>Kestrel Valley · Second Subdivision</h3><div `+
        `class="sub">${sp?"Automatic block signals · Standard Code speed signals":"Route signals · CP Hollis worked by a control operator"}</div><div `+
        `class="xw-orders"><b>Signals `+
        `passed</b>${state.passed.length?state.passed.slice(-8).map(t=>`<div class="ord">${esc(t)}</div>`).join(""):"<div class=\"ord\">None yet</div>"}</div><div `+
        `class="xw-si"><b>Special `+
        `instructions</b><ul>${sp?"<li>Automatic block signals, except manual block "+STATIONS[2].n+" to "+STATIONS[3].n+", worked by the operators.</li><li>Block signals govern trains in the same direction (Rule 251).</li>":""}<li>Interlocking `+
        `at Granite, where the line crosses another railroad.</li><li>River bridge: high water detector, P `+
        `plate signal.</li><li>The grade below Granite: G plate signal.</li><li>Double track Hollis to `+
        `Ironton.</li></ul></div>`;
    return;
  }
  if(state.era==="yard"){
    el.innerHTML=`<h3>Ironton yard job</h3><div class="sub">Engine KV 1502 · yardmaster on duty</div><div `+
        `class="xw-orders"><b>Work `+
        `list</b>${state.jobs.map(j=>`<div class="ord">${j.done?"✓ ":""}${esc(j.t)}</div>`).join("")}</div><div `+
        `class="xw-si"><b>Special instructions</b><ul><li>Ironton yard limits include Main 1 and Main 2 `+
        `(GCOR 6.13).</li><li>Main 1 eastward, Main 2 westward (current of traffic).</li><li>Yard tracks and `+
        `the Kestrel Feed spur are not main track: GCOR 6.28.</li><li>East of CP Ironton East: `+
        `CTC.</li></ul></div>`;
    return;
  }
  if(state.era==="tto"){
    const tr=state.tt.trains.filter(t=>!t.hidden&&!t.meetOnly);
    const cols=[...tr.filter(t=>t.dir==="W"),...tr.filter(t=>t.dir==="E")];
    if(state.meet&&!state.meet.tr.hidden)cols.push(state.meet.tr);
    let h=`<h3>Kestrel Valley · Second Subdivision</h3><div class="sub">Time-table No 12 · single track, `+
        `double Hollis to Ironton · D = open office</div><div class="xw-tt" `+
        `tabindex="0"><table><thead><tr><th>Station</th>`;
    const short={"First class":"1st","Second class":"2nd","Extra":"extra"};
    cols.forEach(t=>h+=`<th>${esc(t.name)}<small>${t.dir==="W"?"West":"East"} · ${esc(short[t.cls]||t.cls)}</small></th>`);
    h+=`<th>X 812 E<small>run min</small></th></tr></thead><tbody>`;
    STATIONS.forEach((st,i)=>{
      h+=`<tr class="${i===state.pos&&!state.moving?"here":""}"><td class="stn">${esc(st.n)}<small>MP `+
          `${st.mp.toFixed(1)}${st.off?" · D":""}${st.sd?"":" · no siding"}</small></td>`;
      cols.forEach(t=>{
        if(t.meetOnly){h+=`<td>${i===6?"meet":""}</td>`;return}
        const known=state.orders.some(o=>o.tr===t);
        const v=known&&t.late&&t.lateAt&&t.lateAt[i]?`<span class="late"><s>${fmt(t.t[i])}</s><b>${fmt(t.t[i]+t.late)}</b></span>`:fmt(t.t[i]);
        h+=`<td>${v}</td>`;
      });
      h+=`<td class="pencil">${i<LAST?state.tt.leg[i]:""}</td></tr>`;
    });
    h+=`</tbody></table></div><div class="xw-si"><b>Special instructions</b><ul><li>Westward trains are `+
        `superior to eastward trains of the same class.</li><li>One time shown is the leaving time (Rule `+
        `5).</li><li>Ashby and Ironton are inside yard limits.</li><li>Extras clear opposing regular trains `+
        `by 5 minutes (Rule S-87).</li><li>Double track Hollis to Ironton: D- rules apply `+
        `there.</li></ul></div>`;
    if(state.orders.length)h+=`<div class="xw-orders"><b>Orders `+
        `held</b>${state.orders.map(o=>`<div class="ord">No ${o.no}: ${esc(o.text)}<span class="ok">OK</span></div>`).join("")}</div>`;
    el.innerHTML=h;
  }else{
    let h=`<h3>Kestrel Valley · Second Subdivision</h3><div class="sub">Track warrant control · dark `+
        `territory · double track Hollis to Ironton</div><div class="xw-tt" `+
        `tabindex="0"><table><thead><tr><th>Station</th><th>Siding</th><th>Notes</th><th>KV 812 E<small>run `+
        `min</small></th></tr></thead><tbody>`;
    STATIONS.forEach((st,
      i)=>{h+=`<tr class="${i===state.pos&&!state.moving?"here":""}"><td class="stn">${esc(st.n)}<small>MP `+
        `${st.mp.toFixed(1)}</small></td><td>${st.sd?"yes":"no"}</td><td>${st.yl?"yard limits":i===4?"tunnel":i===7?"double track east":""}</td><td `+
        `class="pencil">${i<LAST?state.tt.leg[i]:""}</td></tr>`});
    h+=`</tbody></table></div><div class="xw-si"><b>Special instructions</b><ul><li>Main track between the `+
        `yard limits is governed by track warrant (GCOR 14).</li><li>Ashby and Ironton yard limits: GCOR `+
        `6.13.</li><li>Double track Hollis to Ironton: Main 1 eastward, Main 2 westward.</li><li>Dispatcher: `+
        `RK.</li></ul></div>`;
    el.innerHTML=h;
  }
}

/* ---------- start ---------- */
function begin(era){
  randSetup=randOrders=randChoices=Math.random;
  for(const k of Object.keys(state))delete state[k];
  Object.assign(state,newState(era));ENGINE.reset();
  $("xwLog").innerHTML="";trainMp=100;
  $("xwStart").hidden=true;$("xwGame").hidden=false;
  renderStatus();renderSheet();
  window.scrollTo({top:$("xw").getBoundingClientRect().top+scrollY-80,behavior:reduced?"auto":"smooth"});
  if(era==="tto")startTTO();else if(era==="yard")X.startYARD();
    else if(era==="sigs"||era==="sigr")X.startSIG(era==="sigs"?"speed":"route");else X.startTWC();
}
function showStart(){
  $("xwStart").hidden=false;$("xwGame").hidden=true;
  $("sigSys").closest(".xw-switch").classList.toggle("on",$("sigSys").checked);
  $("sigRules").textContent=sigEra()==="sigr"?"Rulebook: the Signals guide (route signals and plates)":"Rulebook: 1949 Standard Code Rules 281 to 292, with the Signals guide's plates";
  const runs=store.get("xw_runs",[]);
  const best=e=>{const r=runs.filter(x=>x.era===e&&!x.failed).sort((a,b)=>a.marks-b.marks||a.time-b.time)[0];
    return r?`${r.verdict}, ${r.marks} mark${r.marks===1?"":"s"}, ${Math.floor(r.time/60)}h `+
      `${String(r.time%60).padStart(2,"0")}`:"none yet"};
  $("xwBest").textContent=runs.length?`Your best in this browser. ${Object.keys(RUNS).map(e=>RUNS[e].short+": "+best(e)).join(". ")}.`:"";
}
/* ---------- title screen (pixel art) ---------- */
(function title(){
  const cv=$("xwTitleCv");if(!cv)return;
  let g=cv.getContext("2d");const W=cv.width,H=cv.height;
  const SKY1="#e9dcb4",SKY2="#efe6c8",SKY3="#f5f0e1",SUN="#ead39a",GOLD="#ead39a",CREAM="#f5f0e1",RED="#a3302b",
    HILL1="#d6c79f",HILL2="#c3b287",GROUND="#a99a72",RAIL="#1d2733",INK="#1d2733",POLE="#5d5a4e",MUTED="#5d5a4e";
  const FONT={A:"01110100011000111111100011000110001",D:"11110100011000110001100011000111110",
    E:"11111100001000011110100001000011111",H:"10001100011000111111100011000110001",
    I:"11111001000010000100001000010011111",K:"10001100101010011000101001001010001",
      L:"10000100001000010000100001000011111",N:"10001110011010110011100011000110001",
    O:"01110100011000110001100011000101110",P:"11110100011000111110100001000010000",
      R:"11110100011000111110101001001010001",S:"01111100001000001110000010000111110",
    T:"11111001000010000100001000010000100",V:"10001100011000110001100010101000100",
      W:"10001100011000110101101011010101010",X:"10001100010101000100010101000110001",
    Y:"10001100010101000100001000010000100",C:"01111100001000010000100001000001111",
      U:"10001100011000110001100011000101110",
    B:"11110100011000111110100011000111110",M:"10001110111010110101100011000110001",
      "4":"00010001100101010010111110001000010","6":"01110100001000011110100011000101110",
    "·":"00000000000000000100000000000000000"," ":"00000000000000000000000000000000000"};
  function text(str,x,y,sc,col,shadow){
    const w=str.length*6*sc-sc;if(x==="c")x=Math.round((W-w)/2);
    for(const pass of shadow?[[shadow,1],[col,0]]:[[col,0]]){
      g.fillStyle=pass[0];
        [...str].forEach((ch,i)=>{const f=FONT[ch]||FONT[" "];
        for(let r=0;r<7;r++)for(let c=0;c<5;c++)if(f[r*5+c]==="1")g.fillRect(x+pass[1]+(i*6+c)*sc,y+pass[1]+r*sc,sc,
        sc)});
    }
  }
  // the still part of the picture, drawn once
  const bg=document.createElement("canvas");bg.width=W;bg.height=H;const b=bg.getContext("2d");
  [[0,SKY1],[30,SKY2],[52,SKY3]].forEach(([y,c],i,arr)=>{b.fillStyle=c;b.fillRect(0,y,W,(arr[i+1]?arr[i+1][0]:H)-y)});
  b.fillStyle=SKY2;for(let x=0;x<W;x+=2)b.fillRect(x+(x/2%2),29,1,1); // dithered band edges
  b.fillStyle=SKY3;for(let x=0;x<W;x+=2)b.fillRect(x+(x/2%2),51,1,1);
  b.fillStyle=SUN;
    for(let dy=-8;dy<=8;dy++){const w=Math.round(Math.sqrt(64-dy*dy));
    b.fillRect(212-w,68+dy,w*2+1,1)} // rising sun (east is on the right)
  function ridge(base,amp,step,col,seed){b.fillStyle=col;let h=0;
    for(let x=0;x<W;x++){if(x%step===0)h=Math.round(amp*(.5+.5*Math.sin(x*.045+seed)+.35*Math.sin(x*.13+seed*2)));
    b.fillRect(x,base-h,1,H)}}
  ridge(84,22,4,HILL1,1.3);ridge(92,14,3,HILL2,4.1);
  b.fillStyle=GROUND;b.fillRect(0,104,W,H-104);
  b.fillStyle=RAIL;b.fillRect(0,103,W,1);b.fillStyle="#8c7e58";for(let x=0;x<W;x+=4)b.fillRect(x,105,2,1);
  b.fillStyle=POLE;for(let x=10;x<W;x+=48){b.fillRect(x,82,1,21);b.fillRect(x-3,83,7,1)} // telegraph poles
  for(let x=10;x<W-48;x+=48)for(let i=0;i<48;i++)b.fillRect(x+i,84+Math.round(2*Math.sin(Math.PI*i/48)),1,1);
  { const keep=g;g=b; // the lettering never changes, so it goes on the still picture once
    text("KESTREL VALLEY RAILROAD","c",7,1,INK);text("EXTRA EAST","c",19,3,INK,RED);
      text("ASHBY TO IRONTON · 46 MILES","c",45,1,MUTED);g=keep }
  // the train, 92 px long, facing east (right)
  function train(x,f){
    const px=(c,a,y,w,h)=>{g.fillStyle=c;g.fillRect(Math.round(x+a),y,w,h)};
    // caboose
    px(RED,0,92,14,9);px(RED,4,88,6,4);px(INK,3,87,8,1);px(CREAM,2,94,3,2);px(CREAM,9,94,3,2);
    // boxcar
    px("#6b4a33",16,90,20,11);px("#5a3d29",23,91,6,9);
    // gondola with coal
    px("#3d4652",38,95,18,6);px(INK,39,93,16,2);
    // tender
    px(INK,58,92,14,9);px("#2a2f36",59,90,12,2);
    // engine 812: cab, boiler, stack, dome, headlight, pilot
    px(INK,73,86,9,15);px(SUN,75,88,4,4);px(INK,82,92,18,7);px(INK,95,85,3,7);px(INK,94,84,5,1);px(INK,88,90,3,2);
      px(SUN,100,92,2,2);px(INK,99,99,4,2);
    // wheels and rods, turning
    for(const a of [3,10,18,26,32,44,52,60,69])px(INK,a,101,3,2);
    for(const a of [84,89,94])px(INK,a,99,4,4);
    px(RED,84,100+(f%2),14,1);
    // smoke
    for(let i=0;i<4;i++){const p=(f+i*3)%12;g.fillStyle=`rgba(150,140,115,${(1-p/12)*.75})`;
      g.fillRect(Math.round(x+96-p*2.2),82-p*2,2+(p>>2),2+(p>>2))}
  }
  function draw(t){
    g.drawImage(bg,0,0);
    const span=W+110,x=still?120:((t/40)%span)-100;
    train(x,Math.floor(t/120));
  }
  const still=reduced;
  if(still){draw(0);return}
  let raf=0;const loop=t=>{draw(t);raf=requestAnimationFrame(loop)};
  // run only while the title is on screen
  const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting&&!raf)raf=requestAnimationFrame(loop);
    else if(!e.isIntersecting&&raf){cancelAnimationFrame(raf);raf=0}})});
  io.observe(cv);draw(0);
})();
const sigEra=()=>$("sigSys").checked?"sigr":"sigs";
$("sigSys").checked=store.get("xw_sigsys","sigs")==="sigr";
$("sigSys").onchange=()=>{store.set("xw_sigsys",sigEra());showStart()};
document.querySelectorAll("[data-era]").forEach(b=>b.onclick=()=>begin(b.dataset.era==="sig"?sigEra():b.dataset.era));
showStart();
Object.assign(X,{state,$,fmt,esc,rnd,pick,shuffle,randSetup:()=>randSetup(),reduced,STATIONS,LAST,addTime,renderMap,
  animateTo,renderStatus,renderSheet,runTime,drawRoad,drawStation,semSvg,finish,push,front,next,log,scene,ask,info});
})();
