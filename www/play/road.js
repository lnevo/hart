/* The 1949 coal extra of Extra East: HART Railroad, "Up the Chartiers", the first run on the road engine. The line, the one
   fixed time-table, the meet check, the map, the sheet and the order paper are in road-engine.js; this file holds the
   run's own questions, its station-by-station moves and its story. Every question is a rule from the C&E study deck
   (exam/deck-data.js), in the deck's words.
 */
(function(){
"use strict";
const RE=window.RoadEngine;
const {ST,LAST,HOU,ARD,BV,HIL,lib,fmt,esc,semSvg,WIKI}=RE;

/* ---------- questions, in the deck's words ---------- */
/* Asked in the same place on every run. */
const Qs={
  s83:{sec:"sup",src:"SC · Rule S-83",title:"Before leaving Carnegie",body:"Carnegie is your initial station and a register station. What must you find out before Extra 4619 South leaves?",right:"Whether all superior trains that are due have arrived or left",wrong:[["That the block ahead shows clear"],["Whether all extras on the division have reported clear"],["The dispatcher's OK on a track warrant"]],why:"Rule S-83: a train must not leave its initial station on any division or subdivision, or a junction, or pass from two or more tracks to single track, until it has been ascertained whether all superior trains due have arrived or left. Register stations are designated by time-table, and the train register there records the arrival and departure of trains."},
  r73:{sec:"sup",src:"SC · Rule 73",title:"Reading the time-table",body:"No 92 is a second-class freight. Your train is an extra. Which is superior?",right:"No 92: extra trains are inferior to regular trains",wrong:[["Your extra, since it has no schedule to keep"],["Neither; the first to reach a siding decides"],["Your extra, being southward"]],why:"Rule 73: extra trains are inferior to regular trains. Rule 72: first class is superior to second, second to third."},
  ylWho:{sec:"yl",src:"YL",title:"Who is in charge here?",body:"Your train stands on the main track inside the Carnegie yard limits, and a yardmaster is on duty. Who is in charge of the moves?",right:"The yardmaster",wrong:[["The dispatcher"],["The conductor of the first train there"],["The engineer of the longest train"]],why:"Yard Limits guide: the yardmaster or agent if one is on duty; otherwise generally the conductor or switch crew foreman of the first train there."},
  bvSem:{sec:"sem",src:"SM",title:"The home signal at Bridgeville",body:"At Bridgeville, where the Bridgeville &amp; McDonald branch leaves and the P&amp;WV is close by, the home signal of the interlocking shows its blade horizontal.",extra:semSvg(0),right:"Stop",wrong:[["Approach, prepared to stop at the next signal"],["Clear"],["It depends on whether it is upper or lower quadrant"]],why:"A horizontal semaphore blade is always stop, upper or lower quadrant."},
  s71:{sec:"sup",src:"SC · Rule S-71",title:"Onto single track",body:"At Houston the line goes from two tracks to one. On single track, how is one train superior to another?",right:"By right, class or direction; right, given by train order, beats class or direction",wrong:[["By class only"],["By direction, then class, then right"],["By engine number"]],why:"Rule S-71: right is conferred by train order, class and direction by time-table. Right is superior to class or direction, and direction counts only between trains of the same class."},
  sa:{sec:"to",src:"SC · Form S-A",title:"The meet order",body:"Your order reads “Extra 4619 South meet Extra 2231 North at Arden.” What does it require?",right:"Neither train may proceed past Arden until both have arrived",wrong:[["Extra 2231 North waits at Houston for you"],["The train that arrives first goes on at once"],["Both trains clear each other's time by 5 minutes at Arden"]],why:"Form S-A fixes a meeting point for opposing trains. Neither train may proceed past it until both have arrived. Normally the superior train holds the main and the inferior takes the siding."},
  r104:{sec:"sup",src:"SC · Rule 104",title:"The Westland switch",body:"Your head brakeman lined the switch for the Westland branch and the engine took the empties in. Who is responsible for that switch now?",right:"You, the conductor: it must be lined back for the main track",wrong:[["The section foreman"],["The engineman"],["Nobody; leave it open for the next train"]],why:"Rule 104: conductors are responsible for the position of switches used by them and their crews, except where switch tenders are stationed. A switch must not be left open for another train unless a member of that train's crew is in charge of it."},
  hilSem:{sec:"sem",src:"SM",title:"The signal at Hills",body:"The Montour Railroad joins the line at Hills. The semaphore at the interlocking is an upper-quadrant signal. Through what positions does its blade move?",right:"0°, 45° and 90°, rising from horizontal",wrong:[["0°, 30° and 60°, dropping"],["0°, 60° and 90°"],["0° and 90° only"]],why:"Upper-quadrant blades rise to clear through 0°, 45° and 90°, and came about around 1900. Lower-quadrant blades drop through 0°, 30° and 60°."},
  stopped:{sec:"sup",src:"SC · Rule 99",title:"Standing on the main at Arden",body:"Extra 2231 North has gone by. You pull out of the siding and stop on the main track at Arden while the head brakeman lines the Manifold switch, and a superior train may come up behind you. What protects the rear?",right:"The flagman goes back at once with flagman's signals, placing two torpedoes and, when necessary, lighted fusees",wrong:[["The flagman drops lighted fusees at intervals until the train moves"],["The marker lamps are enough while the switch is being lined"],["The engineman sounds — o o o and the train waits for a reply"]],why:"Rule 99: a train stopped where it may be overtaken is protected by the flagman going back immediately with flagman's signals a sufficient distance to insure full protection, placing two torpedoes and, when necessary, lighted fusees. The engineman signals the flagman to go back, and recalls him when ready to proceed."},
  s88:{sec:"sup",src:"SC · Rule S-88",title:"Meeting Extra 2231 North",body:"Extra 2231 North is at Arden, and your order says the two extras meet there. Northward trains are superior by direction. Which extra takes the siding?",right:"Extra 4619 South, the train in the inferior time-table direction",wrong:[["Extra 2231 North, because it is the opposing train"],["Whichever arrives first"],["The one with the higher engine number"]],why:"Rule S-88: when two extras meet, the train in the inferior time-table direction takes the siding, unless otherwise provided. On Form S-A, neither train goes past Arden until both have arrived."},
  d71:{sec:"sup",src:"SC · Rule D-71",title:"The double track",body:"From Carnegie to Houston the line is double track. On two or more tracks, how is a train superior?",right:"By right or class only; direction no longer counts",wrong:[["By right, class or direction, as on single track"],["By direction only"],["By class or direction"]],why:"Rule D-71: on two or more tracks a train is superior by right or class only. Right is conferred by train order, class by time-table, and right is superior to class. The S- rules are the single-track versions."},
};
/* Drawn on the road (between stations) and at a station, from a shuffled bag so a question does not come twice. */
const ROAD=[
  {sec:"sem",src:"SM",title:"An old lower-quadrant blade",body:"The fireman notes the next signal is a lower-quadrant semaphore. Why is a lower-quadrant blade not fail-safe?",right:"If the mechanism fails, gravity drops the blade toward a proceed position",wrong:[["Its lamp burns out easily"],["It can show only two positions"],["Snow freezes it at stop"]],why:"On a lower-quadrant signal the blade drops to clear (0°, 30°, 60°), so a broken linkage can turn stop into approach or clear. Upper-quadrant blades rise (0°, 45°, 90°)."},
  {sec:"sup",src:"SC · Rule 99",title:"Slow on the grade",body:"Extra 4619 is crawling up a grade, and a superior train may come up behind you while you are still moving. How does the flagman protect the rear?",right:"He drops lighted fusees at proper intervals",wrong:[["He goes back and places two torpedoes while the train keeps moving"],["None is needed while the train is moving"],["The engineman sounds — o o o every mile"]],why:"Rule 99: a moving train that may be overtaken is protected by the flagman dropping lighted fusees at proper intervals. Torpedoes are for a stopped train."},
  {sec:"sem",src:"SM",title:"Behind the blade",body:"The colored glass lenses on a semaphore are the roundels. What holds them?",right:"The spectacle",wrong:[["The blade"],["The housing"],["The lamp"]],why:"Semaphore parts: blade, roundels (the lenses), spectacle (holds the roundels), lamp, actuating mechanism, housing."},
  {sec:"sem",src:"SM",title:"Fixed at 45 degrees",body:"Before a river bridge stands a semaphore whose blade never moves from 45°. What is it?",right:"A single-position signal: a permanent approach warning of something ahead",wrong:[["A broken signal to report"],["A train order board"],["A stop signal"]],why:"Single-position semaphores were fixed at 45° as a permanent warning of something ahead such as a bridge, commonly for a restricting indication."},
  {sec:"sem",src:"SM",title:"Old signals",body:"The fireman says these semaphores are as old as the railroad. When was the semaphore patented?",right:"In the 1840s",wrong:[["Around 1900"],["In the 1870s"],["In the 1930s"]],why:"The semaphore was patented in the 1840s and first lit by kerosene, later by electric bulbs. The upper quadrant came around 1900."}
];
const STN=[
  {sec:"sup",src:"SC · Rule S-89",title:"Backing into the siding",body:"The switch at the north end of this siding is blocked by a car, so you must back into the siding from the south end. What does Rule S-89 require?",right:"Protect the train as prescribed by Rule 99",wrong:[["Get a train order first"],["Sound — — o — while backing"],["Nothing, if the superior train is not in sight"]],why:"Rule S-89: if the inferior train must back in, it is protected as prescribed by Rule 99, unless otherwise provided."},
  {sec:"sup",src:"SC · Rule 82",title:"A very late train",body:"The operator says No 93, a regular train, is more than 12 hours behind its schedule at this station. What is its standing now?",right:"It has lost both right and schedule and may move only by train order",wrong:[["It became an extra automatically"],["It keeps its schedule but loses right"],["It runs on its schedule at restricted speed"]],why:"Rule 82: a regular train more than 12 hours behind its arriving or leaving time at any station loses both right and schedule."},
  {sec:"sup",src:"SC · Rule 94",title:"A disabled train",body:"Word comes of a southward freight disabled ahead and unable to move. If needed, your train may…",right:"Pass it if practicable, and if necessary take its schedule and orders",wrong:[["Push it to the next siding"],["Wait until the dispatcher annuls its orders"],["Become a work extra"]],why:"Rule 94: pass the disabled train if practicable; if necessary assume its schedule and take its train orders, then report from the next point of communication."},
  {sec:"sup",src:"SC · Rule S-72",title:"Same class, opposite ways",body:"No 305 South and No 302 North, both first class, are due to meet. With nothing in the orders, which is superior?",right:"No 302: the time-table makes northward trains superior between trains of the same class",wrong:[["The southward train, which is running late"],["Whichever left its terminal first"],["Neither; they need a meet order"]],why:"Rule S-72: trains in the direction specified by the time-table are superior to trains of the same class in the opposite direction. On the Chartiers Branch time-table that is northward."},
  {sec:"sup",src:"SC · Rule 72",title:"First and second class",body:"No 305 is first class and No 92 is second class. Which is superior?",right:"No 305: first class is superior to second",wrong:[["No 92, being a freight"],["They are equal; direction decides"],["Whichever is closer to its schedule"]],why:"Rule 72: trains of the first class are superior to those of the second, second to third, and so on."},
  {sec:"sup",src:"SC · Rule 85",title:"Sections passing",body:"First 305 is delayed here, and Second 305 wants to go around it. What must happen first?",right:"The two sections exchange train orders, signals and numbers",wrong:[["Second 305 gets a train order from the dispatcher"],["Second 305 waits 10 minutes"],["First 305 takes down its green flags"]],why:"Rule 85: a section must not pass another section of the same schedule without first exchanging train orders, signals and numbers with it, and the change is reported from the next point of communication."},
  {sec:"sup",src:"SC · Rule 92",title:"Ready early",body:"No 302 is ready to leave here four minutes before its schedule time. May it go?",right:"No; a train must not leave a station before its schedule leaving time",wrong:[["Yes, first-class trains may run early"],["Yes, if the dispatcher says so by phone"],["Yes, if no opposing train is due"]],why:"Rule 92: a train must not leave a station in advance of its schedule leaving time."},
  {sec:"sup",src:"SC · Rule 20",title:"Two green flags",body:"A southward passenger train goes by with two green flags on the front of the engine. What do they tell you?",right:"Another section of that train follows on the same schedule",wrong:[["It is running late"],["It has right over all trains"],["The track ahead is clear for two blocks"]],why:"Rule 20: all sections except the last display two green flags, and two green lights at night. A section is one of two or more trains running on the same schedule."}
];

/* ---------- the coal extra ---------- */
const coal={group:"chartiers",covers:["sup","to","sem","yl"],code:"Extra 4619 South",name:"the coal extra",year:"1949",
  dateLine:"a weekday in 1949",start:420,end:720,endPlace:"Arden",tieUp:"{t}",
  coda:`The Chartiers Branch ran from Carnegie (Mansfield) to Washington, double track to Houston by 1904. Coal branches left it at Bridgeville from 1890 and, from 1904, for Westland, Palanka and Manifold (${lib("Railroads of the Chartiers Valley")}, <a href="${WIKI}" rel="noopener">Wikipedia: Chartiers Branch</a>).`,
  where(S){const G=S.road;if(!G)return "Carnegie";return G.moving?"between "+G.moving:ST[G.pos].n+(G.inSiding&&G.pos>0&&G.pos<LAST?" (siding)":"")},

  map(S){return RE.map(S,{label:"4619"})},

  sheet(S){return RE.sheet(S,{runLabel:"X 4619"})},

  build(H){
    const S=H.S,rnd=H.rnd,R=()=>H.R();
    const G={pos:0,dir:1,limit:HOU,inSiding:true,moving:null,orders:[],used:new Set(),bag:{},legs:0,depAt:0};
    S.road=G;
    G.tt=RE.newTT();
    const run=(a,b)=>RE.run(G,a,b);
    G.run=run;
    const work=["Take the empties up the double track to Houston","Work the Westland branch","Run the single track to Arden and meet Extra 2231 North","Work the Manifold branch"];

    const checkMove=(k,j,c,a)=>RE.checkMove(G,k,j,c,a);

    /* ----- the questions that depend on the draw: shown to the player, and listed once for the answer key ----- */
    const q=Object.assign({},RE.Q,{
      board:()=>({sec:"to",src:"SC · Rule 221",where:"Houston",title:"The train order board",body:"Coming into Houston, the semaphore at the open office shows its blade horizontal.",extra:semSvg(0),right:"Stop: an operator is on duty, and you must not leave without a Clearance Form A",wrong:[["Slow down and take orders on the fly"],["Proceed: it is only a block signal"],["Whistle — — and keep going"]],why:"Rule 221: the train order signal shows stop while an operator is on duty, and trains must not leave without a Clearance Form A. The semaphore guide adds that a horizontal blade is always stop."})
    });
    // the answer key lists each draw-dependent question once
    [q.margin("[varies]","[varies]","[varies]"),q.r86("[varies]","[varies]"),q.board(),q.fix("[varies]","[varies]"),q.who("[varies]","[varies]")].forEach(H.key);
    Object.values(Qs).forEach(o=>H.key(o));ROAD.forEach(o=>H.key(o));STN.forEach(o=>H.key(o));

    const draw=(key,pool,p)=>RE.draw(G,R,H,key,pool,p);

    /* ----- the station decision ----- */
    function stationRoad(){
      const k=G.pos,d=G.dir,lim=G.limit;
      if(k===lim){endOfPhase();return}
      const opts=[];
      for(let j=k+d;d>0?j<=lim:j>=lim;j+=d){
        if(!ST[j].sd)continue;if(opts.length>=3)break;
        const via=[];for(let m=k+d;m!==j;m+=d)via.push(ST[m].n);
        opts.push({j,t:"Run to "+ST[j].n,s:"arrive about "+fmt(S.clock+run(k,j))+(via.length?" · through "+via.join(", "):"")});
      }
      const el=H.scene(ST[k].n,"At "+ST[k].n+(G.inSiding&&k>0?", in the siding":""),
        `<p>${k===0&&!G.legs?"Your train stands at Carnegie, ready to leave.":"Extra 4619 "+(d>0?"South":"North")+" is in the clear at "+esc(ST[k].n)+"."} Choose how far to run, or wait in the siding for the next train to pass. Use the time-table and your running times.</p><div class="choices" id="dc"></div>`);
      const box=el.querySelector("#dc")||H.$("dc");
      box.innerHTML=opts.map((o,i)=>`<button class="xw-btn" data-i="${i}">${esc(o.t)}<small>${esc(o.s)}</small></button>`).join("")+
        `<button class="xw-btn" id="dw">Wait in the siding for the next train<small>hold at ${esc(ST[k].n)}</small></button>`;
      const lock=f=>()=>{box.querySelectorAll("button").forEach(z=>z.disabled=true);f()};
      box.querySelectorAll("button[data-i]").forEach(b=>b.onclick=lock(()=>departRoad(opts[+b.dataset.i].j)));
      H.$("dw").onclick=lock(waitRoad);
    }
    function waitRoad(){
      const k=G.pos;
      const due=G.tt.trains.filter(tr=>tr.act[k]>S.clock).sort((a,b)=>a.act[k]-b.act[k]);
      if(!due.length){H.addTime(10);H.log("Waited 10 minutes at "+ST[k].n);
        H.front(H.info(ST[k].n,"Nothing comes","<p>Ten minutes pass and no train comes by. No more regular trains are due at "+esc(ST[k].n)+".</p>"),stationRoad);H.next();return}
      const tr=due[0];
      S.clock=Math.max(S.clock,tr.act[k]);
      const txt=`${tr.name} passes ${ST[k].n} at ${fmt(tr.act[k])}`;
      H.log(txt);
      H.front(H.info(ST[k].n,tr.name+" goes by","<p>"+esc(txt)+".</p>"),stationRoad);H.next();
    }

    /* what lies between k and j: the semaphores at the Bridgeville and Hills interlockings, the double track, or a question from the road */
    function passing(k,j){
      const out=[];
      if(k===0)out.push(H.ask(Qs.d71));
      if(k===HOU)out.push(H.ask(Qs.s71)); // leaving Houston onto the single track
      for(let i=k+1;i<=j;i++){
        if(i===BV&&!G.used.has("bv")){G.used.add("bv");out.push(H.ask(Qs.bvSem),H.wait(4,"Waited for the route at Bridgeville"))}
        if(i===HIL&&!G.used.has("hil")){G.used.add("hil");out.push(H.ask(Qs.hilSem))}
      }
      if(!out.length){const ev=draw("road",ROAD,.6);if(ev)out.push(ev)}
      return out;
    }
    function departRoad(j){
      const k=G.pos;
      G.depAt=S.clock;
      H.log("Leaves "+ST[k].n+(j!==k+G.dir?" for "+ST[j].n:""));
      G.legs++;G.inSiding=false;G.moving=ST[k].n+" and "+ST[j].n;
      H.front(...passing(k,j),()=>resolveMove(k,j));H.next();
    }
    /* Wrong answers on the road cost time after arrival. Head-on and rear-end collisions end the run. */
    function resolveMove(k,j){
      const dep=G.depAt,extra=S.clock-dep,c=dep+extra,a0=c+run(k,j); // minutes lost to wrong answers on the way count
      const fault=checkMove(k,j,c,a0);
      const sev=fault.find(p=>p.kind==="headon"||p.kind==="rear");
      if(sev){crash(sev,k,j);return}
      const notes=[];
      fault.filter(p=>p.kind==="margin").forEach(p=>notes.push(H.ask(q.margin(p.tr.name,ST[p.at].n,Math.max(0,p.by)))));
      fault.filter(p=>p.kind==="r86").forEach(p=>notes.push(H.ask(q.r86(p.tr.name,ST[j].n))));
      S.clock=a0;G.pos=j;G.moving=null;G.inSiding=!!ST[j].sd&&j>0&&j<LAST;
      arrive(j,notes);
    }
    function crash(p,k,j){
      const between=`between ${ST[k].n} and ${ST[j].n}`,me="Extra 4619 "+(j>k?"South":"North");
      const what=p.kind==="headon"?`${p.tr.name} met ${me} head-on ${between}`:`${p.tr.name} ran into the rear of ${me} ${between}`;
      const why=p.kind==="headon"
        ?`You left ${ST[k].n} at a time when you could not reach ${ST[j].n} ahead of ${p.tr.name}. An extra must keep out of the way of opposing regular trains and clear their time by 5 minutes (Rule S-87), or be protected under Rule 99.`
        :`${p.tr.name} is superior and was following you. You had to be clear when it was due to leave the station behind you (Rule 86).`;
      S.misses.push({title:"Collision",why,src:p.kind==="headon"?"SC · Rule S-87":"SC · Rule 86",sec:"sup",end:true});
      H.log("✗ "+what);
      H.finish(what+". "+why,true);
    }
    function arrive(j,notes){
      H.log("Arrives "+ST[j].n);
      const scenes=[...notes];
      if(j!==G.limit){const ev=draw("stn",STN,.4);if(ev)scenes.push(ev)}
      H.front(...scenes,stationRoad);H.next();
    }

    /* ----- the ends of the two stretches ----- */
    function endOfPhase(){
      if(G.phase==="A")houston();else arden();
    }
    function houston(){
      G.phase="done-A";
      // the one order: the meet with Extra 2231 North
      const n1=rnd(11,19),orders=[{no:n1,text:"Extra 4619 South meet Extra 2231 North at Arden"}];
      const nums=orders.map(o=>o.no),wrongClear=R()<.5,shown=RE.clearNums(nums,wrongClear);
      const scenes=[
        H.done(0),
        H.info("Houston","Houston","<p>Extra 4619 South stands on the main at Houston, where the Westland branch leaves. The empties go to the mine.</p>"),
        H.ask(q.board()),
        RE.paper(H,{place:"Houston",train:"Extra 4619 South",orders,shown,at:S.clock+3}),
        wrongClear?H.ask(q.fix(shown.join(", "),nums.join(", "))):H.ask(q.who(shown.join(", "),nums.join(", ")))];
      scenes.push(RE.take(H,G,orders,wrongClear),
        H.ask(Qs.sa),
        H.info("Houston","The Westland branch",`<p>The Westland branch leaves the main at Houston (${lib("the Chartiers Branch's coal branches")}). Your crew pulls the empties off the main and sets them where the mine crew wants them, and picks up the loads.</p>`),
        H.ask(Qs.r104),
        H.wait(35,"Westland branch worked: empties set, loads picked up"),H.done(1),
        ()=>{G.phase="B";G.limit=ARD;G.dir=1;G.inSiding=true;H.log("Extra 4619 South ready at Houston");stationRoad()});
      H.front(...scenes);H.next();
    }
    function arden(){
      G.phase="done-B";
      H.front(
        H.info("Arden","Extra 2231 North","<p>Extra 2231 North comes up from Washington and stops at Arden. The Manifold branch leaves the single track here.</p>"),
        H.ask(Qs.s88),H.done(2),
        H.info("Arden","The Manifold branch",`<p>The Manifold branch is one of the coal branches the Chartiers Branch served (${lib("Railroads of the Chartiers Valley")}). The head brakeman lines the switch and the engine goes in for the loads.</p>`),
        ()=>{G.inSiding=false;H.next()}, // out of the siding onto the main for the Manifold switch
        H.ask(Qs.stopped),
        H.wait(30,"Manifold branch worked: loads out"),H.done(3));
      H.next();
    }

    const steps=[
      H.info("Carnegie","Called for 7:00",`<p>You are the conductor of Extra 4619 South, a freight extra from Carnegie, the Mansfield end of the Pennsylvania Railroad's Chartiers Branch. The branch runs south to Washington (${lib("Railroads of the Chartiers Valley")}). It has been double track as far as Houston since 1904.</p><p>The time-table on the right shows the regular trains. Northward trains are superior to southward trains of the same class, and your extra is inferior to every regular train. You have empties for the mines at Houston and Arden.</p>`,"Go to the caboose"),
      H.ask(Qs.ylWho),H.ask(Qs.s83),H.ask(Qs.r73),
      ()=>{G.phase="A";G.limit=HOU;G.dir=1;H.log("Extra 4619 South ready at Carnegie");stationRoad()}
    ];
    return {work,steps,noPar:true,end:()=>"Extra 4619 South is tied up at Arden at {t}. The loads from Westland and Manifold go north with the next crew."};
  }
};

window.NevilleRuns=Object.assign(window.NevilleRuns||{},{coal});
})();
