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
const GRANITE=6; // the station index of Granite, where a meet order puts Extra 530 West

/* The extra's running time, in minutes per mile; Extra 530 West runs at the same rate. */
const EXTRA_MIN_PER_MILE=3.3;
/* The extra's time on each leg varies by this many minutes, low and high. */
const LEG_SPREAD=[-1,2];
/* Second 2: how often No 2 runs in two sections, and how many minutes behind it the second section runs, plus a
   spread of a few more. */
const SECOND_SECTION_CHANCE=.5,SECOND_SECTION_BEHIND=10,SECOND_SECTION_SPREAD=[0,4];
/* The hot box: how often a run has one, the legs it may come on, and the minutes the train stands on the main. */
const HOT_BOX_CHANCE=.75,HOT_BOX_LEGS=[1,5],HOT_BOX_MIN=15;
/* The quickest storeroom sign-out, in minutes: a run with a hot box must have signed out flag equipment, so its par
   starts that much later. */
const MIN_SIGN_OUT=3;
/* Rule S-87: an extra clears the time of an opposing regular train by not less than this many minutes. */
const CLEAR_MARGIN=5;
/* The problems of a move that end the run: a collision or a run past the meeting point. A missed margin (margin, r86)
   is a mark. */
const RUN_ENDING=new Set(["headon","rear","meet"]);
/* The farthest stations with a siding the crew may run to from one station. */
const CHOICES_AHEAD=3;
/* A wait with no train due, and how far past the start the par search keeps waiting, in minutes. waitTTO's
   "Ten minutes pass" spells WAIT_MIN out: change the two together. */
const WAIT_MIN=10,PAR_HORIZON=720;
/* What is in the caboose locker at the start, and what Rule 99 protection uses up. */
const LOCKER_FUSEES=1,LOCKER_TORPEDOES=0,FLAG_FUSEES=1,FLAG_TORPEDOES=2;
/* The stations whose office may hold orders for us: Cobb or Dunmore. */
const ORDER_OFFICES=[2,3];
/* A time order is on a westward train at least this many minutes from the office. */
const TIME_ORDER_LEAD=10;
/* The meet with Extra 530 West at Granite: how often an office holds one, and when 530 West leaves Ironton, in minutes
   after the start plus a drawn spread. */
const MEET_ORDER_CHANCE=.6,MEET_LEAVES_AFTER=150,MEET_SPREAD=[30,50];
/* The clearance: the minutes to its OK time, how often it lists a wrong number, how far off that number is, and the
   minutes the correction takes. */
const CLEARANCE_OK_IN=3,WRONG_CLEARANCE_CHANCE=.5,WRONG_NUMBER_OFF_BY=3,CLEARANCE_FIX_MIN=6;

/* ---------- 1949: time-table and train orders ---------- */
/* Regular trains. dir W runs Ironton→Ashby (index falling), E runs Ashby→Ironton.
   t[i] is the scheduled time at station i (one time = leaving time, Rule 5). act[i] is when the train actually passes. */
function makeTT(){
  const runMinutes=(fromMp,toMp,minPerMile)=>Math.abs(toMp-fromMp)*minPerMile;
  function schedule(dir,startTime,minPerMile){
    const times=new Array(STATIONS.length);
    if(dir==="W"){
      times[LAST]=startTime;
      for(let i=LAST-1;i>=0;i--)times[i]=Math.round(times[i+1]+runMinutes(STATIONS[i+1].mp,STATIONS[i].mp,minPerMile));
    }else{
      times[0]=startTime;
      for(let i=1;i<=LAST;i++)times[i]=Math.round(times[i-1]+runMinutes(STATIONS[i-1].mp,STATIONS[i].mp,minPerMile));
    }
    return times;
  }
  const [no1,no2,no21]=REGULARS.map(({start,spread,f,...tr})=>({...tr,t:schedule(tr.dir,start+rnd(spread[0],spread[1]),f)}));
  [no1,no2,no21].forEach(tr=>{
    tr.act=tr.t.slice();
    tr.late=0;
  });
  const trains=[no1,no21,no2];
  // No 2 runs in two sections on about half the runs: Second 2 is on the same schedule, about 10 minutes behind.
  if(randSetup()<SECOND_SECTION_CHANCE){
    no2.signals=true;
    trains.push({id:"2nd2",name:"Second 2",dir:"E",cls:"First class",hidden:true,t:no2.t.slice(),
      act:no2.t.map(x=>x+SECOND_SECTION_BEHIND+rnd(SECOND_SECTION_SPREAD[0],SECOND_SECTION_SPREAD[1])),late:0});
  }
  // the extra's running times between stations
  const legMinutes=[];
  for(let i=0;i<LAST;i++)
    legMinutes[i]=Math.round(runMinutes(STATIONS[i].mp,STATIONS[i+1].mp,EXTRA_MIN_PER_MILE))+rnd(LEG_SPREAD[0],LEG_SPREAD[1]);
  return {trains,leg:legMinutes};
}
/* Check a move from station `from` (leaving at leaveAt) to station `to`, arriving at arriveAt. Returns the problems,
   the worst first. */
function checkMove(from,to,leaveAt,arriveAt){
  const problems=[];
  for(const tr of state.tt.trains){
    if(tr.meetOnly){
      if(to<=tr.meetAt)continue; // it waits at the meeting point for us
      if(from<tr.meetAt){ // running through the meeting point: it must already be there
        if(tr.act[tr.meetAt]>leaveAt+runTime(from,tr.meetAt))problems.push({kind:"meet",tr});
        continue;
      }
    }
    if(tr.dir==="W"){
      if(tr.act[from]<=leaveAt)continue; // already past us
      if(from>=DOUBLE_TRACK_FROM)continue; // double track: opposing trains use the other main (Rule D-71)
      // only the single-track part can meet them
      const singleEnd=Math.min(to,DOUBLE_TRACK_FROM),arriveSingleEnd=leaveAt+runTime(from,singleEnd);
      // head-on if it reaches singleEnd before we do, and we leave `from` before it gets there
      if(leaveAt<tr.act[from]&&tr.act[singleEnd]<arriveSingleEnd)problems.push({kind:"headon",tr});
      else if(arriveSingleEnd>tr.act[singleEnd]-CLEAR_MARGIN&&!tr.meetOnly)
        problems.push({kind:"margin",tr,by:Math.round(tr.act[singleEnd]-arriveSingleEnd)});
    }else{
      if(tr.act[from]<=leaveAt)continue; // already ahead of us
      // Rule 86: clear at `to` by the time it is due to leave `from`, the station in its rear
      if(arriveAt>tr.act[from]){
        if(tr.act[to]<=arriveAt)problems.push({kind:"rear",tr});
        else problems.push({kind:"r86",tr,by:Math.round(arriveAt-tr.act[from])});
      }
    }
  }
  problems.sort((x,y)=>RUN_ENDING.has(y.kind)-RUN_ENDING.has(x.kind)); // the worst first
  return problems;
}
/* the best legal finish, for par */
function solvePar(){
  let best=Infinity;
  const seen=new Set(),office=state.officeOrders;
  function search(at,clock,stopped){
    if(at===LAST){
      best=Math.min(best,clock);
      return;
    }
    const key=at+":"+clock+":"+stopped;
    if(seen.has(key)||clock>=best)return;
    seen.add(key);
    let choices=0;
    for(let dest=at+1;dest<=LAST&&choices<CHOICES_AHEAD;dest++){ // the same choices stationTTO offers
      if(!STATIONS[dest].sd)continue;
      choices++;
      const stopAt=(!stopped&&office>at&&office<dest)?office:dest; // the board at the order office stops the train
      const arrive=clock+runTime(at,stopAt);
      // the clearance fix happens at the office
      if(!checkMove(at,stopAt,clock,arrive).length)
        search(stopAt,arrive+(!stopped&&stopAt===office?(state.clearFix||0):0),stopped||stopAt===office);
    }
    const waits=state.tt.trains.map(tr=>tr.act[at]).filter(t=>t!==undefined&&t>clock).sort((x,y)=>x-y);
    if(waits.length)search(at,waits[0],stopped||at===office);
    else if(clock<state.start+PAR_HORIZON)search(at,clock+WAIT_MIN,stopped||at===office);
  }
  search(0,state.start+(state.hotDelay?MIN_SIGN_OUT:0),false); // a hot box needs at least the quickest sign-out
  return best;
}

function startTTO(){
  state.tt=makeTT();
  state.par=0;
  state.officeOrders=pick(ORDER_OFFICES); // Cobb or Dunmore holds orders for us
  state.hotLeg=randSetup()<HOT_BOX_CHANCE?rnd(HOT_BOX_LEGS[0],HOT_BOX_LEGS[1]):-1;
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
  scene("Ashby","The caboose locker",
    "<p>The locker holds "+LOCKER_FUSEES+" fusee and no torpedoes. Rule 99 calls for two torpedoes, lighted fusees when necessary, and a "+
      "lighted fusee left behind when the flagman is recalled. Each trip to the storeroom costs "+
      "time.</p><div class='choices' id='stb'></div>");
  const items=[
    {t:"Sign out 4 fusees and 4 torpedoes",s:"6 min",min:6,f:4,tp:4},
    {t:"Sign out 2 fusees and 2 torpedoes",s:"3 min",min:3,f:2,tp:2},
    {t:"Leave with what is in the locker",s:"no delay",min:0,f:0,tp:0}];
  $("stb").innerHTML=items.map((x,i)=>`<button class="xw-btn" data-i="${i}">${esc(x.t)}<small>${esc(x.s)}</small></button>`).join("");
  $("stb").querySelectorAll("button").forEach(b=>b.onclick=()=>{
    $("stb").querySelectorAll("button").forEach(z=>z.disabled=true);
    const item=items[+b.dataset.i];
    state.fus=LOCKER_FUSEES+item.f;
    state.torp=LOCKER_TORPEDOES+item.tp;
    addTime(item.min);
    log(`Caboose: ${state.fus} fusees, ${state.torp} torpedoes`);
    next();
  });
}

/* station decision */
function stationTTO(){
  const at=state.pos;
  if(at===LAST){
    endTTO();
    return;
  }
  scene(STATIONS[at].n,"At "+STATIONS[at].n+(state.inSiding&&at>0?", in the siding":""),
    `<p>${at===0?"Your train stands at Ashby, ready to leave.":"Extra 812 East is in the clear at "+STATIONS[at].n+"."} `+
      `Choose how far to run, or wait in the siding for the next train to pass. Use the time-table and `+
      `your running times.</p><div class="choices" id="dc"></div>`);
  const runs=[];
  for(let dest=at+1;dest<=LAST&&runs.length<CHOICES_AHEAD;dest++){
    if(!STATIONS[dest].sd)continue;
    const via=[];
    for(let m=at+1;m<dest;m++)via.push(STATIONS[m].n);
    runs.push({dest,t:"Run to "+STATIONS[dest].n,
      s:"arrive about "+fmt(state.clock+runTime(at,dest))+(via.length?" · through "+via.join(", "):"")});
  }
  $("dc").innerHTML=runs.map((o,i)=>`<button class="xw-btn" data-i="${i}">${esc(o.t)}<small>${esc(o.s)}</small></button>`).join("")+
    `<button class="xw-btn" id="dw">Wait in the siding for the next `+
    `train<small>${at===0?"stay at Ashby":"hold at "+esc(STATIONS[at].n)}</small></button>`;
  const lock=f=>()=>{
    $("dc").querySelectorAll("button").forEach(z=>z.disabled=true);
    f();
  };
  $("dc").querySelectorAll("button[data-i]").forEach(b=>b.onclick=lock(()=>departTTO(runs[+b.dataset.i].dest)));
  $("dw").onclick=lock(waitTTO);
}
function waitTTO(){
  const at=state.pos;
  const due=state.tt.trains.filter(tr=>tr.act[at]>state.clock).sort((a,b)=>a.act[at]-b.act[at]);
  if(!due.length){
    addTime(WAIT_MIN);
    log("Waited "+WAIT_MIN+" minutes at "+STATIONS[at].n);
    front(info(STATIONS[at].n,"Nothing comes",
      "<p>Ten minutes pass and no train comes by. No more regular trains are due at "+esc(STATIONS[at].n)+".</p>"),
      stationTTO);
    next();
    return;
  }
  const tr=due[0];
  state.clock=Math.max(state.clock,tr.act[at]);
  if(tr.hidden)tr.hidden=false;
  let txt=`${tr.name} passes ${STATIONS[at].n} at ${fmt(tr.act[at])}`;
  if(tr.signals)txt+=", with two green flags on the front of the engine";
  if(tr.meetOnly)txt=`${tr.name} arrives at ${STATIONS[at].n} at ${fmt(tr.act[at])} and stops on the main track`;
  log(txt);
  const scenes=[info(STATIONS[at].n,tr.name+(tr.meetOnly?" arrives":" goes by"),"<p>"+esc(txt)+".</p>")];
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
function departTTO(dest){
  const from=state.pos;
  // a train order office with orders for us: the board shows stop and the train must stop there
  const office=(state.officeOrders>from&&state.officeOrders<dest&&!state.used.has("orders"))?state.officeOrders:-1;
  const stopAt=office>0?office:dest;
  const scenes=[];
  let delay=0,protection=null;
  // a hot box only where standing on the main for it cannot put the extra against an opposing train
  const hotBoxFits=!checkMove(from,stopAt,state.clock,
    state.clock+runTime(from,stopAt)+HOT_BOX_MIN).some(p=>p.kind==="headon"||p.kind==="margin");
  if(stopAt===LAST&&!state.used.has("d71")){
    state.used.add("d71");
    scenes.push(ask({sec:"sup",src:"SC · Rule D-71",title:"Onto double track",
      body:"East of Hollis the line is double track. On two or more tracks, how is a train superior?",
      right:"By right or class only; direction no longer counts",
      wrong:[["By right, class or direction, as on single track"],["By direction only"],["By class or direction"]],
      why:"Rule D-71: on two or more tracks a train is superior by right or class only. Right is conferred by "+
        "train order, class by time-table, and right is superior to class. The S- rules are the single-track versions."}));
  }else if(state.hotLeg>=0&&state.legs>=state.hotLeg&&!state.used.has("hot")&&hotBoxFits){
    state.used.add("hot");
    delay=HOT_BOX_MIN;
    state.hotDelay=HOT_BOX_MIN;
    scenes.push(hotBox(from,stopAt,given=>{
      protection=given;
    }));
  }else{
    const ev=drawRoad();
    if(ev)scenes.push(ev);
  }
  state.depAt=state.clock;
  scenes.push(()=>resolveMove(from,stopAt,delay,()=>protection));
  log("Leaves "+STATIONS[from].n+(stopAt!==dest?" for "+STATIONS[dest].n:""));
  state.legs++;
  state.inSiding=false;
  state.moving=STATIONS[from].n+" and "+STATIONS[stopAt].n;
  front(...scenes);
  next();
}
/* Wrong answers on the road cost time after arrival; only the hot box stop changes the move itself. */
function resolveMove(from,to,delay,getProtection){
  const leftAt=state.depAt,roadMinutes=state.clock-leftAt;
  const arrive=leftAt+runTime(from,to),arriveAfterStop=arrive+delay;
  const problems=checkMove(from,to,leftAt,arrive);
  // only what the hot box stop adds: Rule 99 protection covers a train that cannot clear in time (Rules 86, S-87)
  const stopProblems=delay?checkMove(from,to,leftAt,arriveAfterStop).filter(p=>!problems.some(f=>f.tr===p.tr)):[];
  const protection=getProtection();
  const collision=problems.find(p=>RUN_ENDING.has(p.kind));
  if(collision){
    animateTo(to,()=>crash(collision,from,to));
    return;
  }
  const stopCollision=stopProblems.find(p=>p.kind==="headon"||p.kind==="rear");
  const notes=[];
  problems.filter(p=>p.kind==="margin").forEach(p=>notes.push(marginMiss(p,to)));
  problems.filter(p=>p.kind==="r86").forEach(p=>notes.push(r86Miss(p,to)));
  if(protection!=="ok")stopProblems.filter(p=>p.kind==="r86").forEach(p=>notes.push(r86Miss(p,to)));
  if(stopCollision){
    if(protection!=="ok"){
      animateTo(to,()=>crash(stopCollision,from,to,true));
      return;
    }
    notes.push(info(null,"Flagged",
      `<p>${esc(stopCollision.tr.name)} came up while you stood on the main. Your flagman stopped it, and it `+
        `followed you in at restricted speed.</p>`));
  }
  animateTo(to,()=>{
    state.clock=arriveAfterStop+roadMinutes;
    state.pos=to;
    state.moving=null;
    state.inSiding=STATIONS[to].sd&&to<LAST;
    arriveTTO(to,notes);
  });
}
function marginMiss(p,at){
  return ask({miss:true,sec:"sup",src:"SC · Rule S-87",title:"Too close to "+p.tr.name,
    body:`You got into the siding at ${STATIONS[at].n} only ${Math.max(0,p.by)} minutes ahead of `+
      `${p.tr.name}'s time there. By how much must an extra clear the time of an opposing regular train?`,
    right:`Not less than ${CLEAR_MARGIN} minutes`,
    wrong:[["Any margin, as long as it is in the clear"],["Not less than 2 minutes"],["Only to the leaving time"]],
    ok:{marks:1},okText:"Right, and you did not. +1 mark.",
    why:`Rule S-87: extras must clear the time of opposing regular trains by not less than ${CLEAR_MARGIN} minutes unless `+
      "otherwise provided. The TT&TO primer quotes 10 minutes."});
}
function r86Miss(p,at){
  const note=p.tr.id==="2nd2"?"No 2's two green flags meant Second 2 was following on the same schedule (Rule 20).":"";
  return ask({miss:true,sec:"sup",src:"SC · Rule 86",title:p.tr.name+" was close behind",
    body:`${p.tr.name} was due to leave the station behind you before you were in the clear at `+
      `${STATIONS[at].n}. When must an inferior train running ahead of a superior train be clear?`,
    right:"When the superior train is due to leave the next station in the rear where time is shown",
    wrong:[["5 minutes before the superior train is due at the station ahead"],
      ["When the superior train comes in sight"],["At the superior train's arriving time at the station ahead"]],
    ok:{marks:1},okText:"Right, and you were not. +1 mark.",
    why:"Rule 86: unless otherwise provided, the inferior train must be clear at the time the superior "+
      "train is due to leave the next station in the rear where time is shown.",note});
}
function crash(p,from,to,stopped){
  const between=`between ${STATIONS[from].n} and ${STATIONS[to].n}`;
  if(p.kind==="meet"){
    const meetWhat="Extra 812 East ran past Granite before Extra 530 West arrived",
    meetWhy="Form S-A, as the TT&TO primer explains it: neither train may proceed past the meeting point until "+
      "both have arrived.";
    state.misses.push({title:"Meet order",why:meetWhy,src:"TT · Forms",sec:"to",end:true});
    log("✗ "+meetWhat);
    finish(meetWhat+". "+meetWhy,true);
    return;
  }
  const what=p.kind==="headon"?`${p.tr.name} met Extra 812 East head-on ${between}`:
    `${p.tr.name} ran into the rear of Extra 812 East ${between}`;
  let why=p.kind==="headon"
    ?`You left ${STATIONS[from].n} at a time when you could not reach ${STATIONS[to].n} ahead of `+
    `${p.tr.name}. An extra must keep out of the way of opposing regular trains and clear their time by `+
    `${CLEAR_MARGIN} minutes (Rule S-87), or be protected under Rule 99.`
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
function hotBox(from,to,setProtection){
  return ()=>{
    state.moving=STATIONS[from].n+" and "+STATIONS[to].n;
    const equipped=state.fus>=FLAG_FUSEES&&state.torp>=FLAG_TORPEDOES; // Rule 99: two torpedoes, and a lighted fusee left when recalled
    ask({sec:"sup",src:"SC · Rule 99",miss:!equipped,title:"Hot box",
      body:"Smoke from a journal on the ninth car. The engineer stops Extra 812 East on the main track to cool "+
        `and repack it, about ${HOT_BOX_MIN} minutes. Trains may come up behind you or against you. What protection do `+
        "you give the train?",
      right:"Flagman goes back with two torpedoes and, when necessary, lighted fusees; the front is protected "+
        "the same way when necessary",
      wrong:[["Leave the marker lamps lit; that is protection enough",{marks:1}],
        ["No protection; the stop is short",{marks:1}],
        ["Flagman drops a lighted fusee while the train stands",{marks:1},
          "Dropping fusees at intervals protects a moving train."]],
      ok:equipped?{}:{marks:1},
      okText:equipped?"Right. The engineman whistles — o o o (Rule 14(c)) and the flagman goes back. (Uses 1 fusee and 2 torpedoes.)":
        "Right, but the caboose is short of flag equipment, so the train stands unprotected. +1 mark.",
      why:"Rule 99: a stopped train that may be overtaken is protected by the flagman going back with two "+
        "torpedoes and, when necessary, lighted fusees; when called in he leaves the torpedoes and a lighted "+
        "fusee. The front is protected the same way when necessary.",
      note:equipped?"":"Sign out enough at the start.",
      after:ok=>{
        if(ok&&equipped){
          state.fus-=FLAG_FUSEES;
          state.torp-=FLAG_TORPEDOES;
          setProtection("ok");
        }else setProtection("none");
    }})();
  };
}
function arriveTTO(at,notes){
  log("Arrives "+STATIONS[at].n);
  const scenes=[];
  if(at===LAST){
    front(...(notes||[]),stationTTO);
    next();
    return;
  }
  if(at===state.officeOrders&&!state.used.has("orders")){
    state.used.add("orders");
    scenes.push(...orderBoard(at));
  }
  if(state.meet&&at===state.meet.at&&!state.used.has("s88")){
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
  if(!state.used.has("r104")&&at>0){
    state.used.add("r104");
    scenes.push(ask({sec:"sup",src:"SC · Rule 104",title:"The siding switch",
      body:"Your head brakeman lined the switch at "+STATIONS[at].n+" and the train pulled into the siding. Who is responsible for that switch now?",
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
/* Coming into the open office at station `at`: the train order board shows stop (Rule 221). */
function boardAsk(at){
  return ask({sec:"to",src:"SC · Rule 221",where:STATIONS[at].n,title:"The train order board",
    body:`Coming into ${STATIONS[at].n}, the semaphore at the open office shows its blade horizontal.`,extra:semSvg(0),
    right:"Stop: an operator is on duty, and you must not leave without a Clearance Form A",
    wrong:[["Slow down and take orders on the fly"],["Proceed: it is only a block signal"],
      ["Whistle — — and keep going"]],
    why:"Rule 221: the train order signal shows stop while an operator is on duty, and trains must not "+
      "leave without a Clearance Form A. The semaphore guide adds that a horizontal blade is always stop."});
}
/* The orders the office at station `at` holds: a time order on a regular train still ahead of us, and sometimes a meet with an
   extra at Granite. Each is {no, text, apply}, plus tr and L for a time order; apply puts it into effect. */
function drawOrders(at){
  const firstNo=rnd(TIME_ORDER.no[0],TIME_ORDER.no[1],randOrders);
  const ahead=state.tt.trains.filter(tr=>tr.dir==="W"&&!tr.hidden&&tr.act[at]>state.clock+TIME_ORDER_LEAD);
  const orders=[];
  if(ahead.length){
    const tr=pick(ahead,randOrders),L=pick(TIME_ORDER.late,randOrders);
    orders.push({no:firstNo,text:TIME_ORDER.words(tr.name,L),
      apply:()=>{
        tr.late+=L;
        tr.lateAt=tr.act.map(x=>x>state.clock);
        tr.act=tr.act.map(x=>x>state.clock?x+L:x);
      },
      tr,L});
  }
  const meet=(randOrders()<MEET_ORDER_CHANCE||!ahead.length)&&at<GRANITE;
  const meetAfter=rnd(MEET_SPREAD[0],MEET_SPREAD[1],randOrders);
  if(meet){
    orders.push({no:firstNo+(orders.length?1:0),text:"Extra 812 East meet Extra 530 West at Granite",
      apply:()=>{
        const times=new Array(STATIONS.length);
        times[LAST]=state.start+MEET_LEAVES_AFTER+meetAfter;
        for(let i=LAST-1;i>=GRANITE;i--)times[i]=Math.round(times[i+1]+(STATIONS[i+1].mp-STATIONS[i].mp)*EXTRA_MIN_PER_MILE);
        const tr={id:"530",name:"Extra 530 West",dir:"W",cls:"Extra",t:times.slice(),act:times,meetOnly:true,meetAt:GRANITE,late:0};
        state.tt.trains.push(tr);
        state.meet={at:GRANITE,tr};
    }});
  }
  return orders;
}
/* The scene where the operator hands up the orders and Clearance Form A, which lists the numbers `shown`. */
function ordersScene(at,orders,shown){
  const clearTxt=`CLEARANCE FORM A\nTo KV Extra 812 East  at ${STATIONS[at].n.toUpperCase()}\nI have ${shown.length} `+
    `order${shown.length>1?"s":""} for your train.\nNos ${shown.join(", ")}\nOK  ${fmt(state.clock+CLEARANCE_OK_IN)}  `+
    `RK, dispatcher`;
  const ordTxt=orders.map(o=>`<span class="no">Order No ${o.no}</span>\n${esc(o.text)}`).join("\n\n");
  return info(STATIONS[at].n,"Orders",
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
        addTime(CLEARANCE_FIX_MIN);
        state.clearFix=CLEARANCE_FIX_MIN;
        log("Clearance corrected (+"+CLEARANCE_FIX_MIN+" min)");
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
function timeOrderAsk(at,time){
  return ask({sec:"to",src:"SC · Form E",ref:"order",title:"Order No "+time.no,
    body:`“${esc(time.text)}.” What does this order do for you?`,
    right:`Run with respect to ${time.tr.name}'s schedule ${time.L} minutes later`,
    wrong:[[`Ignore ${time.tr.name} until Ironton`],[`Wait at ${STATIONS[at].n} for ${time.tr.name}`],
      [`You now have right over ${time.tr.name}`]],
    why:"Form E, a time order: any train receiving it runs with respect to the later time exactly as it "+
      "would to the regular schedule. The time-table on the right now shows the new times in red."});
}
/* The scenes at an open office with orders for us: the board, the orders, the clearance check and the time order. */
function orderBoard(at){
  const out=[boardAsk(at)];
  const orders=drawOrders(at);
  const nums=orders.map(o=>o.no);
  const wrongClear=randOrders()<WRONG_CLEARANCE_CHANCE;
  const shown=wrongClear?nums.map((x,i)=>i===nums.length-1?x+WRONG_NUMBER_OFF_BY:x):nums;
  out.push(ordersScene(at,orders,shown),clearanceAsk(wrongClear,nums,shown));
  const time=orders.find(o=>o.L);
  if(time)out.push(timeOrderAsk(at,time));
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
X.give("run-tto.js",{startTTO,solvePar,checkMove});
})();
