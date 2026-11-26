/* Extra East: the Ironton yard job under GCOR: the yard sketch and the job's scenes.
   Runs inside its own function; the names it shares with run.js are on window.ExtraEast (see run.js). */
(function(){
"use strict";
const X=window.ExtraEast;
const {fmt,$,randSetup,rnd,pick,state,addTime,renderStatus,finish,renderSheet,esc,push,next,log,ask,info}=X;
/* ---------- the Ironton yard job (GCOR) ---------- */
/* Places on the yard sketch: x,y in the sketch's units, n = name shown in the status line. */
const YLOC={
  eng:{x:70,y:78,n:"engine track"},t4:{x:150,y:92,n:"yard track 4"},lead:{x:250,y:70,n:"yard lead"},
  m1:{x:340,y:44,n:"Main 1"},m2:{x:420,y:24,n:"Main 2"},feed:{x:480,y:8,n:"Kestrel Feed spur"},
  t2:{x:150,y:64,n:"yard track 2"},cp:{x:560,y:44,n:"CP Ironton East"}};
function renderYardMap(){
  const W=600,box=$("xwMap"),L=YLOC[state.yloc];
  const k=box.clientWidth&&box.clientWidth<560?1.7:1,fs=n=>(n*k).toFixed(1);
    // labels stay readable on phones, as on the line map
  let s=`<svg viewBox="0 0 ${W} 112" role="img" aria-label="Sketch of Ironton yard, job at ${esc(L.n)}">`;
  s+=`<rect x="36" y="2" width="560" height="104" fill="#e8dfc4"/><text x="592" y="102" `+
      `font-size="${fs(8.5)}" text-anchor="end" fill="#5d5a4e">YARD LIMITS</text>`;
  s+=`<line x1="20" y1="44" x2="${W-10}" y2="44" stroke="#1d2733" stroke-width="2.5"/><line x1="20" `+
      `y1="24" x2="${W-10}" y2="24" stroke="#1d2733" stroke-width="2.5"/>`;
  s+=`<text x="24" y="40" font-size="${fs(8)}" fill="#5d5a4e">MAIN 1 EAST</text><text x="24" y="20" `+
      `font-size="${fs(8)}" fill="#5d5a4e">MAIN 2 WEST</text>`;
  s+=`<path d="M300 44 L270 70 L110 70 M240 70 L215 64 L100 64 M230 70 L200 78 L40 78 M225 70 L190 92 `+
      `L100 92 M270 70 L250 84 L100 84" fill="none" stroke="#1d2733" stroke-width="1.6"/>`;
  s+=`<path d="M380 44 L400 24 M440 24 L470 8 L530 8" fill="none" stroke="#1d2733" stroke-width="1.6"/>`;
  s+=`<text x="96" y="62" font-size="${fs(7.5)}" text-anchor="end" fill="#5d5a4e">2</text><text x="96" `+
      `y="94" font-size="${fs(7.5)}" text-anchor="end" fill="#5d5a4e">${state.ytrack}</text><text x="36" `+
      `y="80" font-size="${fs(7.5)}" text-anchor="end" fill="#5d5a4e">eng</text><text x="534" y="10" `+
      `font-size="${fs(7.5)}" fill="#5d5a4e">FEED</text>`;
  s+=`<line x1="548" y1="14" x2="548" y2="54" stroke="#a3302b" stroke-width="1.5" stroke-dasharray="3 `+
      `2"/><text x="552" y="66" font-size="${fs(8)}" fill="#a3302b">CP · CTC →</text>`;
  s+=`<g transform="translate(${L.x} ${L.y})"><rect x="-13" y="-6" width="26" height="10" rx="2" `+
      `fill="#a3302b"/><text x="0" y="2" font-size="${fs(7.5)}" text-anchor="middle" fill="#fff" `+
      `font-weight="700">1502</text></g>`;
  box.innerHTML=s+`</svg>`;
}
/* Move the job to another place on the sketch, taking some minutes. */
const yMove=(to,min,note)=>()=>{state.yloc=to;addTime(min);state.parAdd+=min;if(note)log(note);renderStatus();next()};
  // par is the sum of the moves
const yDone=i=>()=>{state.jobs[i].done=true;renderSheet();next()};
function startYARD(){
  state.clock=state.start=420;state.tt={}; // the yard job starts at 7:00
  // the draw: which track to pull, how many cars, and the block signal at the lead
  state.ytrack=pick([3,4,5]);const cars=rnd(2,4),leadClear=randSetup()<.5;YLOC.t4.n="yard track "+state.ytrack;
  state.jobs=[{t:`Pull the ${cars} cars on track ${state.ytrack}`},{t:"Spot 2 loads at Kestrel Feed (spur off Main 2)"},
    {t:"Clear the main for the trains"},{t:"Set the cars on track 2, clear of the clearance point"},
    {t:"Take 2 empties to CP Ironton East for the eastward local"}];
  push(
    info("Ironton","On duty at Ironton, 7:00",
      "<p>You are the conductor of the Ironton yard job, engine KV 1502. Ironton yard limits cover both "+
        "main tracks: Main 1 eastward and Main 2 westward. The yardmaster is on duty and has given you the "+
        "work list on the right. East of CP Ironton East the line is CTC.</p>","Begin"),
    ask({sec:"gcor",src:"GC · 1.46",title:"Whose list?",
      body:"The yardmaster wants track 4 pulled first. The engineer would rather start with Kestrel Feed. "+
        "Whose instructions does the yard job follow?",
          right:"The yardmaster's: where a yardmaster is on duty, train, engine and yard crews follow the "+
        "yardmaster's instructions",
          wrong:[["The engineer's, who operates the engine"],["The conductor's alone, who supervises the job"],
          ["The train dispatcher's"]],
          why:"GCOR 1.46: the yardmaster directly supervises yard crews; where a yardmaster is on duty, train, "+
        "engine and yard crews follow the yardmaster's instructions."}),
    ask({sec:"sig",src:"GC · 5.8.2",title:"Car men on track 3",
      body:"Car men are working on track 3, next to the engine track. The engine is ready to move. What does "+
        "the engineer do first?",right:"Sound the required whistle signal before moving",
          wrong:[["Nothing; the engine track is not main track"],["Move at restricted speed without a signal"],
          ["Ask the train dispatcher for permission"]],
          why:"GCOR 5.8.2: when other employees are working in the immediate area, sound the required whistle "+
        "signal before moving."}),
    yMove("t4",8,`Coupled to the ${cars} cars on track ${state.ytrack}`),
    ask({sec:"gcor",src:"GC · 6.28",title:"Pulling the yard track",
      body:"You pull the cars out of the yard track onto the yard lead. These are yard tracks, off the main "+
        "and outside any block system. At what speed?",
          right:"A speed that allows stopping within half the range of vision",
          wrong:[["Restricted speed, not over 20 MPH, looking out for broken rail"],
          ["Yard speed, unless the track is known to be clear"],["Not over 10 MPH"]],
          why:"GCOR 6.28: except on a main track or where a block system is in effect, move at a speed that "+
        "allows stopping within half the range of vision short of a train, engine, car, men or equipment, "+
        "stop signal, or derail or switch lined improperly."}),
    ask({sec:"def",src:"GC · Glossary",title:"The spring switch",
      body:"The cut trails through the spring switch at the end of the yard track. After the last car has "+
        "passed, where are the points?",
          right:"Back in their original position: a spring returns them after they are trailed through",
          wrong:[["Where the wheels forced them, until someone lines them back"],["Locked in the reversed position"],
          ["Half open, until the next movement"]],
          why:"GCOR glossary: on a spring switch a spring returns the points to their original position after "+
        "they are trailed through. A variable switch, marked V or with a yellow bowl, leaves them where they "+
        "were forced."}),
    yDone(0),
    yMove("lead",4),
    leadClear?ask({sec:"yl",src:"GC · 6.13",title:"Onto Main 1",
      body:"From the lead you head out onto Main 1, inside the yard limits. The block signal at the lead shows "+
        "Clear. Must the move be made at restricted speed?",
          right:"No: the movement is under a block signal more favorable than Approach",
          wrong:[["Yes: every movement inside yard limits is at restricted speed"],
          ["Yes, until the job passes the east yard limit sign"],["No, but not over 10 MPH"]],
          why:"GCOR 6.13: within yard limits, all movements at restricted speed unless under a block signal more "+
        "favorable than Approach. Clear is more favorable."})
             :ask({sec:"yl",src:"GC · 6.13",title:"Onto Main 1",
               body:"From the lead you head out onto Main 1, inside the yard limits. The block signal at the lead shows "+
                 "Approach. Must the move be made at restricted speed?",
                   right:"Yes: only a signal better than Approach lifts restricted speed",
                   wrong:[["No: any block signal lifts the yard limit speed"],
                   ["No: Approach means the next block is clear, so track speed"],["Only if a yardmaster is on duty"]],
                   why:"GCOR 6.13: within yard limits, all movements at restricted speed unless under a block signal more "+
                 "favorable than Approach. An Approach does not lift it."}),
    yMove("m1",5,"On Main 1"),
    ask({sec:"yl",src:"GC · 6.13",title:"A train behind you",
      body:"While the job works on Main 1, the eastward passenger train comes around the curve behind you on "+
        "Main 1. What does the job do?",
          right:"Get out of the way: engines give way to trains as they approach and must not delay passenger trains",
          wrong:[["Keep working: inside yard limits nobody protects against anybody",
          {end:true,endText:"The job stayed on Main 1 and delayed the passenger train."}],
          ["Light a fusee so the train stops behind the cut",
          {end:true,endText:"The job stopped the passenger train with a fusee instead of getting out of its way."}],
          ["Ask the dispatcher for a track warrant to stay on Main 1"]],
          why:"GCOR 6.13: trains and engines may use the main track without protecting against other trains or "+
        "engines, but engines give way to trains as they approach and must not delay passenger trains.",
          after:ok=>{state.jobs[2].done=ok}}),
    ask({sec:"yl",src:"GC · 6.13",title:"Against the current",
      body:"The Kestrel Feed spur leaves Main 2, the westward main. To reach it, the job must run east on Main "+
        "2. What does that move need?",
          right:"Authorization or protection by track warrant, track bulletin, yardmaster or other authorized employee",
          wrong:[["Nothing: yard limits allow any move on the main track",
          {end:true,endText:"The job ran against the current of traffic on Main 2 without authority."}],
          ["Permission from the control operator at CP Ironton East"],["A flagman 1 mile ahead of the movement"]],
          why:"GCOR 6.13: within yard limits, movements against the current of traffic must not be made unless "+
        "authorized or protected by track warrant, track bulletin, yardmaster or other authorized employee. "+
        "Ironton's control operator governs only the CTC east of the CP."}),
    info("Ironton","The yardmaster's OK",
      "<p>The yardmaster protects the move and gives you Main 2 east to the Kestrel Feed spur.</p>"),
    ask({sec:"def",src:"GC · Glossary",title:"From Main 1 to Main 2",
      body:"You cross from Main 1 to Main 2 through two switches joined by a short track between the mains. "+
        "What is that connection?",right:"A crossover",
          wrong:[["A dual control switch"],["A controlled siding"],["A spring switch"]],
          why:"GCOR glossary: a crossover is a track connection between two adjacent tracks, consisting of two "+
        "switches, intended to be used primarily for crossing over from one track to the other."}),
    yMove("m2",4),
    ask({sec:"def",src:"GC · Glossary",title:"Working limits on the spur",
      body:"A track foreman has working limits on the Kestrel Feed spur while his men replace ties. How may "+
        "the job move inside those limits?",right:"Only as permitted by the employee in charge of the working limits",
          wrong:[["At restricted speed, not over 20 MPH"],["Freely: the spur is not main track"],
          ["Only with a track warrant from the dispatcher"]],
          why:"GCOR glossary: working limits are a segment of track within definite boundaries on which movements "+
        "may be made only as permitted by the employee in charge."}),
    yMove("feed",12,"2 loads spotted at Kestrel Feed"),
    yDone(1),
    yMove("m2",5),
    yMove("lead",6),
    ask({sec:"def",src:"GC · Glossary",title:"Clear on track 2",
      body:"You set the cars on track 2. Where must the last car stand?",
      right:"Clear of the clearance point: where it is safe for equipment, and a person riding the side of "+
        "equipment, to pass on the adjacent track",
          wrong:[["Just past the switch points"],["At least one car length from the switch"],
          ["Anywhere, as long as the switch is lined back"]],
          why:"GCOR glossary: the clearance point is the location closest to a switch where it is safe for "+
        "equipment, and a person riding the side of equipment, to pass equipment on an adjacent track."}),
    yMove("t2",6,"Cars set on track 2"),
    yDone(3),
    yMove("m1",6),
    ask({sec:"yl",src:"GC · 6.13",title:"Toward CP Ironton East",
      body:"The yardmaster sends the 2 empties east to CP Ironton East for the eastward local. Past the CP the "+
        "yard limits lie in CTC territory. Who must authorize the job's movement on the main track there?",
          right:"The control operator",
          wrong:[["The yardmaster"],
          ["No one: yard limits allow any main track movement",
          {end:true,endText:"The job moved into CTC territory without the control operator's authority."}],
          ["The conductor of the eastward local"]],
          why:"GCOR 6.13: where yard limits are in effect in CTC territory, the control operator must authorize "+
        "any movement on the main track."}),
    ask({sec:"def",src:"GC · Glossary",title:"The switch at the CP",
      body:"The switch at CP Ironton East is power-operated from the control operator's machine, but it also "+
        "has a hand lever. What is it?",right:"A dual control switch",
          wrong:[["A spring switch"],["A variable switch"],["An electric switch lock"]],
          why:"GCOR glossary: a dual control switch is a power-operated switch, moveable point frog, or derail "+
        "that can also be operated by hand."}),
    yMove("cp",7,"Empties left at CP Ironton East for the local"),
    yDone(4),
    ()=>{addTime(8);state.par=state.start+state.parAdd+8;log("Back to the engine track; tied up");
      finish("The Ironton yard job tied up at "+fmt(state.clock)+".",false)}
  );
  next();
}
Object.assign(X,{YLOC,renderYardMap,startYARD});
})();
