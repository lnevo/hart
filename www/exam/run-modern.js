/* Extra East: the modern run under track warrants: the warrant form, the run and its road events.
   Runs inside its own function. It takes the names it uses from run.js with ExtraEast.take and hands back its own with
   ExtraEast.give (see run.js, GIVES). The form's boxes and the dispatcher's words come from js/track-warrant.js, which
   run.html loads first. */
(function(){
"use strict";
const X=window.ExtraEast;
const {fmt,$,esc,reduced,randSetup,rnd,STATIONS,LAST,state,addTime,renderMap,renderStatus,leg,drawRoad,
  finish,push,front,next,log,scene,ask,info}=X.take("run-modern.js",["fmt","$","esc","reduced","randSetup","rnd",
  "STATIONS","LAST","state","addTime","renderMap","renderStatus","leg","drawRoad","finish","push","front",
  "next","log","scene","ask","info"]);
/* ---------- modern: track warrant control ---------- */
/* The choices in the form's blanks: stations, tracks, warrant numbers, trains, times, speeds and the "other specific
   instructions". time grows by the Box 5 time when the crew calls (setBox5). */
const TW_SEL={s:STATIONS.map(x=>x.n),t:["Main","Main 1","Main 2"],w:["101","102","103","104"],
  train:["2211 West","640 East","844 East"],time:["6:15","6:20","6:25","7:00","8:00","9:00"],mph:["10","20","30","40"],
  txt:["Joint with work train 292 between Birchwood and Cobb","Joint with 640 East between Hollis and Ironton",
    "Joint with 2211 West between Dunmore and Elk Gap"]};
/* The form's boxes, the dispatcher's words, the blank form and the copy check: www/js/track-warrant.js. */
const {BOXES,SAY,formHtml,compare:wrongBoxes}=window.TrackWarrant;
/* The run's three warrants: run-data.js TWC_PLAN, which the answer key reads too. */
const {TWC_PLAN}=window.ExtraEastData;


/* One warrant of TWC_PLAN for this run: its boxes, with each draw's box set chosen by drawn[name]. */
function drawWarrant(name,drawn){
  const plan=TWC_PLAN.warrants[name];
  const boxes={...plan.boxes};
  for(const [k,[yes,no]] of Object.entries(plan.draws||{})){
    if(typeof drawn[k]!=="boolean")throw new Error(`warrant ${plan.no}: the run has no draw ${k}`);
    Object.assign(boxes,drawn[k]?yes:no);
  }
  return {no:plan.no,at:plan.at,boxes};
}

/* The dispatcher's words for warrant w, a line at a time. Every box must have its values by now. */
function dispatcherLines(w){
  const nums=Object.keys(w.boxes).map(Number).sort((a,b)=>a-b);
  const unset=nums.filter(b=>!Array.isArray(w.boxes[b]));
  if(unset.length)throw new Error(`warrant ${w.no}: box ${unset.join(", ")} read out before it was filled`);
  return [`Track warrant number ${w.no.split("").join(" ")}, to KV 812 East at ${w.at}.`,
    ...nums.map(b=>`Box ${b}. ${SAY[b](w.boxes[b])}.`),"Dispatcher RK. Read it back."];
}
/* The form as the player filled it: {box: {on, v}}, on for the checkbox and v the blanks' values in order. */
function readForm(){
  return Object.fromEntries(BOXES.map(([n])=>[n,{on:$("c"+n).checked,
    v:[...$("row"+n).querySelectorAll("select")].map(s=>s.value)}]));
}

/* The copy scene: the dispatcher reads warrant w, the player fills the form and repeats it back. A wrong copy costs
   2 minutes and, the first time, a miss (GCOR 14.9); a right one puts the OK time on the warrant. */
function warrantCopy(w){
  return ()=>{
    state.attempts=0;
    const lines=dispatcherLines(w);
    scene(w.at,"Copy track warrant "+w.no,
      `<p>The dispatcher reads the warrant at copying speed. Check each box he gives and fill in its blanks, then repeat it back.</p><div class="xw-dict" id="dict"></div>
      <div class="xw-tw"><div class="hd">TRACK WARRANT No ${esc(w.no)} · ${new Date().toLocaleDateString("en-US",{month:"short",day:"numeric"})} 1997<br><span style="font-weight:400">To KV 812 East at ${esc(w.at)}</span></div>${formHtml(TW_SEL,esc)}<div class="okline">OK ____  Dispatcher ____</div></div>
      <div class="choices"><button class="xw-btn primary" id="rb">Repeat it to the dispatcher</button></div><div class="result" hidden></div>`);
    // read it out a line at a time
    const d=$("dict");
    let i=0;
    const tick=()=>{
      if(!d.isConnected)return;
      if(i<lines.length){
        d.textContent+=(i?"\n":"")+lines[i++];
        if(!reduced)setTimeout(tick,650);
        else tick();
      }
    };
    tick();
    $("rb").onclick=()=>{
      const bad=wrongBoxes(w,readForm());
      BOXES.forEach(([n])=>{
        const row=$("row"+n);
        row.classList.remove("bad");
        if(bad.includes(n))row.classList.add("bad");
      });
      const r=document.querySelector("#xwScene .result");
      r.hidden=false;
      if(bad.length)copiedWrong(w,bad,r);
      else copiedRight(w,r);
    };
  };
}
function copiedWrong(w,bad,r){
  state.attempts++;
  addTime(2);
  renderStatus();
  r.innerHTML=`<div class="verdict no">“That's not what I gave you.” <small `+
    `style="font-size:14px;font-family:var(--mono)">+2 min</small></div><p>The dispatcher corrects `+
    `box${bad.length>1?"es":""} ${bad.join(", ")}. Fix the shaded rows and repeat it again.</p>`+(state.attempts>=2?`<p class="src">The dispatcher's words are in the blue panel above. Each box he names is checked, `+
      `with its blanks in the order he reads them.</p>`:"");
  log("Warrant "+w.no+" read back with errors in "+bad.join(", "));
  if(state.attempts===1)state.misses.push({title:"Copying track warrant "+w.no,
    why:"GCOR 14.9: the employee writes all the information and repeats it, preprinted and written words, "+
      "to the dispatcher, who checks it before giving the OK.",src:"GC · 14.9",sec:"twc"});
}
function copiedRight(w,r){
  const ok=fmt(state.clock+1);
  w.ok=ok;
  document.querySelector(".xw-tw .okline").innerHTML=`OK <b>${ok}</b>  Dispatcher <b>RK</b>`;
  $("rb").disabled=true;
  r.innerHTML=`<div class="verdict ok">“That is correct. OK ${ok}, RK.”</div><div><button class="xw-btn primary" `+
    `id="xwGo">Continue</button></div>`;
  log("Warrant "+w.no+" OK "+ok);
  addTime(1);
  renderStatus();
  $("xwGo").onclick=()=>{
    $("xwGo").disabled=true;
    next();
  };
}

/* A stretch from station `from` to `to` (run.js leg): the events given, or one drawn from the road pool as the train
   leaves. */
function legTWC(from,to,events){
  return leg(from,to,()=>{
    if(events&&events.length)return events;
    const r=drawRoad();
    return r?[r]:[];
  });
}
/* The modern run: draws its warrants from TWC_PLAN and the wait for 2211 West, then queues the run a stretch at a
   time. */
function startTWC(){
  state.tt={leg:[]};
  for(let i=0;i<LAST;i++)state.tt.leg[i]=Math.round((STATIONS[i+1].mp-STATIONS[i].mp)*2.6)+rnd(-1,2);
  const box12=randSetup()<.6;
  const hold=randSetup()<.5;
  const w1=drawWarrant("w1",{box12}),w2=drawWarrant("w2",{hold}),w3=drawWarrant("w3",{});
  state.inSiding=false;
  const wait=rnd(10,18);
  TW_SEL.time=["6:15","6:20","6:25","7:00","8:00","9:00"];
  /* When the crew calls: Box 5 takes its time, the time list offers it, and the par time counts from it. */
  const setBox5=()=>{
    const t=Math.ceil((state.clock+TWC_PLAN.box5Lead)/5)*5;
    state.box5=t;
    w1.boxes[5]=[fmt(t)];
    if(!TW_SEL.time.includes(fmt(t)))TW_SEL.time.splice(2,0,fmt(t));
    state.par=t+state.tt.leg.reduce((a,b)=>a+b,0)+wait+3+8;
    next();
  };

  const run={w1,w2,w3,box12,hold,wait,setBox5};
  push(...ashby(run),...birchwoodToCobb(run),...dunmore(run),...granite(run),...ironton());
  next();
}
/* After the Box 5 question: a crew ready before the Box 5 time waits for it. */
function waitForBox5(){
  if(state.clock<state.box5){
    log("Waited for "+fmt(state.box5));
    state.clock=state.box5;
  }
}
/* Ashby: on duty, warrant 101 and its boxes, then out to Birchwood. */
function ashby({setBox5,w1}){
  return [
    info("Ashby","On duty at Ashby, 6:00",
      "<p>You are the conductor of KV 812 East, a freight from Ashby to Ironton through dark territory. "+
        "Train movements here are authorized by track warrant. Ashby and Ironton are inside yard limits. "+
        "Your train is on the main track inside the Ashby yard limits.</p>","Begin"),
    ask({sec:"yl",src:"GC · 6.13",title:"Moving up to the limit sign",
      body:"You pull up the main inside the Ashby yard limits toward the yard limit sign. There is no block "+
        "signal. At what speed?",right:"Restricted speed",
      wrong:[["Yard speed, unless the main is known to be clear"],["Maximum authorized speed"],["10 MPH"]],
      why:"GCOR 6.13: within yard limits, movements are made at restricted speed unless a block signal shows "+
        "something more favorable than Approach. “Yard speed unless known clear” is the Standard Code wording."}),
    ask({sec:"twc",src:"GC · 14.8",title:"Calling the dispatcher",
      body:"At the yard limit sign you call the dispatcher for a track warrant. What do you tell him?",
      right:"What movements you will make and, when necessary, which tracks and how much time you need",
      wrong:[["Your train's tonnage and car count"],["Only your train symbol; he works out the rest"],
        ["The OK time you would like"]],
      why:"GCOR 14.8: tell the dispatcher what movements will be made and, when necessary, which tracks and "+
        "how much time is required."}),
    setBox5,
    warrantCopy(w1),
    ask({sec:"twc",src:"GC · 14.9",title:"The OK time",
      body:"The dispatcher has given the OK time and his initials. What do you do now?",
      right:"Write the OK time and initials on the warrant and repeat them",
      wrong:[["Tell the engineer to go; the warrant is good",
        {end:true,endText:"You left before the OK time and initials were on the warrant and repeated back."}],
        ["Wait for a written copy at the next station"],["Read the box numbers back again"]],
      why:"GCOR 14.9 step 4: the employee writes the OK time and initials and repeats them. A warrant is not "+
        "in effect until the OK time is shown on it."}),
    ask({sec:"twc",src:"GC · 14.9",title:"Copies",body:"Who must have a copy of warrant 101?",
      right:"The conductor and the engineer, each copy dated",
      wrong:[["Only you, the conductor"],["Only the engineer, who runs the train"],
        ["The dispatcher keeps the only copy"]],
      why:"GCOR 14.9: the conductor and the engineer each have a copy, every crew member must read and "+
        "understand it, and the copy shows the date."}),
    ask({sec:"twc",src:"GC · 14.0 form",ref:"w101",title:"Box 5",
      get body(){return `Warrant 101 has its OK time, and Box 5 reads “Not in effect until ${fmt(state.box5)}.” It is ${fmt(state.clock)}. May you leave now?`},
      get right(){return `No; wait until ${fmt(state.box5)}, when the warrant takes effect`},
      get wrong(){return [["Yes; the OK time puts it in effect",
        {end:true,
          endText:`You took the main before ${fmt(state.box5)}. Box 5 kept warrant 101 out of effect until then.`}],
        [`Yes, at restricted speed until ${fmt(state.box5)}`],["Yes, if no train is in sight"]]},
      why:"Box 5: Not in effect until the time shown. Box 6 is the other timing box: This authority expires "+
        "at the time shown.",
      after:waitForBox5}),
    ask({sec:"twc",src:"GC · 14.0 form",title:"Box 15",
      body:"Box 15 is checked on warrant 101: “Flag protection not required against following trains on the "+
        "same track.” What does that tell you?",
      right:"The dispatcher protects your rear: you need not flag against following trains",
      wrong:[["You must flag against following trains"],["No other train is on the subdivision"],
        ["You may back up without permission"]],
      why:"Box 15: flag protection not required against following trains on the same track. The TWC guide "+
        "says a model railroad can drop it, along with Boxes 5, 6 and 12 to 14."}),
    legTWC(0,1)
  ];
}
/* Birchwood to Cobb, under Box 12 (men or equipment) or Boxes 11 and 17 (joint with work train 292). */
function birchwoodToCobb({box12}){
  return [
    legTWC(1,2,
      box12?[ask({sec:"sig",src:"GC · 5.8.2",where:"Birchwood to Cobb",title:"Men on the track",
        body:"Box 12 is in your warrant. Rounding a curve you see a track gang ahead at Cobb. What whistle signal?",
        right:"— o, then o o at intervals until the head end has passed them",
        wrong:[["A succession of short sounds"],["— — o —"],["None; Box 12 replaces the whistle"]],
        why:"GCOR 5.8.2 (8): — o approaching men or equipment, regardless of whistle prohibitions; then o o "+
          "intermittently until the head end has passed. It cannot be replaced by radio."}),
        ask({sec:"gcor",src:"GC · 6.27",where:"Birchwood to Cobb",title:"How long at restricted speed?",
          body:"Box 12 puts you at restricted speed between Birchwood and Cobb. When may you resume speed?",
          right:"When the leading wheels pass the end of the restriction",
          wrong:[["When the rear car passes the end"],["When you see a clear signal"],
            ["When the foreman waves you by"]],
          why:"GCOR 6.27: restricted speed applies until the leading wheels pass the point where it is no longer "+
            "required. Not over 20 MPH, able to stop within half the range of vision."})]:[ask({sec:"twc",
        src:"GC · 14.0 form",where:"Birchwood to Cobb",title:"Joint with work train 292",
        body:"Boxes 11 and 17 say you are joint with work train 292 between Birchwood and Cobb. How do you run there?",
        right:"At restricted speed: the limits are occupied by a train",
        wrong:[["At maximum authorized speed; 292 will stay clear"],["Not over 30 MPH"],
          ["Stop and wait for 292 to report clear"]],
        why:"Box 11: between the points, make all movements at restricted speed; limits occupied by train. Box "+
          "17 carries other instructions such as “joint with”. GCOR 6.27: not over 20 MPH, able to stop within "+
          "half the range of vision."})])
  ];
}
/* Cobb to Dunmore: the end of warrant 101, into the siding, warrant 102 and the meet with 2211 West. */
function dunmore({w2,wait}){
  return [
    ask({sec:"gcor",src:"GC · 1.47A",where:"Cobb",title:"Approaching your limit",
      body:"Dunmore is the end of your authority. When must you remind the engineer of it?",
      right:"After passing the last station before it, and at least 2 miles before it",
      wrong:[["When the Dunmore station sign comes into view"],["Only if he asks"],["One mile before it"]],
      why:"GCOR 1.47A: the conductor reminds the engineer when approaching the limits of authority after "+
        "passing the last station, but at least 2 miles before."}),
    legTWC(2,3),
    ask({sec:"twc",src:"GC · 14.2",where:"Dunmore",title:"Where does warrant 101 end?",
      body:"Dunmore is the last named point, and Box 10 tells you to clear the main track there. Where does "+
        "your authority end?",extra:"",right:"At the first siding switch at Dunmore, including it",
      wrong:[["At the Dunmore station sign"],
        ["At the last siding switch at Dunmore",
          {end:true,
            endText:"You ran past the first siding switch at Dunmore, out of your limits, toward the switch 2211 West would use."}],
        ["At the next station, Elk Gap",{end:true,endText:"You ran past the end of your authority at Dunmore."}]],
      why:"GCOR 14.2: at the last named point, authority extends to and includes the first siding switch. "+
        "First is last and last is first. GCOR 14.3: never foul a switch at either end where an opposing "+
        "train may use it to clear."}),
    ask({sec:"twc",src:"TW · Selected rules",where:"Dunmore",title:"Into the siding",
      body:"You head into the siding at Dunmore. The warrant does not govern the siding. How fast may you move in it?",
      right:"At a speed that lets you stop within half the range of vision",
      wrong:[["Restricted speed under warrant 101"],["Maximum authorized speed"],["Yard speed"]],
      why:"Track warrants govern only the main track. In sidings and other tracks, move at a speed that lets "+
        "you stop within half the range of vision short of any obstruction or improperly lined switch (GCOR 6.28)."}),
    ask({sec:"twc",src:"TW · Selected rules",where:"Dunmore",title:"Reporting clear",
      body:"The engine is in the siding at Dunmore. When can you report clear of warrant 101's limits?",
      right:"When the whole train is off the main and the switch is lined back to normal",
      wrong:[["Now; the engine is clear"],["When the engine passes the clearance point"],
        ["When 2211 West is in sight"]],
      why:"Clear of the limits means the whole train, not just the engine, clear of the limits and off the "+
        "main track, with switches restored to normal (except within yard limits)."}),
    ()=>{
      state.inSiding=true;
      renderMap();
      next();
    },
    warrantCopy(w2),
    ask({sec:"twc",src:"GC · 14.0 form",ref:"w102",where:"Dunmore",title:"Box 7",
      body:"Warrant 102 has its OK time. A headlight is coming: 2211 West is a mile out of Dunmore. May you "+
        "pull out of the siding?",right:"No. The warrant is not in effect until 2211 West has arrived at Dunmore",
      wrong:[["Yes; the OK time is on the warrant",
        {end:true,
          endText:"You took the main before 2211 West arrived at Dunmore. Box 7 kept warrant 102 out of effect."}],
        ["Yes, at restricted speed"],["Yes, after whistling — o"]],
      why:"Box 7: Not in effect until after arrival of the named train at the named point. Box 7 was used in "+
        "the worked example for 844 West waiting on 2211 East."}),
    ()=>{addTime(wait);
      log("2211 West arrives Dunmore");
      front(info("Dunmore","2211 West arrives",
        "<p>2211 West rolls past the siding and heads into the Dunmore house track, clear of the main. "+
          "Warrant 102 is now in effect.</p>"),
        ask({sec:"twc",src:"TW · Worked example",where:"Dunmore",title:"The other warrant",
          body:"2211 West has arrived at Dunmore, the end of its own warrant. What happens to that warrant now?",
          right:"2211 West reports clear of its limits, and the dispatcher voids its warrant",
          wrong:[["It stays in effect until midnight"],["It passes to your train with warrant 102"],
            ["Nothing; the dispatcher keeps it open for the return trip"]],
          why:"In the guide's worked example, 844 West's warrant is not in effect until after arrival of 2211 "+
            "East at Olga Yard. When 2211 East arrives, its warrant 701 is reported clear and voided. Here 2211 "+
            "West does the same at Dunmore. Unless a Box 6 time ends it sooner, a warrant stays in effect until "+
            "the crew releases it."}));
      next()},
    ()=>{
      state.inSiding=false;
      next();
    }
  ];
}
/* Dunmore to Granite through the Elk Gap tunnel, the end of warrant 102 (Box 8 or not), and warrant 103. */
function granite({w3,hold}){
  return [
    legTWC(3,4,
      [ask({sec:"gcor",src:"GC · 1.43",where:"Elk Gap",title:"Stalled in the tunnel",
        body:"Your engine slips down to a stop in the tunnel at Elk Gap and cannot move promptly. What first?",
        right:"Shut down the diesel, make a full service brake application, apply hand brakes and call the dispatcher",
        wrong:[["Keep the engine running for heat and wait",{min:13,marks:1}],
          ["Back out of the tunnel at once",{min:13,marks:1}],["Sound a succession of short sounds",{min:13,marks:1}]],
        why:"GCOR 1.43: shut down the diesel at once, make a full service brake application, apply hand brakes, "+
          "and the dispatcher should be notified immediately.",ok:{min:8}})]),
    legTWC(4,5),
    legTWC(5,6),
    hold?ask({sec:"twc",src:"GC · 14.2",where:"Granite",title:"The end of warrant 102",
      body:"Granite is your last named point and Box 8, Hold main track at last named point, is checked. Where "+
        "does your authority end?",right:"Short of the last siding switch at Granite, not including it",
      wrong:[["At the first siding switch, including it"],
        ["At the last siding switch, including it",
          {end:true,endText:"You fouled the far switch at Granite that an opposing train needed."}],
        ["At the Granite station sign"]],
      why:"Box 8 extends the limit past the near switch, to but not including the last siding switch, so you "+
        "hold the main while an opposing train uses the siding. GCOR 14.3: never foul that switch."})
      :ask({sec:"twc",src:"GC · 14.2",where:"Granite",title:"The end of warrant 102",
      body:"Granite is your last named point. Where does your authority end?",
      right:"At the first siding switch at Granite, including it",
      wrong:[["At the last siding switch at Granite, including it",
        {end:true,endText:"You ran past the first siding switch at Granite, out of your limits."}],
        ["At the Granite depot"],
        ["At the next station, Hollis",{end:true,endText:"You ran past the end of your authority at Granite."}]],
      why:"GCOR 14.2: at the last named point, authority extends to and includes the first siding switch. "+
        "First is last and last is first."}),
    hold?ask({sec:"twc",src:"GC · 14.3",where:"Granite",title:"The far switch",
      body:"Stopped at the end of warrant 102, the engineer asks whether he may pull ahead far enough to foul "+
        "the far siding switch at Granite. An opposing train may use that switch to clear the main. May he?",
      right:"No; a train must not foul a switch at either end of its limits where an opposing train may use it to clear",
      wrong:[["Yes, if he stops short of the station sign"],["Yes, at restricted speed"],
        ["Yes, if he whistles — o first"]],
      why:"GCOR 14.3: the train must not foul a switch at either end of its limits where an opposing train "+
        "may use that switch to clear the main track. Box 8 already stops your limit short of that switch."}):()=>next(),
    warrantCopy(w3),
    ask({sec:"twc",src:"GC · 14.0 form",where:"Granite",title:"Box 2 or Box 4?",
      body:"640 East, the Ironton local, is working the industries between Hollis and Ironton. Which box lets "+
        "it move both ways in its limits?",right:"Box 4, Work between",
      wrong:[["Box 2, Proceed from … to"],["Box 7, Not in effect until after arrival of"],
        ["Box 10, Clear main track at last named point"]],
      why:"Box 2 is one direction only; backing up needs permission for a reverse move. Box 4, Work between, "+
        "gives movement in both directions for locals and work trains."})
  ];
}
/* Granite to Ironton on double track, into the Ironton yard limits and yard. */
function ironton(){
  return [
    legTWC(6,7,
      [ask({sec:"twc",src:"GC · 14.0 form",where:"Granite to Hollis",title:"Box 13",
        body:"Warrant 103 has Box 13, “Do not exceed 40 MPH between Granite and Hollis.” The engineer has the "+
          "train up to 45 MPH on the tangent past Granite.",right:"Bring it down to 40 MPH or less",
        wrong:[["Hold 45; the limit starts at Hollis"],["Hold 45 until the next signal"],
          ["Drop to restricted speed"]],
        why:"Boxes 13 and 14 set a speed limit between the named points; Box 13 here covers Granite to Hollis."})]),
    legTWC(7,8,
      [ask({sec:"gcor",src:"GC · 6.25",where:"Hollis",title:"Main 2, against the current",
        body:"Box 3 sends you from Hollis to Ironton on Main 2, the westward main, because 640 East is working "+
          "on Main 1. Why does that move need your warrant?",
        right:"A move against the current of traffic must be authorized by track warrant or track bulletin",
        wrong:[["It does not; double track has no current of traffic outside CTC"],
          ["Only because Main 2 is a siding"],["The engineer may decide without authority at restricted speed"]],
        why:"GCOR 6.25: movement against the current of traffic must be authorized by track bulletin or track "+
          "warrant, except under yard limits, restricted limits, track permits, signal protection by lining a "+
          "switch in ABS, or DTC. Approach block and interlocking signals prepared to stop unless they show proceed."}),
        ask({sec:"def",src:"GC · Glossary",where:"Hollis to Ironton",title:"Current of traffic",
          body:"What is the current of traffic on this double track?",
          right:"The direction trains move on each main as the rules specify: eastward on Main 1, westward on Main 2",
          wrong:[["Whichever way the last train went"],["The direction the dispatcher sets for each warrant"],
            ["The direction of the steepest grade"]],
          why:"GCOR: current of traffic is the movement of trains in one direction on a main track, as specified "+
            "by the rules. Double track is two mains with the current one way on one and the opposite way on the other."}),
        ask({sec:"twc",src:"GC · 14.0 form",where:"Hollis to Ironton",title:"Boxes 13 and 14",
          body:"Box 13 reads “Do not exceed 40 MPH between Granite and Hollis” and Box 14 “Do not exceed 30 MPH "+
            "between Hollis and Ironton.” What is your limit now, between Hollis and Ironton?",
          right:"30 MPH, from Box 14",
          wrong:[["40 MPH, from Box 13"],["The higher of the two, 40 MPH"],
            ["Restricted speed, since two limits apply"]],
          why:"Boxes 13 and 14 each limit speed between their own named points. Past Hollis, Box 14's 30 MPH applies."})]),
    ask({sec:"yl",src:"GC · 6.13",where:"Ironton yard limits",title:"Block signal at Ironton",
      body:"Inside Ironton yard limits a block signal shows Approach (yellow). At what speed may you move past it?",
      right:"Restricted speed",
      wrong:[["Prepared to stop at the next signal, at track speed"],["Yard speed"],
        ["Any speed, since you have a warrant"]],
      why:"GCOR 6.13: within yard limits, restricted speed unless the block signal indication is more "+
        "favorable than Approach. Approach is not."}),
    ask({sec:"gcor",src:"GC · 1.46",where:"Ironton",title:"Yarding the train",
      body:"The Ironton yardmaster is on duty and tells you which track to yard on. Whose instructions do you follow?",
      right:"The yardmaster's",wrong:[["The dispatcher's only"],["Your own, as conductor"],["The engineer's"]],
      why:"GCOR 1.46: where a yardmaster is on duty, train, engine and yard crews comply with the "+
        "yardmaster's instructions."}),
    ask({sec:"gcor",src:"GC · 6.28",where:"Ironton yard",title:"On the yard tracks",
      body:"You shove the train onto yard track 4, off the main and outside any block system, at a speed that "+
        "lets you stop within half the range of vision. Short of what must you be able to stop?",
      right:"A train, engine, car, men or equipment, a stop signal, a derail or a switch lined wrong",
      wrong:[["Only another train"],["Only the end of the track"],["Only men on the track"]],
      why:"GCOR 6.28: except on a main track or where a block system is in effect, move at a speed that "+
        "allows stopping within half the range of vision short of a train, engine, car, men or equipment, "+
        "stop signal, derail or improperly lined switch."}),
    ()=>finish("KV 812 East is yarded at Ironton at "+fmt(state.clock)+".",false)
  ];
}
const ROAD_TWC=[
  ()=>ask({sec:"sig",src:"GC · 5.8.2(7)",title:"Crossing at 40 MPH",
    body:"You are running at 40 MPH toward a public crossing. When does the engineer start the crossing whistle?",
    right:"At least 15 but not more than 20 seconds before the crossing",
    wrong:[["At the whistle sign, whatever the speed"],["A quarter mile before the crossing"],
      ["10 seconds before the crossing"]],
    why:"GCOR 5.8.2(7): at 45 MPH or less, start at least 15 but not more than 20 seconds before entering "+
      "the crossing. Over 45 MPH, start at or about the sign but not more than 1/4 mile before. The "+
      "pattern is — — o —, held until the engine occupies the crossing."}),
  ()=>ask({sec:"gcor",src:"GC · 5.6",title:"A fusee on the track",
    body:"A burning fusee lies between the rails of your track. Nobody is with it.",
    right:"Stop, then go on at restricted speed for 1 mile beyond it",
    wrong:[["Slow to 20 MPH and pass it"],["Ignore it; it is not a signal"],["Stop and wait for a flagman"]],
    why:"An unattended burning fusee: stop, then proceed at restricted speed for 1 mile beyond it. A fusee "+
      "beyond the first rail of an adjacent track does not apply to your track."}),
  ()=>ask({sec:"gcor",src:"GC · 1.47C",title:"Calling the signal",
    body:"Passing a distant signal, you call it Approach and the engineer calls it Clear. How is it treated?",
    right:"As the most restrictive indication observed: Approach",
    wrong:[["As the engineer calls it: Clear"],["As the conductor calls it"],["Stop and ask the dispatcher"]],
    why:"GCOR 1.47C: crew members call each signal as soon as it is visible, and if they disagree, it is "+
      "regarded as the most restrictive indication observed."}),
  ()=>ask({sec:"sig",src:"GC · 5.8.2",title:"Short blasts ahead",
    body:"From a train on the passing track ahead you hear a long succession of short whistle sounds.",
    right:"Stop until it is safe to proceed",
    wrong:[["Answer o o and continue"],["Continue at restricted speed"],["Sound the same signal back"]],
    why:"GCOR 5.8.2 (1): a succession of short sounds warns of persons or livestock on the track or an "+
      "emergency such as a derailment. Crews on other trains who hear it must stop until it is safe."}),
  ()=>ask({sec:"sig",src:"GC · 5.8.3",title:"The whistle fails",
    body:"The horn on the lead unit quits and no other unit can lead. How do you go on?",
    right:"With the bell ringing continuously, stopping before each public crossing unless the gates are down "+
      "or no traffic is near",
    wrong:[["Normally, with the headlight on bright"],["Not at all; wait for a rescue engine"],
      ["At restricted speed only"]],
    why:"GCOR 5.8.3: continue with the bell ringing and stop before each public crossing so a crew member "+
      "can warn traffic, unless the gates are fully down or no traffic is approaching or stopped."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"A sign with a D",
    body:"A signal ahead in dark territory carries a D on its mast. What is it?",
    right:"A distant signal, governing the approach to the signal or interlocking ahead",
    wrong:[["A dwarf signal for sidings"],["A detector signal you must inspect"],
      ["A signal you may pass at restricted speed without stopping"]],
    why:"A distant signal is outside a block system and governs the approach to a block signal, "+
      "interlocking signal or switch point indicator. It does not indicate track conditions between itself "+
      "and that signal. In the signals guide, a P plate marks a detector and a G plate a grade signal."}),
  ()=>ask({sec:"sig",src:"SG · Route indications",title:"Two heads at the junction",
    body:"The interlocking signal at the junction shows red over yellow.",
    right:"Diverging Approach: the OS block and the next block are unoccupied, but the block after that is occupied",
    wrong:[["Stop: there is red on the mast"],["Approach on the main route"],["Restricting"]],
    why:"It is not red unless it is all red. Red over yellow is Diverging Approach: the OS block and the "+
      "next block are unoccupied but the next block after that is occupied."}),
  ()=>ask({sec:"twc",src:"GC · 14.7",title:"Reporting clear by a hand switch",
    body:"You report clear of a warrant after leaving the main through a hand-operated switch, outside yard "+
      "limits. What must you tell the dispatcher?",right:"The position of the switch and that it is locked",
    wrong:[["Only that the train is clear"],["The time you passed the switch"],
      ["Nothing more; the switch is not his concern"]],
    why:"GCOR 14.7: outside yard or restricted limits, tell the dispatcher the switch position and that it "+
      "is locked when reporting clear. He repeats it and you confirm."}),
  ()=>ask({sec:"twc",src:"GC · 14.7",title:"No caboose",
    body:"There is no crew on the rear of KV 812 East. Which shows the dispatcher your whole train is clear "+
      "of the limits?",
    right:"A rear-end telemetry device, with air pressure on the head-end device showing brake pipe continuity",
    wrong:[["The engineer's word that the train felt complete"],["The time since you passed the last station"],
      ["The head end passing the clearance point"]],
    why:"GCOR 14.7 lists: a rear-end telemetry device with air pressure on the head-end device showing "+
      "brake pipe continuity, an employee verifying the marker, a crew member seeing the rear car with the "+
      "marker, an inspection while stopped, or matching axle counts from two detectors."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"A switch marked V",
    body:"You must trail through a switch whose bowl is painted yellow and marked V. What will it do after "+
      "your train passes?",right:"Stay where your wheels forced the points",
    wrong:[["Spring back to its original position"],["Lock in the reverse position"],
      ["Throw itself to normal after a delay"]],
    why:"A variable switch stays where the points were forced when trailed through. A spring switch returns "+
      "to its original position."}),
  ()=>ask({sec:"sig",src:"GC · 5.8.1",title:"Before moving",
    body:"You are ready to pull out of the siding at Hollis. What does the engineer do before moving?",
    right:"Ring the bell",
    wrong:[["Sound — — o —"],["Sound a succession of short sounds"],["Nothing; the radio call is enough"]],
    why:"GCOR 5.8.1: ring the bell before moving (except momentary stop-and-start switching), approaching "+
      "men or equipment, and approaching public crossings."}),
  ()=>ask({sec:"sig",src:"GC · 5.8.2(7)",title:"Crossing at 50 MPH",
    body:"On the tangent past Fenwick you are at 50 MPH, approaching a public crossing. When does the "+
      "crossing whistle start?",right:"At or about the crossing sign, but not more than 1/4 mile before the crossing",
    wrong:[["15 to 20 seconds before the crossing"],["Half a mile before the crossing"],
      ["When the crossing comes into view"]],
    why:"GCOR 5.8.2(7): over 45 MPH, start at or about the sign, but not more than 1/4 mile before. At 45 "+
      "MPH or less, start 15 to 20 seconds before."}),
  ()=>ask({sec:"gcor",src:"GC · 1.47B",title:"Special handling",
    body:"There are two loads of steel plate on the head end. Who checks whether any cars need special handling?",
    right:"The engineer checks with the conductor",
    wrong:[["The dispatcher tells the engineer"],["Nobody; it is on the waybills"],["The yardmaster at Ironton"]],
    why:"GCOR 1.47B: the engineer must check with the conductor whether any cars need special handling."}),
  ()=>ask({sec:"gcor",src:"GC · 1.47A",title:"Doubled up",
    body:"The dispatcher combines your train with 640 East at Hollis. Both have conductors. Who is in charge?",
    right:"The conductor with the most seniority",
    wrong:[["The conductor of the leading train"],["The engineer of the lead unit"],["The dispatcher names one"]],
    why:"GCOR 1.47A: if trains combine, the senior conductor takes charge."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"Into CTC",
    body:"Past Ironton the line enters CTC. What authorizes your movement there?",
    right:"Block signal indications, set by the control operator at control points",
    wrong:[["Your track warrant, extended to Ironton"],["The yardmaster's radio OK"],["Time-table superiority"]],
    why:"GCOR: CTC is a block system that uses block signal indications to authorize train movements. "+
      "Control points are absolute signals controlled by a control operator."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"DTC territory",
    body:"A neighboring subdivision runs under DTC. How is authority given there?",
    right:"The dispatcher authorizes occupancy of named blocks, marked by Begin and End block signs",
    wrong:[["By track warrant boxes"],["By block signal indications"],["By time-table and train order"]],
    why:"GCOR: in DTC the train dispatcher authorizes occupancy of a DTC block, a length of main track "+
      "named by wayside signs reading Begin and End block, and by milepost in the time-table."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"Interlocking limits",
    body:"You cross the other railroad at grade at Granite under an interlocking. Where do its limits run?",
    right:"Between the outer opposing absolute signals",
    wrong:[["Between the first and last switches"],["From the tower to the distant signal"],
      ["A quarter mile each side of the crossing"]],
    why:"GCOR: interlocking limits are the tracks between the outer opposing absolute signals of an interlocking."}),
  ()=>ask({sec:"twc",src:"TW · Selected rules",title:"Without a warrant",
    body:"A hi-rail truck asks on the radio whether it can run on the main without a warrant. Who may occupy "+
      "the main in TWC territory without one?",right:"Nobody, except within yard limits or restricted limits",
    wrong:[["Work extras"],["Anyone moving under 20 MPH"],["Passenger trains"]],
    why:"Outside yard (or restricted) limits, nobody occupies the main track in TWC territory without a "+
      "warrant (GCOR 14.1)."}),
  ()=>ask({sec:"twc",src:"TW · Selected rules",title:"How long it lasts",
    body:"Your warrant has no Box 6 time. How long does it stay in effect?",right:"Until you release it",
    wrong:[["Until the dispatcher's shift ends"],["Until midnight"],["Until you reach the last named point"]],
    why:"A track warrant stays in effect until the field employee releases it. Report clear of the limits "+
      "as soon as practicable."}),
  ()=>ask({sec:"twc",src:"TW · Defined",title:"What TWC is",
    body:"The engineer, new to this line, asks what track warrant control is.",
    right:"The dispatcher gives authority by voice; the crew copies it on a form, repeats it, and gets an OK time",
    wrong:[["Signals authorize each block"],["The time-table authorizes each train"],
      ["Operators hand up written orders at each station"]],
    why:"TWC authorizes trains, and men and equipment, across a specified territory. The dispatcher gives "+
      "verbal instructions; the field employee copies them on a form and repeats them; the dispatcher "+
      "gives an OK time."}),
  ()=>ask({sec:"twc",src:"GC · 14.0 form",title:"Box 9",
    body:"Another crew's warrant has Box 9 checked with your train's symbol. What does Box 9 say?",
    right:"Do not foul limits ahead of the named train",
    wrong:[["Clear main track at last named point"],["Not in effect until after arrival of the named train"],
      ["Joint with the named train"]],
    why:"Box 9: Do not foul limits ahead of __. Box 7 is Not in effect until after arrival of __ at __, and "+
      "Box 10 is Clear main track at last named point."}),
  ()=>ask({sec:"twc",src:"TW · Selected rules",title:"Model railroad warrants",
    body:"The fireman runs TWC at his club. Which boxes does the TWC guide say a model railroad can drop?",
    right:"Boxes 5 and 6 (times), 12 (men and equipment), 13 and 14 (speed) and 15",
    wrong:[["Boxes 2 and 3"],["Boxes 7 and 8"],["Box 17 only"]],
    why:"The TWC guide says a model railroad can drop Box 12, Boxes 5 and 6, Boxes 13 and 14, and Box 15. "+
      "The real line here uses them."}),
  ()=>ask({sec:"yl",src:"GC · 6.13",title:"Yard limits in CTC",
    body:"On the next subdivision, the yard limits lie in CTC territory. Who must authorize a move on the "+
      "main track there?",right:"The control operator",
    wrong:[["Nobody; yard limit rules apply"],["The yardmaster"],["The conductor of the first train there"]],
    why:"GCOR 6.13: in CTC territory the control operator must authorize any main track movement, even "+
      "within yard limits."}),
  ()=>ask({sec:"yl",src:"YL",title:"Why yard limits?",body:"The engineer asks why Ironton has yard limits at all.",
    right:"So crews can use short stretches of main track without the dispatcher issuing many fast-changing "+
      "orders or warrants",
    wrong:[["To allow higher speeds near the yard"],["To keep extras off the main"],
      ["To mark where warrants are delivered"]],
    why:"Yard Limits guide: many trains and engines need short stretches of main track, such as a yard "+
      "ladder joined to the main. Yard limits let them work without a stream of orders or warrants."}),
  ()=>ask({sec:"gcor",src:"GC · 1.44, 1.45",title:"Who directs whom",
    body:"The Ironton operator relays a lineup to you. Whose direction does the operator work under?",
    right:"The dispatcher's",wrong:[["The yardmaster's"],["The senior conductor's"],["Nobody's; operators work alone"]],
    why:"GCOR 1.44 and 1.45: dispatchers supervise train movement; control operators and operators work "+
      "under the dispatcher's direction for warrants, bulletins, lineups and train movements."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"Clearance point",
    body:"You leave the rear car in the siding at Hollis. Where must it stand?",
    right:"Clear of the clearance point, where a person riding the side of a car can pass equipment on the next track",
    wrong:[["Anywhere past the switch points"],["At the station sign"],["Within one car length of the switch"]],
    why:"GCOR: the clearance point is the location closest to a switch where it is safe for equipment, and "+
      "a person riding the side of equipment, to pass equipment on an adjacent track."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"A reverse move",
    body:"Your warrant says Proceed from Granite to Hollis, and you need to back up 200 feet. What is that "+
      "in GCOR terms?",right:"A reverse movement, opposite the authorized direction, which needs permission",
    wrong:[["A shove move, allowed under any warrant"],["Movement against the current of traffic"],
      ["A work move under Box 4"]],
    why:"GCOR: a reverse movement is a movement opposite the authorized direction. Box 2 is one direction "+
      "only; backing up needs permission."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"Yard or yard limits?",
    body:"Are the Ironton yard tracks and the Ironton yard limits the same thing?",
    right:"No: the yard is the tracks off the main; yard limits are a portion of main track",
    wrong:[["Yes, two names for the same tracks"],["No: yard limits are the yard tracks only"],
      ["Yes, when a yardmaster is on duty"]],
    why:"GCOR: a yard is a system of tracks other than main tracks and sidings. Yard limits are a portion "+
      "of main track designated by signs and time-table or bulletin."}),
  ()=>ask({sec:"def",src:"GC · Glossary",title:"What makes a train",
    body:"Your engine runs light from the yard to the main. Under the GCOR, when is it a train?",
    right:"When it displays a marker and is authorized to operate on a main track",
    wrong:[["Only when it has cars"],["Whenever it moves"],["Only with a full crew"]],
    why:"GCOR: a train is one or more engines coupled, with or without cars, displaying a marker, and "+
      "authorized to operate on a main track."})
];
X.give("run-modern.js",{startTWC,ROAD_TWC,
  warrantForm:{BOXES,SAY,wrongBoxes}}); // the form, its spoken lines and its check, for the exam test
})();
