/* The 1981 PC&Y ore transfer of Extra East: HART Railroad, "Up the Chartiers": the Pittsburgh, Chartiers & Youghiogheny's
   transfer from Scully Yard down the valley, over the Pittsburgh & Lake Erie at McKees Rocks, along its main to Neville
   and over the back channel to the Y Interchange on Neville Island. It is the signals and yard limits run: no time-table,
   no train orders. The player is the conductor. Questions come from the C&E study deck (exam/deck-data.js) in the deck's
   words, and each comes from one book: the GCOR for yard limits, restricted speed and crew duties, the Standard Code
   speed signals (Rules 281 to 292, exam/signals.js) for what a signal shows, the Signals guide for plates. The line is
   from library/chartiers-valley-railroads.html and the P&OV page; the call time, the traffic and the waits are the game's
   own. It loads after road-engine.js (the helpers and the signal toolkit) and registers in window.NevilleRuns.
 */
(function(){
"use strict";
const RE=window.RoadEngine;
const {lib,esc}=RE;
const POV="../library/pittsburgh-ohio-valley-railway.html";

/* ---------- the line ---------- */
/* The points the transfer stands at, in order. x,y is where the engine is drawn. limits: what governs the track there. */
const POINTS=[
  {n:"Scully Yard",x:30,y:92,limits:"yard limits"},
  {n:"PC&Y main",x:105,y:92,limits:"yard limits"},
  {n:"McKees Rocks",x:200,y:92,limits:"interlocking limits"},
  {n:"P&LE main",x:320,y:64,limits:"yard limits, CTC"},
  {n:"Neville",x:430,y:64,limits:"interlocking limits"},
  {n:"Back channel",x:486,y:40,limits:"inside Neville's limits"},
  {n:"Y Interchange",x:556,y:40,limits:"main track inside yard limits"}];
/* The fixed signals the map draws: where, and which way the dots stack (up from the rail or down). */
const SIGS=[
  {k:"dist",x:140,y:92,up:1,t:"Distant, D plate"},
  {k:"xhome",x:176,y:92,up:1,t:"McKees Rocks home"},
  {k:"blk",x:300,y:64,up:0,t:"P&LE block signal"},
  {k:"nvApp",x:370,y:64,up:0,t:"Neville approach"},
  {k:"nvHome",x:412,y:64,up:0,t:"Neville home"}];

/* ---------- questions, in the deck's words ---------- */
const Qs={
  yl:{sec:"yl",src:"YL",where:"Scully Yard",title:"The limits on the sheet",body:"The special instructions list the yard limits of the PC&amp;Y by milepost. Yard limits are a section of…",right:"Main track",wrong:[["Yard track"],["Siding"],["Industry track"]],why:"Yard limits are main track."},
  yardmaster:{sec:"gcor",src:"GC · 1.46",where:"Scully Yard",title:"The Conrail yardmaster",body:"A Conrail yardmaster is on duty at Scully Yard and gives your crew the job. Where a yardmaster is on duty, train, engine and yard crews must…",right:"Comply with the yardmaster's instructions",wrong:[["Take instructions from the dispatcher only"],["Follow their conductor only"],["Work by timetable"]],why:"GCOR 1.46: the yardmaster directly supervises yard crews, clerks and others in the yard, and is responsible for prompt movement of cars and proper make-up of trains. Where a yardmaster is on duty, train, engine and yard crews follow the yardmaster's instructions."},
  speed:{sec:"yl",src:"YL · Definitions",where:"Scully Yard",title:"Leaving on the PC&Y main",body:"The PC&amp;Y main from Scully runs inside yard limits, and there are no block signals on it. According to the Yard Limits guide, all movements within yard limits must be at…",right:"Restricted Speed, unless block signal protection is present",wrong:[["Track speed, since yard limits are main track"],["Whatever speed the yardmaster sets"],["Track speed, unless a train is known to be ahead"]],why:"Yard Limits guide, page 2, item 5: all movements must be at Restricted Speed (unless block signal protection is present)."},
  mph:{sec:"gcor",src:"GC · 6.27",where:"Scully Yard",title:"The number for restricted speed",body:"The engineman asks the conductor for the number. GCOR 6.27: the maximum speed when required to move at restricted speed is…",right:"20 MPH",wrong:[["15 MPH"],["10 MPH"],["25 MPH"]],why:"GCOR 6.27: restricted speed allows stopping within half the range of vision short of a train, engine, car, men or equipment fouling the track, stop signal, or derail or switch lined improperly. Look out for broken rail and do not exceed 20 MPH."},
  // the Conrail move, two forms
  against:{sec:"yl",src:"GC · 6.13",where:"PC&Y main",title:"Against the current of traffic",body:"The Conrail local's engine is on the main ahead and is backing up toward Scully, against the current of traffic. Inside yard limits, GCOR 6.13 allows a movement against the current of traffic only when…",right:"It is authorized or protected by track warrant, track bulletin, yardmaster or other authorized employee",wrong:[["The main track is known to be clear"],["The conductor of the first train there allows it"],["It is made at restricted speed with no other protection"]],why:"GCOR 6.13: against the current of traffic, only when authorized or protected by track warrant, track bulletin, yardmaster or other authorized employee. Yard limits are in effect continuously unless special instructions or a bulletin say otherwise."},
  charge:{sec:"yl",src:"YL",where:"PC&Y main",title:"Who is in charge here?",body:"A Conrail yard engine is working the main ahead, and no yardmaster or agent is on duty on this stretch. Inside yard limits with no yardmaster or agent on duty, who is generally in charge?",right:"The conductor or switch crew foreman of the first train there",wrong:[["The dispatcher"],["The engineer of the longest train"],["Whoever arrives last"]],why:"Yard Limits guide: the yardmaster or agent if one is on duty; otherwise generally the conductor or switch crew foreman of the first train there."},
  distant:{sec:"def",src:"GC · Glossary",where:"PC&Y main",title:"The signal before McKees Rocks",body:"The head brakeman calls a distant signal ahead. It governs the approach to the interlocking and does not tell the track conditions between itself and the next signal. In the GCOR, a distant signal is identified by…",right:"A D",wrong:[["An A"],["A G"],["A P"]],why:"A distant signal governs the approach to a block or interlocking signal and is identified by a D."},
  disagree:{sec:"sig",src:"GC · 1.47C",where:"PC&Y main",title:"Reading the signal",body:"The engineman and the head brakeman read the signal differently, and the conductor was looking at the cars. GCOR: crew members in the cab disagree on a signal's indication. They must…",right:"Regard it as the most restrictive indication observed",wrong:[["Follow the engineer's reading"],["Stop and call the dispatcher"],["Follow the conductor's reading"]],why:"GCOR 1.47C: crew members call out the name of each signal as soon as it is visible and keep watching until passing it. If they disagree on the indication, they treat it as the most restrictive one observed."},
  limits:{sec:"def",src:"GC · Glossary",where:"McKees Rocks",title:"Inside the interlocking",body:"The engine is on the diamond at McKees Rocks. GCOR interlocking limits are the tracks between…",right:"The outer opposing absolute signals of an interlocking",wrong:[["The first and last switches of the interlocking"],["The tower and the distant signal"],["Two consecutive control points"]],why:"Interlocking limits: the tracks between the outer opposing absolute signals of an interlocking."},
  yard:{sec:"yl",src:"GC · 6.13",where:"P&LE main",title:"The P&LE yard alongside",body:"A P&amp;LE yard lies on the left of the main, and the whole stretch is inside yard limits. GCOR 6.13: movements within yard limits are made at restricted speed unless…",right:"Operating under a block signal indication more favorable than Approach",wrong:[["The main track is known to be clear"],["The yardmaster permits otherwise"],["The train is first class"]],why:"GCOR 6.13: trains and engines may use the main track without protecting against other trains or engines. All movements are at restricted speed unless under a block signal more favorable than Approach."},
  ctc:{sec:"yl",src:"GC · 6.13",where:"P&LE main",title:"The main is CTC",body:"The P&amp;LE main here is CTC. Yard limits in CTC territory (GCOR 6.13): who must authorize any main track movement?",right:"The control operator",wrong:[["The yardmaster"],["The conductor"],["No one; yard limits rules apply"]],why:"GCOR 6.13: in CTC territory the control operator must authorize any main track movement."},
  blockRs:{sec:"yl",src:"GC · 6.13",where:"P&LE main",title:"Restricted speed at the block signal",body:"The signal ahead is a block signal that may require restricted speed because the main is inside yard limits. GCOR 6.13: upon observing it, or having advance knowledge of it, a movement entering or within yard limits must be at restricted speed…",right:"At that block signal, or as soon as possible thereafter, consistent with good train handling",wrong:[["Only after the next signal"],["Not until the head end is past the interlocking"],["At the interlocking home signal"]],why:"GCOR 6.13 (Diagrams B and C): upon observing or having advance knowledge that a block signal may require restricted speed due to yard limits, if entering or within yard limits, the movement must be at restricted speed at that block signal, or as soon as possible thereafter, consistent with good train handling."},
  ilplant:{sec:"sig",src:"SG · Signal placement",where:"Neville",title:"Signals at the plant",body:"The engine stands at the Neville plant, where the PC&amp;Y route leaves the P&amp;LE main. In typical signal placement, an interlocking plant has a signal…",right:"For every track where it enters the interlocking limits",wrong:[["Only on the main track at each end of the plant"],["Only where a facing point switch is"],["Only on a signal bridge"]],why:"Interlocking plants have a signal for every track where it enters the interlocking limits. If a signal bridge is used, signal heads are to the right of each track."},
  speedSys:{sec:"sig",src:"SG",where:"P&LE main",title:"How the P&LE signals",body:"The engineman talks about the P&amp;LE's signals. Which signaling system tells the engineer how fast to go past the signal?",right:"Speed signaling",wrong:[["Route signaling"],["APB"],["Interlocking"]],why:"Speed signaling tells the engineer how fast to go past the signal: eastern US and post-UCOR western roads."},
  aspect:{sec:"sig",src:"SG / GC · Glossary",where:"Neville",title:"Aspect and indication",body:"The head brakeman calls what the signal looks like and the engineman says what it tells him. The difference between a signal's aspect and its indication is…",right:"Aspect is what it looks like; indication is what it tells you",wrong:[["Aspect is the rule number; indication is the color"],["They mean the same"],["Aspect applies to semaphores only"]],why:"Aspect: what the signal looks like (color, light positions, blade position). Indication: what it tells you (stop, approach, clear). The GCOR glossary agrees: the indication is the action required."},
  blockDef:{sec:"def",src:"SC · Definitions",where:"P&LE main",title:"What a block signal is",body:"The head brakeman points out the signal at the entrance of the next block. Under the Standard Code, a block signal is…",right:"A fixed signal at the entrance of a block to govern trains and engines entering and using that block",wrong:[["A fixed signal used in connection with one or more signals to govern the approach thereto"],["A signal of fixed location indicating a condition affecting the movement of a train or engine"],["A length of track of defined limits, the use of which by trains and engines is governed by block signals"]],why:"Standard Code definitions: a block signal is a fixed signal at the entrance of a block to govern trains and engines entering and using that block. An approach signal governs the approach to one or more signals; a fixed signal is any signal of fixed location; a block is the length of track."},
  offMain:{sec:"gcor",src:"GC · 6.28",where:"Y Interchange",title:"Onto the interchange track",body:"The transfer leaves the East Runner Main for the interchange track, which is not main track and has no block system. GCOR 6.28: off the main track, trains move at a speed allowing them to stop within…",right:"Half the range of vision",wrong:[["The range of vision"],["100 feet"],["One car length"]],why:"GCOR 6.28: except on a main track or where a block system is in effect, move at a speed that allows stopping within half the range of vision short of a train, engine, car, men or equipment fouling the track, stop signal, or derail or switch lined improperly."}
};
/* Drawn on the way, one question from each pool at most, each once per run. */
const POOL_A=[Qs.blockDef,Qs.speedSys];  // the P&LE main
const POOL_B=[Qs.ilplant,Qs.aspect];      // Neville

/* ---------- the aspects the draws put in front of the player ---------- */
const UNDER="The home signal of the plant is lit";
const xHome=(rule,stopped)=>RE.aspectQ({rule,where:"McKees Rocks",title:stopped?"The home signal at McKees Rocks":"The route clears at McKees Rocks",
  body:stopped?`${UNDER}, and a P&amp;LE train is on the diamond.`:"The P&amp;LE train is clear of the diamond and the route is lined for you."});
const blockQ=RE.aspectQ({rule:"281",where:"P&LE main",title:"A block signal on the P&LE main",body:"The first block signal on the P&amp;LE main, past the plant, is lit."});
const nvApp=rule=>RE.aspectQ({rule,where:"P&LE main",title:"The approach to Neville",body:"The next signal before Neville is lit."});
const nvHome=rule=>RE.aspectQ({rule,where:"Neville",title:"The home signal at Neville",body:"The home signal of the Neville plant is lit for the PC&amp;Y route."});
const SPEEDS=RE.SPEEDS;

/* ---------- the run ---------- */
const run={group:"chartiers",covers:["def","sig","yl","gcor"],code:"PC&Y Transfer",name:"the ore transfer",year:"1981",
  dateLine:"a weekday in 1981",start:300,end:420,endPlace:"Y Interchange",tieUp:"The ore is on the interchange track at {t}.",
  coda:`The PC&amp;Y was owned half by the Pittsburgh &amp; Lake Erie and half by the Pennsylvania side that became Conrail, and kept its own operating organization. It reached Neville Island over the back channel, where it interchanged with the Pittsburgh &amp; Ohio Valley, and it was sold in 1996 to the Pittsburgh Industrial Railroad (${lib("Railroads of the Chartiers Valley")}, <a href="${POV}">Pittsburgh &amp; Ohio Valley</a>).`,
  where(S){const G=S.road;return G?G.at:"Scully Yard"},
  map(S){return map(S)},
  sheet(S){return sheet(S)},

  build(H){
    const S=H.S,rnd=H.rnd,R=()=>H.R();
    const G={pos:0,at:POINTS[0].n,sig:{},train:null,bag:{}};
    S.road=G;
    const work=["Make up the cut and leave Scully Yard","Run the PC&Y main to McKees Rocks and cross the P&LE","Run the P&LE main to Neville","Cross the back channel and set out the ore at the Y Interchange"];

    /* ----- the draws ----- */
    const local=R()<.6;                                      // A: the Conrail local on the main, or only a yard engine
    const cross=R()<.6;                                      // B: a P&LE train on the diamond, the home at Stop
    const nv=SPEEDS[Math.floor(R()*3)];                      // C: the speed of the Neville route
    const nvStop=!cross||R()<.45;                            // D: a P&LE train has Neville (forced when the crossing was clear)
    const xs=SPEEDS.filter(x=>x!==nv)[Math.floor(R()*2)];    // the crossing clears at another speed
    const cars=[22,24,26][Math.floor(R()*3)],lead=["the lead SW9","the second SW9"][Math.floor(R()*2)];
    const waitA=rnd(2,4),waitX=rnd(6,14),waitN=rnd(4,10);
    const num=n=>({22:"twenty-two",24:"twenty-four",26:"twenty-six"})[n];

    /* ----- every question the draws can reach, listed once for the answer key ----- */
    Object.values(Qs).forEach(H.key);
    RE.SPEEDS.forEach(s=>{H.key(xHome(RE.PAIR[s].home,false));H.key(nvApp(RE.PAIR[s].app));H.key(nvHome(RE.PAIR[s].home))});
    H.key(xHome("292",true));H.key(nvApp("285"));H.key(nvHome("292"));H.key(blockQ);
    H.key(RE.plateQ("none","McKees Rocks","McKees Rocks"));H.key(RE.plateQ("SA","Neville","Neville"));
    const draw=(key,pool)=>RE.draw(G,R,H,key,pool,.5);

    /* ----- moves: the clock takes the minutes, the map moves the engine ----- */
    const go=(i,min,note)=>()=>{H.addTime(min);G.pos=i;G.at=POINTS[i].n;if(note)H.log(note);H.renderStatus();H.next()};
    const seen=(k,arms)=>()=>{G.sig[k]=arms;H.renderStatus();H.next()};
    const train=t=>()=>{G.train=t;H.renderStatus();H.next()};
    const info=(where,title,html,btn)=>H.info(where,title,html,btn);

    const steps=[
      info("Scully Yard","Called for 5:00",`<p>You are the conductor of the PC&amp;Y transfer, called at Scully Yard for the ore: ${num(cars)} loaded cars and the caboose, with two PC&amp;Y SW9s on the head end. You take them down Chartiers Creek to McKees Rocks, across the Pittsburgh &amp; Lake Erie and along its main to Neville, then over the back channel to the Y Interchange on Neville Island. #105 shoves them to the Shenango dumper at seven (${lib("Railroads of the Chartiers Valley")}, <a href="${POV}">Pittsburgh &amp; Ohio Valley</a>).</p><p>The special instructions are on the sheet.</p>`,"Go to the yard office"),
      H.ask(Qs.yl),
      info("Scully Yard","The yardmaster",`<p>The Conrail yardmaster gives the job to you, the engineman and the head brakeman: the cut is on the lead, the PC&amp;Y main is clear to McKees Rocks, and the transfer is to be on the island before #105 goes on duty.</p>`),
      H.ask(Qs.yardmaster),
      go(0,15,"Brake test done"),
      info("Scully Yard","Ready to leave",`<p>The brake test is done and the marker is on the caboose. ${lead[0].toUpperCase()+lead.slice(1)} is on the point. The PC&amp;Y main runs down the valley to McKees Rocks, about four miles, inside yard limits the whole way with no block signals.</p>`),
      H.ask(Qs.speed),H.ask(Qs.mph),
      go(1,12,"On the PC&Y main"),H.done(0),
      local
        ?info("PC&Y main","The Conrail local",`<p>The Conrail local is working the main ahead, and its engine is backing up toward Scully. The engineman slows to a stop and waits for the move to clear.</p>`)
        :info("PC&Y main","A yard engine on the main",`<p>A Conrail yard engine is working a track off the main ahead. There is no yardmaster on this stretch, and the engineman slows to a stop short of it.</p>`),
      H.ask(local?Qs.against:Qs.charge),
      H.wait(waitA,"Waited for the Conrail engine to clear"),
      seen("dist","D"),
      info("PC&Y main","A signal ahead",`<p>A signal stands at the side of the main with a D on its plate, ahead of McKees Rocks. The head brakeman calls it. The engineman calls it a second time and reads it differently.</p>`),
      H.ask(Qs.distant),H.ask(Qs.disagree),
      go(2,4,"At McKees Rocks"),
      cross?train("xing"):null,
      seen("xhome",cross?"RRR":ASPECT_ARMS(RE.PAIR[xs].home)),
      info("McKees Rocks","The crossing",cross?`<p>The PC&amp;Y crosses the P&amp;LE main here, at about milepost 3.75 on the P&amp;LE. A westbound P&amp;LE manifest is on the diamond, and the home signal of the plant is against you.</p>`:`<p>The PC&amp;Y crosses the P&amp;LE main here, at about milepost 3.75 on the P&amp;LE. The diamond is clear and the route is lined.</p>`),
      ...(cross
        ?[H.ask(xHome("292",true)),H.ask(RE.plateQ("none","McKees Rocks","McKees Rocks")),
          H.wait(waitX,"Waited at McKees Rocks for the P&LE train"),train(null),seen("xhome",ASPECT_ARMS(RE.PAIR[xs].home)),
          info("McKees Rocks","The manifest is by",`<p>The manifest clears the diamond. The operator lines the route and the home signal changes.</p>`),
          H.ask(xHome(RE.PAIR[xs].home,false))]
        :[H.ask(xHome(RE.PAIR[xs].home,false))]),
      H.ask(Qs.limits),H.done(1),
      go(3,6,"On the P&LE main"),
      seen("blk","GRR"),
      info("P&LE main","The P&LE main",`<p>The transfer runs the P&amp;LE main toward Neville, about two miles, under the P&amp;LE's dispatcher. The McKees Rocks yard is on the left. A block signal stands ahead.</p>`),
      H.ask(blockQ),H.ask(Qs.yard),H.ask(Qs.ctc),
      ...[draw("a",POOL_A)].filter(Boolean),
      go(3,5,"Approaching Neville"),
      seen("nvApp",ASPECT_ARMS(nvStop?"285":RE.PAIR[nv].app)),
      info("P&LE main","The approach to Neville",`<p>${nvStop?"A P&amp;LE yard engine is lined into the McKees Rocks yard ahead of you at Neville.":"The route is lined for the PC&amp;Y at Neville."} The approach signal stands ahead.</p>`),
      H.ask(nvApp(nvStop?"285":RE.PAIR[nv].app)),...(nvStop?[H.ask(Qs.blockRs)]:[]),
      go(4,4,"At Neville"),
      train(nvStop?"nv":null),
      seen("nvHome",nvStop?"RRR":ASPECT_ARMS(RE.PAIR[nv].home)),
      info("Neville","Neville",nvStop?`<p>The PC&amp;Y route leaves the P&amp;LE main at Neville for the back channel. The yard engine has the route, and the home signal is against you.</p>`:`<p>The PC&amp;Y route leaves the P&amp;LE main at Neville for the back channel, and the home signal is lit for it.</p>`),
      H.ask(nvHome(nvStop?"292":RE.PAIR[nv].home)),
      ...(nvStop?[H.ask(RE.plateQ("SA","Neville","Neville")),H.wait(waitN,"Waited at Neville for the P&LE engine"),train(null),seen("nvHome",ASPECT_ARMS(RE.PAIR[nv].home)),
        info("Neville","The route clears",`<p>The yard engine is in the clear and the operator lines the route.</p>`)]:[]),
      ...[draw("b",POOL_B)].filter(Boolean),
      H.done(2),
      go(5,6,"Over the back channel"),
      info("Back channel","The bridge",`<p>The transfer crosses the back channel inside Neville's limits, with no signal of its own on the bridge. Neville Island is ahead.</p>`),
      go(6,8,"At the Y Interchange"),
      info("Y Interchange","The Y Interchange",`<p>The transfer comes down the East Runner Main, main track inside yard limits with no block signals, to the Y Interchange. The cut is to stand on the interchange track for #105's crew.</p>`),
      H.ask(Qs.offMain),
      H.done(3)
    ].filter(Boolean);
    return {work,steps,noPar:true,end:()=>`The ore is on the interchange track at {t}. ${S.clock<=420?"#105 goes on duty at 7:00 and the ore is waiting for it.":"#105 went on duty at 7:00, before the ore was in."}`};
  }
};

/* the arms of an aspect by rule, for the map's signal dots */
function ASPECT_ARMS(rule){return ASPECTS.find(a=>a.r===rule).arms}

/* ---------- the map ---------- */
function map(S){
  const G=S.road,W=600,P=POINTS[G.pos];
  let s=`<svg viewBox="0 0 ${W} 122" role="img" aria-label="Line sketch of the PC&amp;Y transfer route from Scully Yard to the Y Interchange, ${esc(S.def.code)} at ${esc(G.at)}">`;
  s+=`<rect x="0" y="0" width="${W}" height="122" fill="var(--land)"/>`;
  s+=`<path d="M0 12 Q150 6 300 12 T600 10" fill="none" stroke="var(--river)" stroke-width="3" opacity=".55"/><path d="M486 18 Q478 34 486 50" fill="none" stroke="var(--river)" stroke-width="9" opacity=".55"/>`;
  s+=`<text x="8" y="23" font-size="6.5" class="water" style="fill:var(--muted)">OHIO RIVER</text><text x="${W-8}" y="23" font-size="6.5" text-anchor="end" class="water" style="fill:var(--muted)">${esc(S.def.year)}</text><text x="486" y="29" font-size="6.5" text-anchor="middle" class="water" style="fill:var(--muted)">BACK CHANNEL</text>`;
  // yard limits shaded: the PC&Y main from Scully to the plant, and the P&LE's McKees Rocks yard
  s+=`<rect x="14" y="82" width="184" height="20" fill="var(--sheet-2)"/><rect x="224" y="54" width="120" height="20" fill="var(--sheet-2)"/>`;
  // track: the PC&Y main, the 45 degree connection to the P&LE main, the P&LE main (heavier), the connection to the island, the bridge and the island track
  s+=`<g fill="none" stroke="var(--ink)" stroke-linecap="round" stroke-linejoin="round"><path stroke-width="2.2" d="M14 92 H196 L224 64 L231 57"/><path stroke-width="3.4" d="M150 64 H470"/><path stroke-width="2.2" d="M430 64 L454 40 H575"/><path stroke-width="3.6" d="M470 40 H502"/><path stroke-width="2.2" d="M575 33 V47"/></g>`;
  if(G.train){const x=G.train==="xing"?228:372;s+=`<rect x="${x}" y="59" width="40" height="10" rx="2" fill="var(--muted)" stroke="#fff" stroke-width=".8"/><text x="${x+20}" y="66.4" font-size="6" text-anchor="middle" fill="#fff" font-weight="700">P&amp;LE</text>`}
  // the signals and the interlockings
  SIGS.forEach(sg=>{s+=RE.sigDots(G,sg)});
  s+=`<path d="M224 59 L229 64 L224 69 L219 64 Z" fill="var(--rust)" opacity=".85" stroke="var(--ink)" stroke-width=".8"/><rect x="427" y="61" width="6" height="6" fill="var(--rust)" opacity=".85"/>`;
  // labels, clear of the track
  s+=`<g class="lbl" font-size="6.3" text-anchor="middle"><text x="30" y="110" font-weight="${G.pos===0?700:400}">SCULLY YARD</text><text x="105" y="110">PC&amp;Y MAIN</text><text x="224" y="52" font-weight="${G.pos===2?700:400}">MCKEES ROCKS · P&amp;LE MP 3.75</text><text x="335" y="102">P&amp;LE MAIN</text><text x="426" y="52" text-anchor="end" font-weight="${G.pos===4?700:400}">NEVILLE · P&amp;LE MP 5.7</text><text x="${W-8}" y="58" text-anchor="end" font-weight="${G.pos===6?700:400}">Y INTERCHANGE</text></g>`;
  s+=`<g transform="translate(${P.x} ${P.y-1})"><rect x="-13" y="-5" width="26" height="10" rx="2" fill="var(--green)" stroke="var(--glow)" stroke-width="1.4"/><text x="0" y="2.4" font-size="6.4" text-anchor="middle" fill="#fff" font-weight="700">PC&amp;Y</text></g>`;
  return s+`</svg>`;
}

/* ---------- the sheet ---------- */
/* The special instructions, the signals the crew has met, and the work. */
function sheet(S){
  const G=S.road;if(!G)return "";
  const met=SIGS.filter(sg=>G.sig[sg.k]).map(sg=>{
    const a=G.sig[sg.k];
    if(a==="D")return `<div class="ord">${esc(sg.t)}: ${G.pos>=2?"passed":"ahead"}</div>`;
    const A=ASPECTS.find(x=>x.arms===a&&["281","281B","281C","282","283","284","285","287","292"].includes(x.r));
    return `<div class="ord">${esc(sg.t)}: Rule ${A.r}, ${esc(A.name)}</div>`;
  });
  let h=`<h3>PC&amp;Y Transfer</h3><div class="sub">Special instructions · Scully Yard to the Y Interchange · ${esc(S.def.dateLine)}</div>`;
  h+=`<div class="xw-si"><b>Special instructions</b><ul><li>Rules: yard limits, restricted speed and crew duties by the GCOR; what a fixed signal shows by the Standard Code speed signals, Rules 281 to 292; the plates on masts by the Signals guide.</li><li>Scully Yard and the PC&amp;Y main to McKees Rocks: yard limits, no block signals.</li><li>McKees Rocks, about P&amp;LE milepost 3.75: interlocking, with a distant signal.</li><li>P&amp;LE main to Neville: yard limits, CTC, block signals.</li><li>Neville, about P&amp;LE milepost 5.7: interlocking.</li><li>Y Interchange: the East Runner Main is main track inside yard limits; the interchange track is not main track.</li></ul></div>`;
  h+=`<div class="xw-orders"><b>Signals met</b>${met.length?met.join(""):`<div class="ord">None yet</div>`}</div>`;
  h+=`<div class="xw-orders"><b>Work</b>${S.jobs.map(j=>`<div class="ord${j.done?" done":""}">${j.done?"✓ ":""}${esc(j.t)}</div>`).join("")}</div>`;
  return h;
}

window.NevilleRuns=Object.assign(window.NevilleRuns||{},{pcy:run});
})();
