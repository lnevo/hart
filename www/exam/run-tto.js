/* Extra East: the 1949 run under time-table and train orders: the time-table, the station choices, the move check
   and the fastest-legal-run solver, and the train order office. Its event pools are in run-1949.js, drawn by run.js
   (drawRoad, drawStation).
   Runs inside its own function. It takes the names it uses from run.js with ExtraEast.take and hands back its own with
   ExtraEast.give (see run.js, GIVES). */
(function(){
"use strict";
const X=window.ExtraEast;
const {fmt,$,esc,rnd,pick,randSetup,randOrders,STATIONS,LAST,state,addTime,animateTo,runTime,drawRoad,drawStation,
  semSvg,finish,push,front,next,log,scene,ask,info}=X.take("run-tto.js",["fmt","$","esc","rnd","pick","randSetup",
  "randOrders","STATIONS","LAST","state","addTime","animateTo","runTime","drawRoad","drawStation","semSvg","finish",
  "push","front","next","log","scene","ask","info"]);
/* The regular trains and the time order: run-data.js, which the answer key reads too. */
const {REGULARS,TIME_ORDER}=window.ExtraEastData;
const DOUBLE_TRACK_FROM=7; // double track from Hollis (index 7) to Ironton

/* ---------- 1949: time-table and train orders ---------- */
/* Regular trains. dir W runs Ironton→Ashby (index falling), E runs Ashby→Ironton.
   t[i] is the scheduled time at station i (one time = leaving time, Rule 5). act[i] is when the train actually passes. */
function makeTT(){
  const run=(mp0,mp1,f)=>Math.abs(mp1-mp0)*f;
  function sched(dir,startT,f){
    const t=new Array(STATIONS.length);
    if(dir==="W"){
      t[LAST]=startT;
      for(let i=LAST-1;i>=0;i--)t[i]=Math.round(t[i+1]+run(STATIONS[i+1].mp,STATIONS[i].mp,f));
    }else{
      t[0]=startT;
      for(let i=1;i<=LAST;i++)t[i]=Math.round(t[i-1]+run(STATIONS[i-1].mp,STATIONS[i].mp,f));
    }
    return t;
  }
  const [no1,no2,no21]=REGULARS.map(({start,spread,f,...tr})=>({...tr,t:sched(tr.dir,start+rnd(spread[0],spread[1]),f)}));
  [no1,no2,no21].forEach(tr=>{
    tr.act=tr.t.slice();
    tr.late=0;
  });
  const trains=[no1,no21,no2];
  // No 2 runs in two sections on about half the runs: Second 2 is on the same schedule, about 10 minutes behind.
  if(randSetup()<.5){
    no2.signals=true;
    trains.push({id:"2nd2",name:"Second 2",dir:"E",cls:"First class",hidden:true,t:no2.t.slice(),
      act:no2.t.map(x=>x+10+rnd(0,4)),late:0});
  }
  // the extra's running times between stations
  const leg=[];
  for(let i=0;i<LAST;i++)leg[i]=Math.round(run(STATIONS[i].mp,STATIONS[i+1].mp,3.3))+rnd(-1,2);
  return {trains,leg};
}
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
    if(k===LAST){
      best=Math.min(best,c);
      return;
    }
    const key=k+":"+c+":"+stopped;
    if(seen.has(key)||c>=best)return;
    seen.add(key);
    let n=0;
    for(let j=k+1;j<=LAST&&n<3;j++){ // the same three choices stationTTO offers
      if(!STATIONS[j].sd)continue;
      n++;
      const to=(!stopped&&office>k&&office<j)?office:j; // the board at the order office stops the train
      const a=c+runTime(k,to);
      // the clearance fix happens at the office
      if(!checkMove(k,to,c,a).length)go(to,a+(!stopped&&to===office?(state.clearFix||0):0),stopped||to===office);
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
    ()=>{
      log("Extra 812 East ready at Ashby");
      stationTTO();
    }
  );
  next();
}
function storeScene(){
  const f=1,t=0;
  scene("Ashby","The caboose locker",
    "<p>The locker holds "+f+" fusee and no torpedoes. Rule 99 calls for two torpedoes, lighted fusees when necessary, and a "+
      "lighted fusee left behind when the flagman is recalled. Each trip to the storeroom costs "+
      "time.</p><div class='choices' id='stb'></div>");
  const items=[
    {t:"Sign out 4 fusees and 4 torpedoes",s:"6 min",min:6,f:4,tp:4},
    {t:"Sign out 2 fusees and 2 torpedoes",s:"3 min",min:3,f:2,tp:2},
    {t:"Leave with what is in the locker",s:"no delay",min:0,f:0,tp:0}];
  $("stb").innerHTML=items.map((x,i)=>`<button class="xw-btn" data-i="${i}">${esc(x.t)}<small>${esc(x.s)}</small></button>`).join("");
  $("stb").querySelectorAll("button").forEach(b=>b.onclick=()=>{
    $("stb").querySelectorAll("button").forEach(z=>z.disabled=true);
    const x=items[+b.dataset.i];
    state.fus=f+x.f;
    state.torp=t+x.tp;
    addTime(x.min);
    log(`Caboose: ${state.fus} fusees, ${state.torp} torpedoes`);
    next();
  });
}

/* station decision */
function stationTTO(){
  const k=state.pos;
  if(k===LAST){
    endTTO();
    return;
  }
  scene(STATIONS[k].n,"At "+STATIONS[k].n+(state.inSiding&&k>0?", in the siding":""),
    `<p>${k===0?"Your train stands at Ashby, ready to leave.":"Extra 812 East is in the clear at "+STATIONS[k].n+"."} `+
      `Choose how far to run, or wait in the siding for the next train to pass. Use the time-table and `+
      `your running times.</p><div class="choices" id="dc"></div>`);
  const opts=[];
  let n=0;
  for(let j=k+1;j<=LAST&&n<3;j++){
    if(!STATIONS[j].sd)continue;
    n++;
    const via=[];
    for(let m=k+1;m<j;m++)via.push(STATIONS[m].n);
    opts.push({j,t:"Run to "+STATIONS[j].n,
      s:"arrive about "+fmt(state.clock+runTime(k,j))+(via.length?" · through "+via.join(", "):"")});
  }
  $("dc").innerHTML=opts.map((o,i)=>`<button class="xw-btn" data-i="${i}">${esc(o.t)}<small>${esc(o.s)}</small></button>`).join("")+
    `<button class="xw-btn" id="dw">Wait in the siding for the next `+
    `train<small>${k===0?"stay at Ashby":"hold at "+esc(STATIONS[k].n)}</small></button>`;
  const lock=f=>()=>{
    $("dc").querySelectorAll("button").forEach(z=>z.disabled=true);
    f();
  };
  $("dc").querySelectorAll("button[data-i]").forEach(b=>b.onclick=lock(()=>departTTO(opts[+b.dataset.i].j)));
  $("dw").onclick=lock(waitTTO);
}
function waitTTO(){
  const k=state.pos;
  const due=state.tt.trains.filter(tr=>tr.act[k]>state.clock).sort((a,b)=>a.act[k]-b.act[k]);
  if(!due.length){
    addTime(10);
    log("Waited 10 minutes at "+STATIONS[k].n);
    front(info(STATIONS[k].n,"Nothing comes",
      "<p>Ten minutes pass and no train comes by. No more regular trains are due at "+esc(STATIONS[k].n)+".</p>"),
      stationTTO);
    next();
    return;
  }
  const tr=due[0];
  state.clock=Math.max(state.clock,tr.act[k]);
  if(tr.hidden)tr.hidden=false;
  let txt=`${tr.name} passes ${STATIONS[k].n} at ${fmt(tr.act[k])}`;
  if(tr.signals)txt+=", with two green flags on the front of the engine";
  if(tr.meetOnly)txt=`${tr.name} arrives at ${STATIONS[k].n} at ${fmt(tr.act[k])} and stops on the main track`;
  log(txt);
  const scenes=[info(STATIONS[k].n,tr.name+(tr.meetOnly?" arrives":" goes by"),"<p>"+esc(txt)+".</p>")];
  if(tr.signals&&!state.used.has("r20")){
    state.used.add("r20");
    scenes.push(ask({sec:"sup",src:"SC · Rule 20",title:"Two green flags",
      body:"No 2 went by with two green flags on the front of the engine. What do they tell you?",
      right:"Another section of No 2 follows on the same schedule",
      wrong:[["No 2 is running late"],["No 2 has right over all trains"],["The track ahead is clear for two blocks"]],
      why:"Rule 20: all sections except the last display two green flags, and two green lights at night. A "+
        "section is one of two or more trains running on the same schedule, so Second 2 runs on No 2's "+
        "schedule and you keep clear of it too. The time-table now shows it.",
      after:()=>{
        state.tt.trains.forEach(t=>{
          if(t.id==="2nd2")t.hidden=false;
        });
    }}));
  }
  front(...scenes,stationTTO);
  next();
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
    state.used.add("hot");
    delay=15;
    state.hotDelay=15;
    scenes.push(hotBox(k,stopAt,p=>{
      prot=p;
    }));
  }else{
    const ev=drawRoad();
    if(ev)scenes.push(ev);
  }
  state.depAt=state.clock;
  scenes.push(()=>resolveMove(k,stopAt,delay,()=>prot));
  log("Leaves "+STATIONS[k].n+(stopAt!==j?" for "+STATIONS[j].n:""));
  state.legs++;
  state.inSiding=false;
  state.moving=STATIONS[k].n+" and "+STATIONS[stopAt].n;
  front(...scenes);
  next();
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
  if(sev){
    animateTo(j,()=>crash(sev,k,j));
    return;
  }
  const sev2=fault2.find(p=>p.kind==="headon"||p.kind==="rear");
  const notes=[];
  fault.filter(p=>p.kind==="margin").forEach(p=>notes.push(marginMiss(p,j)));
  fault.filter(p=>p.kind==="r86").forEach(p=>notes.push(r86Miss(p,j)));
  if(prot!=="ok")fault2.filter(p=>p.kind==="r86").forEach(p=>notes.push(r86Miss(p,j)));
  if(sev2){
    if(prot!=="ok"){
      animateTo(j,()=>crash(sev2,k,j,true));
      return;
    }
    notes.push(info(null,"Flagged",
      `<p>${esc(sev2.tr.name)} came up while you stood on the main. Your flagman stopped it, and it `+
        `followed you in at restricted speed.</p>`));
  }
  animateTo(j,()=>{
    state.clock=a1+extra;
    state.pos=j;
    state.moving=null;
    state.inSiding=STATIONS[j].sd&&j<LAST;
    arriveTTO(j,notes);
  });
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
  if(p.kind==="meet"){
    const w="Extra 812 East ran past Granite before Extra 530 West arrived",
    y="Form S-A, as the TT&TO primer explains it: neither train may proceed past the meeting point until "+
      "both have arrived.";
    state.misses.push({title:"Meet order",why:y,src:"TT · Forms",sec:"to",end:true});
    log("✗ "+w);
    finish(w+". "+y,true);
    return;
  }
  const what=p.kind==="headon"?`${p.tr.name} met Extra 812 East head-on ${between}`:
    `${p.tr.name} ran into the rear of Extra 812 East ${between}`;
  let why=p.kind==="headon"
    ?`You left ${STATIONS[k].n} at a time when you could not reach ${STATIONS[j].n} ahead of `+
    `${p.tr.name}. An extra must keep out of the way of opposing regular trains and clear their time by `+
    `5 minutes (Rule S-87), or be protected under Rule 99.`
    :`${p.tr.name} is superior and was following you. You had to be clear when it was due to leave the `+
    `station behind you (Rule 86).`;
  if(p.tr.id==="2nd2")why+=" The two green flags on No 2 meant Second 2 was following on the same schedule (Rule 20).";
  if(stopped){
    why=`The train stopped on the main with a hot box, and it was not protected. Rule 99: the flagman goes `+
      `back with two torpedoes and lighted fusees when necessary, and the front is protected the same way `+
      `when necessary.`;
  }
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
      okText:can?"Right. The engineman whistles — o o o (Rule 14(c)) and the flagman goes back. (Uses 1 fusee and 2 torpedoes.)":
        "Right, but the caboose is short of flag equipment, so the train stands unprotected. +1 mark.",
      why:"Rule 99: a stopped train that may be overtaken is protected by the flagman going back with two "+
        "torpedoes and, when necessary, lighted fusees; when called in he leaves the torpedoes and a lighted "+
        "fusee. The front is protected the same way when necessary.",
      note:can?"":"Sign out enough at the start.",
      after:ok=>{
        if(ok&&can){
          state.fus-=1;
          state.torp-=2;
          setProt("ok");
        }else setProt("none");
    }})();
  };
}
function arriveTTO(j,notes){
  log("Arrives "+STATIONS[j].n);
  const scenes=[];
  if(j===LAST){
    front(...(notes||[]),stationTTO);
    next();
    return;
  }
  if(j===state.officeOrders&&!state.used.has("orders")){
    state.used.add("orders");
    scenes.push(...orderBoard(j));
  }
  if(state.meet&&j===state.meet.at&&!state.used.has("s88")){
    state.used.add("s88");
    scenes.push(ask({sec:"sup",src:"SC · Rule S-88",title:"Meeting Extra 530 West",
      body:"Your order says Extra 812 East meet Extra 530 West at Granite. Westward trains are superior by "+
        "direction. Which extra takes the siding?",right:"Extra 812 East, the train in the inferior time-table direction",
      wrong:[["Extra 530 West, because it is the opposing train"],["Whichever arrives first"],
        ["The one with the higher engine number"]],
      why:"Rule S-88: when two extras meet, the train in the inferior time-table direction takes the siding, "+
        "unless otherwise provided. The TT&TO primer on Form S-A: neither train goes past Granite until both "+
        "have arrived."}));
  }
  if(!state.used.has("r104")&&j>0){
    state.used.add("r104");
    scenes.push(ask({sec:"sup",src:"SC · Rule 104",title:"The siding switch",
      body:"Your head brakeman lined the switch at "+STATIONS[j].n+" and the train pulled into the siding. Who is responsible for that switch now?",
      right:"You, the conductor: it must be lined back for the main track",
      wrong:[["The section foreman"],["The engineman"],["Nobody; leave it open for the next train"]],
      why:"Rule 104: conductors are responsible for the position of switches used by them and their crews, "+
        "except where switch tenders are stationed. A switch must not be left open for another train unless "+
        "a member of that train's crew is in charge of it."}));
  }else{
    const ev=drawStation();
    if(ev)scenes.push(ev);
  }
  front(...(notes||[]),...scenes,stationTTO);
  next();
}
/* Coming into the open office at j: the train order board shows stop (Rule 221). */
function boardAsk(j){
  return ask({sec:"to",src:"SC · Rule 221",where:STATIONS[j].n,title:"The train order board",
    body:`Coming into ${STATIONS[j].n}, the semaphore at the open office shows its blade horizontal.`,extra:semSvg(0),
    right:"Stop: an operator is on duty, and you must not leave without a Clearance Form A",
    wrong:[["Slow down and take orders on the fly"],["Proceed: it is only a block signal"],
      ["Whistle — — and keep going"]],
    why:"Rule 221: the train order signal shows stop while an operator is on duty, and trains must not "+
      "leave without a Clearance Form A. The semaphore guide adds that a horizontal blade is always stop."});
}
/* The orders the office at j holds: a time order on a regular train still ahead of us, and sometimes a meet with an
   extra at Granite. Each is {no, text, apply}, plus tr and L for a time order; apply puts it into effect. */
function drawOrders(j){
  const n1=rnd(TIME_ORDER.no[0],TIME_ORDER.no[1],randOrders);
  const cand=state.tt.trains.filter(tr=>tr.dir==="W"&&!tr.hidden&&tr.act[j]>state.clock+10);
  const orders=[];
  if(cand.length){
    const tr=pick(cand,randOrders),L=pick(TIME_ORDER.late,randOrders);
    orders.push({no:n1,text:TIME_ORDER.words(tr.name,L),
      apply:()=>{
        tr.late+=L;
        tr.lateAt=tr.act.map(x=>x>state.clock);
        tr.act=tr.act.map(x=>x>state.clock?x+L:x);
      },
      tr,L});
  }
  const meet=(randOrders()<.6||!cand.length)&&j<6;
  const meetAfter=rnd(30,50,randOrders);
  if(meet){
    orders.push({no:n1+(orders.length?1:0),text:"Extra 812 East meet Extra 530 West at Granite",
      apply:()=>{
        const t=new Array(STATIONS.length);
        t[LAST]=state.start+150+meetAfter;
        for(let i=LAST-1;i>=6;i--)t[i]=Math.round(t[i+1]+(STATIONS[i+1].mp-STATIONS[i].mp)*3.3);
        const tr={id:"530",name:"Extra 530 West",dir:"W",cls:"Extra",t:t.slice(),act:t,meetOnly:true,meetAt:6,late:0};
        state.tt.trains.push(tr);
        state.meet={at:6,tr};
    }});
  }
  return orders;
}
/* The scene where the operator hands up the orders and Clearance Form A, which lists the numbers `shown`. */
function ordersScene(j,orders,shown){
  const clearTxt=`CLEARANCE FORM A\nTo KV Extra 812 East  at ${STATIONS[j].n.toUpperCase()}\nI have ${shown.length} `+
    `order${shown.length>1?"s":""} for your train.\nNos ${shown.join(", ")}\nOK  ${fmt(state.clock+3)}  `+
    `RK, dispatcher`;
  const ordTxt=orders.map(o=>`<span class="no">Order No ${o.no}</span>\n${esc(o.text)}`).join("\n\n");
  return info(STATIONS[j].n,"Orders",
    "<p>The operator hands up the orders and the clearance.</p><div class='xw-tele'>"+ordTxt+"</div><div class='xw-clear'>"+esc(clearTxt)+"</div>",
    "Check them");
}
/* The clearance check (Rule 211): a clearance with a wrong number holds the train while the operator corrects it. */
function clearanceAsk(wrongClear,nums,shown){
  if(wrongClear){
    return ask({sec:"to",src:"SC · Rule 211",title:"Check the clearance",
      body:`The clearance lists Nos ${shown.join(", ")}, but you hold Nos ${nums.join(", ")}. What do you do?`,
      right:"Do not leave; have the operator correct it with the dispatcher",
      wrong:[["Leave; the orders in hand are what count"],["Cross out the number and write the right one in"],
        ["Leave and report it from the next office"]],
      why:"Rule 211: Clearance Form A is filled out without erasure or alteration, and conductors, enginemen "+
        "and firemen must see that its information matches the orders received.",
      after:()=>{
        addTime(6);
        state.clearFix=6;
        log("Clearance corrected (+6 min)");
    }});
  }
  return ask({sec:"to",src:"SC · Rule 211",title:"Check the clearance",
    body:`The clearance lists Nos ${shown.join(", ")} and you hold Nos ${nums.join(", ")}. Who on your crew `+
      `must check that they match?`,right:"The conductor, the engineman and the fireman",
    wrong:[["Only the conductor"],["Only the engineman"],["The operator alone"]],
    why:"Rule 211: conductors, enginemen and firemen, and trainmen when practicable, must see that the "+
      "information on Clearance Form A matches the train orders received."});
}
/* What the time order means for us (Form E). */
function timeOrderAsk(j,time){
  return ask({sec:"to",src:"SC · Form E",ref:"order",title:"Order No "+time.no,
    body:`“${esc(time.text)}.” What does this order do for you?`,
    right:`Run with respect to ${time.tr.name}'s schedule ${time.L} minutes later`,
    wrong:[[`Ignore ${time.tr.name} until Ironton`],[`Wait at ${STATIONS[j].n} for ${time.tr.name}`],
      [`You now have right over ${time.tr.name}`]],
    why:"Form E, a time order: any train receiving it runs with respect to the later time exactly as it "+
      "would to the regular schedule. The time-table on the right now shows the new times in red."});
}
/* The scenes at an open office with orders for us: the board, the orders, the clearance check and the time order. */
function orderBoard(j){
  const out=[boardAsk(j)];
  const orders=drawOrders(j);
  const nums=orders.map(o=>o.no);
  const wrongClear=randOrders()<.5;
  const shown=wrongClear?nums.map((x,i)=>i===nums.length-1?x+3:x):nums;
  out.push(ordersScene(j,orders,shown),clearanceAsk(wrongClear,nums,shown));
  const time=orders.find(o=>o.L);
  if(time)out.push(timeOrderAsk(j,time));
  out.push(()=>{
    orders.forEach(o=>{
      o.apply();
      state.orders.push(o);
    });
    log("Orders "+nums.join(", ")+" received");
    next();
  });
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
X.give("run-tto.js",{startTTO,solvePar});
})();
