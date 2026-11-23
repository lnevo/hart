/* The 1949 passenger run of Extra East: HART Railroad, "Up the Chartiers": No 307 South, the first-class train from
   Carnegie to Washington on the Pennsylvania Railroad's Chartiers Branch. It runs on the road engine (road-engine.js)
   and the one fixed time-table the coal extra uses. The player is the conductor: the orders and the Clearance Form A at
   Carnegie, the stop on the main, the meet with No 92, and the meet with a B&O extra at Washington. The run is scripted
   on its schedule; the draws change the orders, how late No 92 is, the stop and the B&O train, never the table. Every
   question is a rule from the C&E study deck (exam/deck-data.js), in the deck's words.
 */
(function(){
"use strict";
const RE=window.RoadEngine;
const {ST,LAST,HOU,ARD,BV,HIL,lib,fmt,esc,semSvg,WIKI}=RE;
const BOYCE=7,DEPART=546; // 9:06, the time-table's leaving time at Carnegie

/* ---------- questions that do not change with the draw ---------- */
const Qs={
  rule5:{sec:"def",src:"SC · Rule 5",where:"Carnegie",title:"One time in the table",body:"The time-table shows 9:06 for No 307 at Carnegie, and no second time. Unless otherwise indicated, that time is the…",right:"Leaving time",wrong:[["Arriving time"],["Meeting time"],["Time the train must be in the clear"]],why:"Rule 5: not more than two times are given for a train at any station. One time is the leaving time unless otherwise indicated; two times are the arriving and leaving times."},
  board:{sec:"to",src:"SC · Rule 221",where:"Carnegie",title:"The order board at Carnegie",body:"The semaphore at the Carnegie office shows its blade horizontal, and an operator is on duty. The train may leave only…",extra:semSvg(0),right:"With a Clearance Form A",wrong:[["After waiting 5 minutes"],["When the operator waves it by"],["If it has no orders"]],why:"Rule 221: a fixed signal at each train order office shows stop when an operator is on duty, and while it shows stop, trains must not leave without a Clearance Form A. The semaphore guide adds that a horizontal blade is always stop."},
  late:L=>({sec:"to",src:"SC · Form E",where:"Carnegie",title:"A late order for No 92",body:`Your first order reads “No 92 run ${L} mins late Washington to Carnegie.” What does it do for your train?`,right:"You run with respect to the later time, exactly as to the regular schedule",wrong:[["You may ignore No 92 between Washington and Carnegie"],["You must wait at Washington until No 92 passes"],["You get right over No 92"]],why:"Form E: a train named in the order has its schedule made later between the points. Any train receiving the order runs with respect to the later time exactly as it would to the regular schedule."}),
  both:nm=>({sec:"to",src:"SC · Form S-A",where:"Carnegie",title:"Two meets in one order",body:`One order reads “${nm} meet No 92 at Houston and Extra B&amp;O 6129 North at Washington.” What does an order for two meets do?`,right:"It fixes both meeting points; your train runs with respect to each train to its point and meets it as the rules prescribe",wrong:[["It is not a proper form; each meet needs its own order"],["It requires your train to take the siding at Houston and at Washington"],["It gives your train right over both trains"]],why:"Form S-A (2) fixes several meets in one order. Trains receiving it run with respect to each other to the designated points and there meet in the manner prescribed by the rules."}),
  boOnly:nm=>({sec:"to",src:"SC · Form S-A",where:"Carnegie",title:"The meet order for Washington",body:`One order reads “${nm} meet Extra B&amp;O 6129 North at Washington.” What does it require?`,right:"Neither train may go past Washington until both have arrived",wrong:[["Your train must take the siding at Washington"],["The extra must wait at Washington 10 minutes"],["Your train has right over the extra to Washington"]],why:"Form S-A fixes a meeting point for opposing trains. Neither train may proceed past it until both have arrived. Normally the superior train holds the main and the inferior takes the siding."}),
  superseded:nm=>({sec:"to",src:"SC · Form S-P",where:"Carnegie",title:"An order that replaces another",body:`Two of your orders concern No 92. The first names Arden as the meeting point. The second reads “${nm} meet No 92 at Houston instead of Arden.” What has happened to the first?`,right:"The meet at Arden is superseded; the meet is at Houston",wrong:[["There are now two meets, at Arden and at Houston"],["The first order is annulled and no meet remains"],["You wait at Arden, then at Houston"]],why:"Form S-P: “instead of” supersedes an order. A superseded order is not reissued under its original number. Any part of an order specifying a particular movement may be superseded or annulled (Rule 220)."}),
  rightOver:nm=>({sec:"to",src:"SC · Form S-C",where:"Carnegie",title:"Right over No 92",body:`One order reads “${nm} has right over No 92 Houston to Arden.” No 92 must not go beyond…`,right:"Arden, until your train has arrived",wrong:[["Houston, until your train has left"],["Any station without a new order"],["Arden, until 5 minutes after your train's time"]],why:"Form S-C (2): the second-named train must not go beyond the point last named until the first-named train has arrived, unless authorized by train order."}),
  foreign:{sec:"to",src:"SC · Rule 206",where:"Carnegie",title:"Naming the B&O engine",body:"Your orders name the B&amp;O's engine, Extra B&amp;O 6129 North. What goes with a foreign road's engine number in a train order?",right:"The railroad's initials, ahead of the number",wrong:[["The railroad's full name, after the number"],["Nothing; the direction names it"],["A letter F, ahead of the number"]],why:"Rule 206: regular trains are named by number and extras by engine number and direction, “Extra 798 East”. A foreign road's engine has its initials ahead of the engine number."},
  formF:{sec:"to",src:"SC · Form F",where:"Carnegie",title:"The order for First 307",body:"Your first order reads “Eng 5741 display signals and run as First 307 Carnegie to Washington.” What follows it?",right:"An order for the second section: “Eng … run as Second 307 Carnegie to Washington”",wrong:[["A Clearance Form A for the second section"],["A Form E order making the second section late"],["Nothing; the first section carries the authority for both"]],why:"Form F (1), “Eng 20 display signals and run as First 1 A to Z”, is followed by Form F (2), “Eng 25 run as Second 1 A to Z”."},
  flags:{sec:"sup",src:"SC · Rule 20",where:"Carnegie",title:"Two green flags",body:"A second section follows First 307. What does the engine of First 307 carry on the front?",right:"Two green flags, and two green lights at night",wrong:[["One green flag, at the rear"],["Two white flags"],["No flags; the order is enough"]],why:"Rule 20: all sections except the last display two green flags, and by night also two green lights, in the places provided on the front of the engine."},
  start:{sec:"sig",src:"SC · Rule 12(c)",where:"Carnegie",title:"The signal to start",body:"The brake test is done and the flagman is aboard. The conductor gives the engineman the signal to start. How does he give it?",right:"Raised and lowered vertically",wrong:[["Swung at right angle to the track"],["Held horizontally at arm's length"],["Swung vertically in a circle at right angle to the track"]],why:"Rule 12(c): raised and lowered vertically is proceed. Rule 84: a train must not start until a proper signal is given."},
  whistle:{sec:"sig",src:"SC · Rule 14(c)",where:"Between Boyce and Hills",title:"The flagman is wanted",body:"The engineman wants the flagman to protect the rear. Which whistle signal does he sound?",right:"— o o o",wrong:[["o o o"],["— —"],["o"]],why:"Rule 14(c): — o o o means flagman protect rear of train. o o o is back up, — — is release brakes and proceed, and o is apply brakes and stop."},
  stopped:{sec:"sup",src:"SC · Rule 99",where:"Between Boyce and Hills",title:"The flagman goes back",body:"The flagman hears the whistle. What does he do?",right:"He goes back at once with flagman's signals, placing two torpedoes and, when necessary, lighted fusees",wrong:[["He goes back with one torpedo and a red flag"],["He goes back and places three torpedoes"],["He stays at the rear of the train with a red lantern only"]],why:"Rule 99: a train stopped where it may be overtaken is protected by the flagman going back immediately with flagman's signals a sufficient distance to insure full protection, placing two torpedoes and, when necessary, lighted fusees."},
  recall:{sec:"sup",src:"SC · Rule 99",where:"Between Boyce and Hills",title:"Calling the flagman in",body:"The repair is done. Who sent the flagman out, and who calls him back?",right:"The engineman, both times",wrong:[["The conductor sends him out and the engineman calls him back"],["The dispatcher, by wire"],["The flagman decides when to go and when to return"]],why:"Rule 99: the engineman signals the flagman to protect the rear immediately when stopped, and recalls him when ready to proceed. When recalled he may return, leaving the torpedoes and a lighted fusee. Conductors and enginemen are responsible for the protection of their trains."},
  s83:{sec:"sup",src:"SC · Rule S-83",where:"Houston",title:"Onto the single track",body:"At Houston the line goes from two tracks to one. Before the train goes on, what must you find out?",right:"Whether all superior trains due have arrived or left",wrong:[["That you have a clearance from every operator on the division"],["That the block ahead is clear"],["Whether all extras on the division have reported clear"]],why:"Rule S-83: a train must not pass from two or more tracks to single track until it has been ascertained whether all superior trains due have arrived or left."},
  meetHou:nm=>({sec:"sup",src:"SC · Rule S-89",where:"Houston",title:"Meeting No 92",body:`${nm} is first class and No 92 is second class, and your order fixes the meet at Houston. Who takes the siding?`,right:"No 92, the inferior train; the superior train holds the main",wrong:[["Your train, because it is the opposing train"],["Whichever arrives first, if it is in the clear"],["Neither; the order names the one who waits"]],why:"Rule 72: first class is superior to second. Rule S-89: at a meeting point the inferior train takes the siding, and Form S-A normally leaves the superior train on the main."}),
  meetArd:nm=>({sec:"to",src:"SC · Form S-C",where:"Arden",title:"Right over, and the siding",body:`Your order gave ${nm} right over No 92, Houston to Arden, and the two trains have met at Arden. Unless the order says otherwise, who takes the siding?`,right:"The first-named train",wrong:[["The second-named train"],["The inferior train by class"],["The train that arrives first"]],why:"Form S-C: if the trains meet at either named point, the first-named train takes the siding unless the order says otherwise."}),
  yl:{sec:"yl",src:"SC · Rule 93",where:"Washington",title:"A switch engine on the main",body:"Washington is inside yard limits, and a switch engine is working the main track. Your train is first class. Under Rule 93, what must the switch engine do?",right:"Clear the time of first-class trains at the next station where time is shown",wrong:[["Clear the time of all regular trains by 5 minutes"],["Clear the time of extra trains only"],["Nothing; yard limits give it the main"]],why:"Rule 93: within yard limits the main track may be used, clearing the time of first-class trains at the next station where time is shown. Protection against second-class trains, extra trains and engines is not required."},
  pass:{sec:"to",src:"SC · Rule 220",where:"Washington",title:"How long the orders ran",body:"No 307 is in at Washington and its orders are fulfilled. How long is a train order in effect?",right:"Until it is fulfilled, superseded or annulled",wrong:[["Until the train reaches its terminal"],["Until midnight"],["For 12 hours after it was issued"]],why:"Rule 220: a train order is in effect until it is fulfilled, superseded or annulled. Any part of an order specifying a particular movement may be superseded or annulled."}
};
/* The extra at Washington, as the order words it. */
const BO="Extra B&amp;O 6129 North";
const Q17=(n,nm)=>({sec:"to",src:"SC · Form S-A",where:"Washington",title:"The B&O extra at Washington",body:`Order No ${n} fixed the meet at Washington. ${BO} is an extra, and ${nm} is a regular first-class train. Who holds the main, and who takes the siding on the Connecting?`,right:"The regular train holds the main; the extra, the inferior train, takes the siding",wrong:[["The B&O extra holds the main because it arrived first"],["Both stop short of the interlocking until the dispatcher speaks"],["The B&O extra holds the main, as a foreign train with the right"]],why:"Rule 73: extra trains are inferior to regular trains. Form S-A: neither train goes past the meeting point until both have arrived, and normally the superior train holds the main and the inferior takes the siding."});
/* Questions drawn from a pool on the way, each once per run. The pool is the stretch it comes up on. */
const POOL_A=[ // Bridgeville to Boyce
  {sec:"sig",src:"SC · Rule 14(l)",where:"Mayview",title:"A crossing at Mayview",body:"A public road crosses the line at grade ahead. Which whistle signal does the engineman sound?",right:"— — o —, prolonged or repeated until the crossing is reached",wrong:[["— o o o"],["o o o"],["— — —"]],why:"Rule 14(l): — — o — is the signal for approaching public crossings at grade, prolonged or repeated until the crossing is reached (GCOR: until the engine completely occupies the crossing)."},
  {sec:"sem",src:"SM · Forms",title:"Old lenses",body:"The fireman talks about the old signals on the branch. In very early semaphores, a purple lens was sometimes used in lieu of…",right:"Red",wrong:[["Green"],["Yellow"],["White"]],why:"Semaphore lens colors: red, purple (sometimes used in very early signals in lieu of red), yellow, green, and/or white (in very early signals before the green lens was perfected)."},
  {sec:"sem",src:"SM · Forms",title:"Two arms on a mast",body:"The mast ahead carries two semaphore arms. How many signals can one mast carry?",right:"One, two or three, for a single indication or a combination of signals on the same mast",wrong:[["Only one"],["Two, always one for each track"],["Any number, each with its own indication"]],why:"Semaphore mounting: one, two or three semaphore signals on a single mast for a single indication, or a combination of signals on the same mast."}];
const POOL_B=[ // the stop to Hills
  {sec:"sig",src:"SC · Rule 14(b)",where:"Between Boyce and Hills",title:"Away again",body:"The flagman is back aboard. The engineman sounds — —. What does it mean?",right:"Release brakes. Proceed.",wrong:[["Flagman protect rear of train"],["Back up"],["Approaching a crossing"]],why:"Rule 14(b): — — means release brakes and proceed."},
  RE.aspectQ({rule:"282",where:"Hills",title:"The home signal at Hills",body:"Approaching Hills, where the Montour joins the line, the home signal of the interlocking is lit."})];
const POOL_C=[ // Houston to Arden
  {sec:"to",src:"SC · Rule 222",where:"Houston",title:"The operator at Houston",body:"As No 307 leaves, the operator at Houston picks up the telephone. What does he report?",right:"The time of arrival and departure of your train",wrong:[["Only the number of cars"],["Nothing, unless your train had orders"],["Its tonnage and the crew's names"]],why:"Rule 222: operators promptly record and report the time of arrival and departure of all trains and the direction of extra trains."},
  {sec:"sem",src:"SM · Forms",title:"How the signals are worked",body:"The fireman wonders how the signals at the interlockings are worked. How were semaphores operated?",right:"By mechanical means (pipes or cables), pneumatic, electro-pneumatic or electrical",wrong:[["By gravity alone"],["By the engine's whistle"],["By hand at the mast only"]],why:"Semaphores were operated by mechanical means, either pipes or cables (wires), or pneumatic, electro-pneumatic or electrical power. The power unit can be at the base or the top of the mast."}];
const SIG292={rule:"292",where:"Washington",title:"The home signal at Washington",body:"The home signal of the Washington interlocking, where the Tylerdale Connecting joins the main, is lit against you."};
const SIG287={rule:"287",where:"Washington",title:"Into the station",body:"The route is lined and the home signal changes."};
const early=t=>({sec:"sup",src:"SC · Rule 92",where:"Carnegie",title:"Not before 9:06",body:`The brake test is done at ${t}, ahead of the 9:06 on the time-table, and the engineman is ready to go. May he leave?`,right:"No; a train must not leave a station in advance of its schedule leaving time",wrong:[["Yes; it is a first-class train"],["Yes, if the dispatcher says so by phone"],["Yes, if no opposing train is due"]],why:"Rule 92: a train must not leave a station in advance of its schedule leaving time."});

/* ---------- the run ---------- */
const run={group:"chartiers",covers:["def","sup","to","sig","sem","yl"],code:"No 307 South",name:"the passenger train",year:"1949",
  dateLine:"a weekday in 1949",start:532,end:623,endPlace:"Washington",tieUp:"{t}",
  coda:`The Chartiers Branch carried nine daily round trips in 1926, about an hour and a half from Pittsburgh to Washington, and its last passenger train ran on 20 July 1952 (${lib("Railroads of the Chartiers Valley")}, <a href="${WIKI}" rel="noopener">Wikipedia: Chartiers Branch</a>).`,
  where(S){const G=S.road;if(!G)return "Carnegie";return G.moving?"between "+G.moving:ST[G.pos].n},
  map(S){return RE.map(S,{label:"307"})},
  sheet(S){return RE.sheet(S,{mine:"307"})},

  build(H){
    const S=H.S,rnd=H.rnd,R=()=>H.R();
    const G={pos:0,moving:null,orders:[],bag:{},tt:RE.newTT()};
    S.road=G;
    const T=RE.train(G,"307").t,t92=RE.train(G,"92");
    const work=["Take the orders and the clearance at Carnegie","Run the double track to Houston","Protect the train when it stops on the main","Meet No 92 and run the single track to Washington","Meet the B&O train at Washington"];

    /* ----- the draws ----- */
    const set=["A","B","C"][Math.floor(R()*3)];         // the three order sets
    const L=[30,35,40][Math.floor(R()*3)];              // how late No 92 is
    const d=[10,14,18][Math.floor(R()*3)];              // the stop on the main, minutes
    const F=R()<.4;                                     // a second section follows: the train runs as First 307
    const mode=R()<.45?"match":R()<.64?"mismatch":"wire"; // the clearance: 45, 35 and 20 percent
    const waiting=R()<.6;                               // the B&O extra is already at the interlocking
    const cause=["a hot box on the second coach","a parted air hose behind the baggage car","an injector that will not work"][Math.floor(R()*3)];
    const nm=F?"First 307":"No 307";
    const texts=[];
    if(F)texts.push("Eng 5741 display signals and run as First 307 Carnegie to Washington");
    const iE=texts.length;
    if(set==="A")texts.push(`No 92 run ${L} mins late Washington to Carnegie`,`${nm} meet No 92 at Houston and Extra B&O 6129 North at Washington`);
    if(set==="B")texts.push(`${nm} meet No 92 at Arden`,`${nm} meet No 92 at Houston instead of Arden`,`${nm} meet Extra B&O 6129 North at Washington`);
    if(set==="C")texts.push(`No 92 run ${L} mins late Washington to Carnegie`,`${nm} has right over No 92 Houston to Arden`,`${nm} meet Extra B&O 6129 North at Washington`);
    const base=rnd(11,19),orders=texts.map((text,i)=>({no:base+i,text}));
    const boNo=orders[orders.length-1].no;
    const nums=orders.map(o=>o.no),wrongClear=mode==="mismatch",shown=RE.clearNums(nums,wrongClear);
    const hasE=set!=="B";

    /* ----- the questions that depend on the draw or the clock: shown lazily, listed once for the answer key ----- */
    const lazy=f=>()=>H.ask(f())();
    H.key(Q17("[varies]","[varies]"));H.key(early("[varies]"));
    [RE.Q.who("[varies]","[varies]"),RE.Q.fix("[varies]","[varies]"),RE.Q.wire()].forEach(H.key);
    [Qs.formF,Qs.flags].forEach(H.key);
    POOL_A.concat(POOL_B,POOL_C).forEach(H.key);
    H.key(RE.aspectQ(SIG292));H.key(RE.aspectQ(SIG287));
    [Qs.late("[varies]"),...[Qs.both,Qs.boOnly,Qs.superseded,Qs.rightOver,Qs.meetHou,Qs.meetArd].map(f=>f("[varies]"))].forEach(H.key);
    const draw=(key,pool)=>RE.draw(G,R,H,key,pool,.45);

    /* ----- moves on the schedule: the clock runs the time-table's own minutes, and delays carry on ----- */
    const goTo=(j,note,already)=>()=>{
      S.clock+=T[j]-T[G.pos]-(already||0);G.pos=j;G.moving=null;
      if(note)H.log(note);H.renderStatus();H.next()};
    const t92Late=()=>{ // the dispatcher's late order moves No 92; sets without one still have it late
      for(let i=0;i<=LAST;i++)t92.act[i]=t92.t[i]+L;
      t92.marked=hasE;H.next()};

    /* ----- the meet with No 92 ----- */
    const meetHou=()=>{
      const a=t92.act[HOU],w=Math.max(0,Math.round(a-S.clock));
      H.front(
        H.info("Houston","No 92 at Houston",w>0?`<p>No 92 is not in yet. You stand in the clear on the main for ${w} minutes. At ${fmt(a)} it comes in and goes into the siding.</p>`:`<p>No 92 is already in the siding, in since ${fmt(a)}. The head brakeman has lined the switch for you.</p>`),
        ...(w>0?[H.wait(w,"Waited at Houston for No 92")]:[]),
        H.ask(Qs.meetHou(nm)),
        ()=>{H.log("No 307 and No 92 met at Houston");H.next()});
      H.next();
    };
    const meetArd=()=>{
      const a=t92.act[ARD],w=Math.max(0,Math.round(S.clock-a));
      H.front(
        H.info("Arden","No 92 at Arden",`<p>No 92 has stood at Arden since ${fmt(a)}, held there by your order until you arrived. You are in at ${fmt(S.clock)}, ${w} minutes after it.</p>`),
        H.ask(Qs.meetArd(nm)),
        ()=>{H.log("No 307 and No 92 met at Arden");H.next()});
      H.next();
    };

    /* ----- the orders at Carnegie ----- */
    const first=hasE?Qs.late(L):Qs.superseded(nm);
    const meetQ=(set==="A"?Qs.both:set==="B"?Qs.boOnly:Qs.rightOver)(nm);
    const clearQ=mode==="wire"?H.ask(RE.Q.wire()):lazy(()=>mode==="mismatch"?RE.Q.fix(shown.join(", "),nums.join(", ")):RE.Q.who(shown.join(", "),nums.join(", ")));
    const orderScenes=[
      RE.paper(H,{place:"Carnegie",train:nm+" South",orders,shown,at:()=>S.clock+4,wire:mode==="wire",note:set==="B"?" The operator says No 92 is reported running late.":""}),
      clearQ,RE.take(H,G,orders,wrongClear,mode==="wire"),t92Late];
    // the order that changes No 92's time or the meeting point first, then the meet, then the foreign engine in the last order
    const orderQs=[H.ask(first),H.ask(meetQ),H.ask(Qs.foreign)];
    if(F)orderQs.unshift(H.ask(Qs.formF),H.ask(Qs.flags));

    const steps=[
      H.info("Carnegie","Called for 9:06",`<p>You are the conductor of No 307 South, the 9:06 first-class train to Washington on the Pennsylvania Railroad's Chartiers Branch (${lib("Railroads of the Chartiers Valley")}). The train came in from Pittsburgh at 8:48 behind a G5s, engine 5741, with a baggage-mail car and two coaches. The crew is the engineman, the fireman, the flagman and the head brakeman.</p><p>The time-table is on the right, with No 307's column marked. The orders for the day are with the operator at the Carnegie office.</p>`,"Go to the office"),
      H.ask(Qs.rule5),H.ask(Qs.board),
      ...orderScenes,...orderQs,H.done(0),
      ()=>{S.clock=Math.max(S.clock,DEPART-2);H.log("Brake test done");H.next()},
      ()=>{if(S.clock<DEPART){H.ask(early(fmt(S.clock)))()}else H.next()},
      H.ask(Qs.start),
      ()=>{S.clock=Math.max(S.clock,DEPART);H.log("No 307 leaves Carnegie");H.next()},
      goTo(BV,"Bridgeville"),
      ...[draw("a",POOL_A)].filter(Boolean),
      goTo(BOYCE,"Boyce"),
      // the stop on the main, a minute out of Boyce
      ()=>{G.moving="Boyce and Hills";G.to=HIL;S.clock+=1;H.log("Stopped on the main");H.renderStatus();H.next()},
      H.info("Between Boyce and Hills","Stopped on the main",`<p>The engineman brings the train to a stop on the main track between Boyce and Hills. It is ${cause}. He cannot say how long the repair will take, and ${F?"Second 307 is close behind you on the same schedule":"No 309, the next first-class train, is only forty minutes behind you"}.</p>`),
      H.ask(Qs.whistle),H.ask(Qs.stopped),
      H.wait(d,"Waited on the main for the repair"),
      H.info("Between Boyce and Hills","The repair is done",`<p>The repair took ${d} minutes. The engineman is ready to go and the flagman is still out at the rear.</p>`),
      H.ask(Qs.recall),H.done(2),
      ...[draw("b",POOL_B)].filter(Boolean),
      ()=>{G.to=undefined;S.clock+=T[HIL]-T[BOYCE]-1;G.pos=HIL;G.moving=null;H.log("Hills");H.renderStatus();H.next()},
      goTo(9,"Canonsburg"),
      goTo(HOU,"Houston"),
      H.done(1),
      H.ask(Qs.s83),
      H.info("Houston","Houston",set==="C"?`<p>No 307 stands on the main at Houston, where the line goes to a single track. Your orders give you right over No 92 from Houston to Arden, so there is no meet here.</p>`:`<p>No 307 stands on the main at Houston, where the line goes to a single track. Your orders fix the meet with No 92 here${set==="B"?", in place of Arden":""}.</p>`),
      ...(set==="C"?[]:[meetHou]),
      ...[draw("c",POOL_C)].filter(Boolean),
      goTo(ARD,"Arden"),
      ...(set==="C"?[meetArd]:[]),
      H.done(3),
      goTo(LAST,"Washington"),
      H.info("Washington","Washington",`<p>No 307 comes down to Washington, where the Tylerdale Connecting joins the main and the line from Carnegie ends. ${waiting?"Extra B&amp;O 6129 North is already on the Connecting, waiting for the route.":"Extra B&amp;O 6129 North is coming over the Connecting as you come down to the interlocking."}</p>`),
      H.ask(Qs.yl),
      H.ask(RE.aspectQ(SIG292)),
      H.wait(waiting?3:8,"Waited for the route at Washington"),
      H.info("Washington","The route clears",`<p>The route is lined. The B&amp;O extra pulls into the siding on the Connecting, and No 307 holds the main.</p>`),
      lazy(()=>Q17(boNo,nm)),
      H.ask(RE.aspectQ(SIG287)),
      H.info("Washington","In at the station",`<p>No 307 comes to the station track. The B&amp;O extra goes out behind you, and the meet order is fulfilled.</p>`),
      H.ask(Qs.pass),H.done(4)
    ];
    return {work,steps,noPar:true,end:()=>`${nm} is in at Washington at {t}. ${S.clock<=623?"The train turns there as No 304, due out at 10:23.":"The train turns there as No 304, which was due out at 10:23 and leaves late."}`};
  }
};

window.NevilleRuns=Object.assign(window.NevilleRuns||{},{passenger:run});
})();
