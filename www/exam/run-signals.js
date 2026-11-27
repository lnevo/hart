/* Extra East: the signals runs, speed semaphores or route signals, on the data in signals.js.
   Runs inside its own function. It takes the names it uses from run.js with ExtraEast.take and hands back its own with
   ExtraEast.give (see run.js, GIVES). */
(function(){
"use strict";
const X=window.ExtraEast;
const {fmt,randSetup,rnd,pick,shuffle,STATIONS,LAST,state,addTime,renderMap,leg,finish,push,next,log,ask,
  info}=X.take("run-signals.js",["fmt","randSetup","rnd","pick","shuffle","STATIONS","LAST","state","addTime",
  "renderMap","leg","finish","push","next","log","ask","info"]);
/* ---------- the signals runs: speed semaphores (Standard Code 281-292) or route signals (Signals guide) ---------- */
/* Signal data and drawings come from signals.js, shared with the study deck. A question drawn at a signal carries gen:
   the answer key lists those from the tables in signals.js instead of reading each call. */
const byRule=Object.fromEntries(ASPECTS.map(a=>[a.r,a]));
/* Minutes each indication costs against a clear run: slowing for medium or slow speed, stopping, restricted speed. */
const RDELAY={"281":0,"281A":1,"281B":1,"281C":2,"282":2,"282A":1,"283":2,"283A":2,"283B":3,"284":3,"285":3,"286":3,
  "287":4,"288":4,"289":5,"290":5,"291":6,"292":0};
const ROUTE_DELAY={clear:0,approach:3,dclear:2,dapproach:3,stop:0,stop2:0};
const PLATE_DELAY={A:6,none:6,num:4,G:2,SA:6,P:8};
const figBox=svg=>`<div class="xw-fig">${svg}</div>`;
/* A signal on the road. sys "speed": a Standard Code aspect by rule; "route": a ROUTE entry by key. plate: a PLATES key or "". */
function sigAsk(sys,id,plate,where,lead){
  if(sys==="speed"){
    const a=byRule[id];
    if(!a)throw new Error("signals run: no Standard Code rule "+id);
    return ask({sec:"sig",src:"SC · Rule "+a.r,gen:"speed",where,title:"Signal ahead",
      body:`${lead} What does it indicate?`,extra:figBox(sigFig(a.arms)),
      right:a.ind,wrong:a.w.map(r=>[byRule[r].ind]),why:`Rule ${a.r}, ${a.name}: ${a.ind}.`,
      after:()=>{
        addTime(RDELAY[a.r]);
        state.parAdd+=RDELAY[a.r];
        state.passed.push(`Rule ${a.r} ${a.name}`);
      }});
  }
  const r=ROUTE.find(x=>x.k===id);
  if(!r)throw new Error("signals run: no route indication "+id);
  const others=[...new Set(ROUTE.map(x=>x.ind))].filter(t=>t!==r.ind);
  const d=ROUTE_DELAY[r.k];
  return ask({sec:"sig",src:"SG · Signal chart",gen:"route",where,title:"Signal ahead",
    body:`${lead} What does it tell you?`,extra:figBox(lightFig(r.heads,plate&&plate!=="none"?plate:"")),
    right:r.ind,wrong:shuffle(others).slice(0,3).map(t=>[t]),why:routeWhy(r),
    after:()=>{
      addTime(d);
      state.parAdd+=d;
      state.passed.push(r.name);
    }});
}
/* What to do at a signal showing Stop, by its plate. Passing an absolute signal without permission ends the run. */
function plateAsk(sys,plate,where,shown){
  const P=PLATES[plate];
  if(!P)throw new Error("signals run: no plate "+plate);
  const wrong=shuffle(plateWrongs(plate)).slice(0,3)
    .map(w=>w.ends?[w.t,{end:true,endText:"You passed a signal at Stop without permission."}]:[w.t]);
  const d=PLATE_DELAY[plate];
  return ask({sec:"sig",src:"SG · Signal signage",gen:"plate",where,title:P.name+" at Stop",
    body:`The signal shows Stop and carries ${P.with}. What do you do?`,
    extra:figBox(sys==="speed"?sigFig(shown,plate==="none"?"":plate):lightFig(shown,plate==="none"?"":plate)),
    right:P.act,wrong,why:P.note,
    after:()=>{
      addTime(d);
      state.parAdd+=d;
    }});
}

/* The words that lead into a signal question, shared by the stories and the set pieces. */
const leadNext="The next block signal shows this aspect.";
const leadAfter="The signal after it shows this aspect.";
const marked="The signal after it, marked as a Stop and proceed signal, shows this aspect.";
const distant="Approaching Granite, the distant signal for the interlocking shows this aspect.";
const home="The Granite home signal, lined into the siding, shows this aspect.";
/* Ordinary legs in block signal territory draw one of these stories (pickStories in signals.js); the set pieces
   (a train ahead, the P and G plates, Granite, CP Hollis, Hollis) keep theirs, keyed the same way. sig(id, plate,
   where, lead) asks at one signal; meets collects the stations where the train takes the siding for an opposing
   train. */
function stories(sp,sys,sig,meets){
  if(sp){
    return {
      clear:(i,w)=>[sig("281","",w,leadNext)],
      ahead2:(i,w)=>[sig("282A","",w,leadNext),sig("285","",w,leadAfter)],
      ahead1:(i,w)=>[sig("285","",w,leadNext),sig("291","",w,marked)],
      restrict:(i,w)=>[sig("290","",w,leadNext)]
    };
  }
  return {
    clear:(i,w)=>[sig("clear","",w,leadNext)],
    approach:(i,w)=>[sig("approach","",w,leadNext),sig("clear","",w,leadAfter)],
    stopnum:(i,w)=>[sig("approach","",w,leadNext),
      sig("stop","num",w,"The signal after it, with a number plate, shows this aspect."),plateAsk(sys,"num",w,"R")],
    meet:(i,w)=>{
      meets.add(i+1);
      return [sig("dapproach","",w,leadNext),
        sig("dclear","",w,`The signal at the ${STATIONS[i+1].n} siding switch, lined into the siding, shows this aspect.`)];
    }
  };
}
/* Speed run: the Standard Code's interlocking aspects, at Granite and the Hollis home signal, in the Code's own
   pairings (an approach aspect, then the route aspect), one sequence drawn per run. */
function graniteIn(sig){
  return [
    w=>[sig("282","",w,distant),sig("283","",w,home)],
    w=>[sig("281A","",w,"Two signals before Granite, the block signal shows this aspect."),sig("282","",w,distant),
      sig("283","",w,home)],
    w=>[sig("281B","",w,distant),sig("281C","",w,home)],
    w=>[sig("284","",w,distant),sig("287","",w,home)],
    w=>[sig("282","",w,distant),
      sig("283B","",w,"The Granite home signal, lined through the interlocking toward the siding, shows this aspect."),
      sig("287","",w,"At the siding switch, the next signal shows this aspect.")]];
}
const GRANITE_OUT=["287","283","281C"]; // what the operator clears the home signal to after the stop
function hollis(sig){
  return [
    {key:"restrict",
      ev:w=>[sig("290","",w,"Entering double track at Hollis behind the Ironton local, the home signal shows this aspect.")]},
    {key:"hollisA",
      ev:w=>[sig("283A","",w,"At Hollis, lined onto Main 1 with the Ironton local two signals ahead, the home signal shows this aspect."),
        sig("285","",w,leadAfter),sig("291","",w,marked)]},
    {key:"hollisM",
      ev:w=>[sig("286","",w,"At Hollis, lined onto Main 1 with the Ironton local one signal ahead, the home signal shows this aspect."),
        sig("291","",w,marked)]},
    {key:"hollisS",
      ev:w=>[sig("288","",w,"At Hollis, lined through the crossover onto Main 1, the home signal shows this aspect."),
        sig("291","",w,marked)]}];
}
/* Stories that show the same signals count as repeats: the Hollis home sequences end in a marked 291 or open with
   285, as ahead1 and ahead2 do, and Restricting matches the Hollis 290. */
const CLASH={hollisA:["ahead1","ahead2"],hollisM:["ahead1","restrict"],hollisS:["ahead1","restrict"]};
const clash=(a,b)=>a===b||(CLASH[a]||[]).includes(b)||(CLASH[b]||[]).includes(a);
/* Speed run: Cobb to Dunmore (leg 2) is manual block. */
const MB=2;

/* The run's draws: a train ahead from leg f (the signals step down, then clear as it moves on), the Granite meet or
   hold, the speed run's interlocking sequences, and the story of each leg. The order of the random calls is the
   game's: changing it changes every seeded run. */
function drawPlan(sys){
  const sp=sys==="speed";
  const sig=(id,plate,where,lead)=>sigAsk(sys,id,plate,where,lead);
  const ahead=randSetup()<.6,f0=rnd(0,2);
  // Speed run: the train ahead always runs on the two legs before the Cobb manual block and then goes into it.
  const f=sp?0:f0;
  const meet=randSetup()<.5; // at Granite: lined into the siding for a meet, or held at the home signal
  const meets=new Set(); // stations where the train takes the siding for an opposing train
  const RS=Math.random;
  const STORY=stories(sp,sys,sig,meets);
  const RI=Math.random;
  // speed run only
  const gIn=sp?pick(graniteIn(sig),RI):null,gOut=sp?pick(GRANITE_OUT,RI):null,hol=sp?pick(hollis(sig),RI):null;
  /* The operator's block signal at Cobb shows Permissive (289) when a train is in the block (always when the train
     ahead, two legs in front, has gone on into it) and Clear otherwise. */
  const mbDraw=RI()<.5;
  const fixedKey=i=>{
    if(sp&&i===MB)return "manual";
    if(ahead&&i===f)return sp?"ahead2":"clear";
    if(ahead&&i===f+1)return sp?"ahead1":"stopnum";
    if(i===4)return "pplate";
    if(i===5)return "granite";
    if(i===6&&!sp)return "cp";
    if(i===7&&sp)return hol.key;
    return null;
  };
  const legStories=pickStories([...Array(LAST)].map((_,i)=>fixedKey(i)),
    i=>Object.keys(STORY).filter(k=>k!=="meet"||(!meet&&STATIONS[i+1].sd&&i+1<LAST)),["meet"],RS,clash);
  // a train shown ahead on the leg before is in the block
  const mbOccupied=sp&&(ahead||["ahead1","ahead2"].includes(legStories[MB-1])||mbDraw);
  return {sys,sp,sig,ahead,f,meet,meets,STORY,gIn,gOut,hol,legStories,mbOccupied};
}

/* The signals on leg i, from station i to i+1. */
function legEvents(plan,i){
  const {sys,sp,sig,ahead,f,STORY,hol,legStories,mbOccupied}=plan;
  const w=STATIONS[i].n+" to "+STATIONS[i+1].n;
  if(sp&&i===MB){
    return [sig(mbOccupied?"289":"281","",w,
      `${STATIONS[MB].n} to ${STATIONS[MB+1].n} is manual block. At ${STATIONS[MB].n} the operator's `+
        `block signal${mbOccupied?", with the marking that designates it,":""} shows this aspect.`)];
  }
  if(ahead&&i===f){
    return [sp?sig("282A","",w,"The next block signal shows this aspect."):
      sig("clear","",w,"The next block signal shows this aspect.")];
  }
  if(ahead&&i===f+1){
    const ev=[sp?sig("285","",w,"The next signal shows this aspect."):sig("approach","",w,"The next signal shows this aspect.")];
    if(sp)ev.push(sig("291","",w,marked));
    else{
      ev.push(sig("stop","num",w,"The signal after it, with a number plate, shows this aspect."));
      ev.push(plateAsk(sys,"num",w,"R"));
    }
    return ev;
  }
  // RRR: Stop (292); RR would read as Stop and proceed (291)
  if(i===4)return [plateAsk(sys,"P",w,sp?"RRR":"R")];
  if(i===5)return granite(plan,w);
  if(i===6&&!sp){
    return [sig("stop2","A",w,"At CP Hollis, where double track begins, the signal with an A plate shows this aspect."),
      plateAsk(sys,"A",w,"RR"),
      sig("dclear","",w,"The control operator lines you onto Main 1 and the signal shows this aspect.")];
  }
  if(i===7&&sp)return hol.ev(w);
  return STORY[legStories[i]](i,w);
}
/* Leg 5, into Granite: the G plate, then the meet in the siding or the stop at the home signal with an SA plate. */
function granite({sys,sp,sig,meet,meets,gIn,gOut},w){
  const ev=[plateAsk(sys,"G",w,sp?"RRR":"R")];
  if(meet){
    if(sp)ev.push(...gIn(w));
    else ev.push(sig("dapproach","",w,"Approaching Granite, the signal shows this aspect."),sig("dclear","",w,home));
    meets.add(6); // after the leg the train is in the Granite siding while the opposing train passes
    return ev;
  }
  ev.push(sp?sig("285","",w,"Approaching Granite, the distant signal shows this aspect."):
    sig("approach","",w,"Approaching Granite, the signal shows this aspect."));
  ev.push(sp?sig("292","",w,"The Granite home signal, with an SA plate, shows this aspect."):
    sig("stop2","SA",w,"The Granite home signal, with an SA plate, shows this aspect."));
  ev.push(plateAsk(sys,"SA",w,sp?"RRR":"RR"));
  ev.push(sp?sig(gOut,"",w,"The operator clears the home signal to this aspect."):
    sig("clear","",w,"The operator clears the home signal to this aspect."));
  return ev;
}

/* The fixed questions from the deck on the speed run, added to the leg events. */
function speedDeckAsks(legEv){
  legEv[0].unshift(ask({sec:"sig",src:"SC · Fixed Signals",where:"Ashby",title:"How a signal speaks",
    body:"The road foreman asks how the Standard Code says a fixed signal can show its aspect.",
    right:"By position of semaphore arms, color of lights, position of lights, flashing of lights, or a "+
      "combination of these",
    wrong:[["By the position of semaphore arms only"],["By color of lights only, day and night"],
      ["By a sign giving the speed in miles per hour"]],
    why:"Standard Code, Fixed Signals: aspects may be shown by position of semaphore arms, color of lights, "+
      "position of lights, flashing of lights, or a combination of color, position and flashing."}));
  legEv[1].push(ask({sec:"sup",src:"SC · Rule 251",title:"Signals and superiority",
    body:"The time-table names this track as governed by block signals for trains in the same direction. How "+
      "do you run with respect to No 2 ahead of you?",
    right:"By the block signal indications, which supersede the superiority of trains",
    wrong:[["By superiority: No 2 is first class"],["By train order only"],
      ["By the time-table times, keeping 5 minutes behind"]],
    why:"Rule 251: on designated tracks, trains run with reference to other trains in the same direction by "+
      "block signals, whose indications supersede the superiority of trains."}));
  legEv[3].push(ask({sec:"sem",src:"SM",title:"Arms up",
    body:"These semaphores raise their arms to show proceed. What kind are they?",
    right:"Upper quadrant: the blade rises from horizontal to 45° and 90°",
    wrong:[["Lower quadrant: the blade drops to show proceed"],["Single-position signals"],["Smashboard signals"]],
    why:"Semaphores guide: an upper-quadrant blade rises through 45° and 90°; a lower-quadrant blade drops "+
      "toward proceed, so it is not fail-safe."}));
  legEv[6].push(ask({sec:"sig",src:"SC · Rules 289, 291",title:"Stop, or Stop and proceed?",
    body:"Two signals ahead both show two horizontal red arms. What tells you whether one is Stop and "+
      "proceed (Rule 291) rather than Stop (Rule 292)?",
    right:"A letter plate, marker light, shape of arm, or a combination of these",
    wrong:[["The number of arms"],["The color of its lights only"],["Its height above the rail"]],
    why:"Rules 289 and 291: designate by a letter plate, a marker light, the shape of the arm, or a "+
      "combination of these. The Code draws Stop with three, two or one arms."}));
}
/* The fixed questions from the deck on the route run, added to the leg events. */
function routeDeckAsks(legEv){
  legEv[0].unshift(ask({sec:"sig",src:"SG · Definitions",where:"Ashby",title:"Route or speed?",
    body:"These signals tell you which route you are lined for and how clear the blocks are ahead; diverging "+
      "speeds come from the timetable. What system is that?",right:"Route signaling",
    wrong:[["Speed signaling"],["Cab signaling"],["Absolute permissive block"]],
    why:"Signals guide: route signaling tells you the route and the state of the blocks ahead; speed "+
      "through diverging routes is in the timetable. Speed signaling tells you how fast to go."}));
  legEv[1].push(ask({sec:"gcor",src:"GC · 1.47C",title:"Calling the signal",
    body:"The engineer calls the next signal Approach; you see Clear. How is it treated?",
    right:"As the most restrictive indication observed: Approach",
    wrong:[["As Clear, since the conductor supervises the train"],["As whichever the engineer called"],
      ["As Stop until the dispatcher confirms it"]],
    why:"GCOR 1.47C: if crew members disagree on the indication, treat it as the most restrictive one observed."}));
  legEv[3].push(ask({sec:"sig",src:"SG · Definitions",title:"Opposing signals",
    body:"Past the head block signal at Dunmore, every opposing signal goes to Stop through to the head "+
      "block at the next siding. What system is that?",right:"APB, Absolute Permissive Block",
    wrong:[["ABS, Automatic Block Signals, with no opposing rule"],["CTC, set by a dispatcher"],
      ["An interlocking, worked from a tower"]],
    why:"Signals guide: under APB, when a train passes a head block, all opposing signals are set to stop "+
      "up to and including the head block at the next siding."}));
  legEv[6].push(ask({sec:"sig",src:"SG · Signal placement",title:"Where the CP signals stand",
    body:"At CP Hollis, where is the facing point signal?",right:"Just clear of the switch points",
    wrong:[["At the clearance point"],["Opposite the next intermediate signal"],["On a dwarf beside the siding"]],
    why:"Signals guide, typical signal placement in CTC: the facing point signal is just clear of the "+
      "switch points; trailing point signals are at the clearance point; a dwarf is often used on the siding."}));
}

/* Queues the run: the briefing at Ashby, each leg with its signals, the meets in a siding, and the finish. */
function pushRun({sp,sig,meets},legEv){
  push(info("Ashby",sp?"Extra 812 East, Ashby, 6:00":"KV 812 East, Ashby, 6:00",
    sp?"<p>You are the conductor of Extra 812 East. Between Ashby and Ironton the line has automatic block "+
      "signals: upper-quadrant semaphores giving Standard Code speed indications. "+STATIONS[2].n+" to "+STATIONS[3].n+" is manual block, worked by the operators. Granite has an interlocking where the line crosses "+
      "another railroad, and double track starts at Hollis. Call each signal as it comes up.</p>":
      "<p>You are the conductor of KV 812 East on a signaled line with route signals. Granite has an "+
      "interlocking where the line crosses another railroad, and CP Hollis, where double track begins, is "+
      "worked by a control operator. Read each signal as it comes up.</p>","Begin"));
  for(let i=0;i<LAST;i++){
    push(leg(i,i+1,()=>legEv[i]));
    if(meets.has(i+1))pushMeet(sp,sig,STATIONS[i+1].n);
  }
  push(()=>{
    state.par=state.start+state.tt.leg.reduce((a,b)=>a+b,0)+state.parAdd;
    finish((sp?"Extra 812 East":"KV 812 East")+" is in at Ironton at "+fmt(state.clock)+".",false);
  });
}
/* The meet in the siding at `at`: the wait while the opposing train passes, then the way back onto the main. */
function pushMeet(sp,sig,at){
  push(()=>{
    state.inSiding=true;
    addTime(8);
    state.parAdd+=8;
    log("In the "+at+" siding for the meet");
    renderMap();
    next();
  },
  info(at,"The meet at "+at,`<p>${sp?"Extra 812 East":"KV 812 East"} waits in the ${at} siding while `+
    `${sp?"Extra 530 West":"KV 530 West"} passes on the `+
    `main.${at==="Granite"?` The ${sp?"operator":"interlocking operator"} lines you back out onto the main.`:""}</p>`));
  // out of a siding other than Granite, the signal at the far switch lines the train back onto the main
  if(at!=="Granite")push(sig("dclear","",at,`Leaving the ${at} siding, the signal at the far switch shows this aspect.`));
}

/* A signals run: sys "speed" (Extra 812 East under the Standard Code) or "route" (KV 812 East under the Signals
   guide). */
function startSIG(sys){
  state.tt={leg:[]};
  for(let i=0;i<LAST;i++)state.tt.leg[i]=Math.round((STATIONS[i+1].mp-STATIONS[i].mp)*2.4)+rnd(-1,1);
  state.sys=sys;
  state.parAdd=0;
  state.passed=[];
  state.inSiding=false;
  const plan=drawPlan(sys);
  const legEv=[];
  for(let i=0;i<LAST;i++)legEv[i]=legEvents(plan,i);
  if(plan.sp)speedDeckAsks(legEv);
  else routeDeckAsks(legEv);
  pushRun(plan,legEv);
  next();
}
X.give("run-signals.js",{startSIG});
})();
