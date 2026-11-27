/* The 1997 PIR run of Extra East: HART Railroad, "Up the Chartiers": PIR Local, the south turn, of the Pittsburgh Industrial
   Railroad (a RailTex company) from the McKees Rocks office to Duff Junction, south on the Chartiers track to Bridgeville and
   Canonsburg, and back to leave a cut for CSX at POV Junction. It is the track warrant run: from Duff Junction the Chartiers
   track has no signals, and every move is a warrant the dispatcher reads and the player copies (warrant.js). The player is
   the conductor. Questions come from the C&E study deck (exam/deck-data.js) in the deck's words: the GCOR for warrants, yard
   limits and crew duties, the track warrant guide for the boxes, the Signals guide for plates. The line and the railroads
   are from library/chartiers-valley-railroads.html; the dispatcher's initials, Local 2, the work train, the warrant numbers
   and the times are the game's own. It loads after warrant.js and registers in window.NevilleRuns.
 */
(function(){
"use strict";
const RE=window.RoadEngine,TW=RE.twc;
const {lib,esc,fmt}=RE;

/* ---------- the line ---------- */
/* The points the engine stands at, in order. x,y is where it is drawn. Mileposts are from Carnegie; Duff Junction has none. */
const POINTS=[
  {n:"McKees Rocks",x:440,y:60},
  {n:"Duff Junction",x:385,y:88},
  {n:"Carnegie",x:315,y:88},
  {n:"Bridgeville",x:240,y:88},
  {n:"Hills",x:150,y:88},
  {n:"Canonsburg",x:60,y:88},
  {n:"McKees Rocks diamond",x:490,y:60},
  {n:"POV Junction",x:556,y:60}];
const [MKR,DUFF,CAR,BRV,HIL,CAN,DIA,POV]=[0,1,2,3,4,5,6,7];
/* The fixed signals the map draws: the distant before the diamond and the home at it. */
const SIGS=[
  {k:"dist",x:452,y:60,up:1,t:"Distant, D plate"},
  {k:"home",x:474,y:60,up:1,t:"McKees Rocks home"}];
/* What each warrant authorises, by points, for the bar on the map; short: it stops short of the last siding switch (Box 8). */
const AUTH={"114":[DUFF,BRV],"118":[BRV,CAN],"121":[HIL,CAN],"125":[CAN,DUFF]};

/* ---------- the warrants ---------- */
const W114=t=>({no:"114",at:"Duff Junction",boxes:{2:["Duff Junction","Bridgeville","Main"],5:[t],10:[],13:["20","Carnegie","Bridgeville"],16:[]}});
const W118w={no:"118",at:"Bridgeville",boxes:{2:["Bridgeville","Canonsburg","Main"],7:["Local 2","Bridgeville"],10:[]}};
const W118h={no:"118",at:"Bridgeville",boxes:{2:["Bridgeville","Canonsburg","Main"],8:[]}};
const W121a={no:"121",at:"Canonsburg",boxes:{4:["Hills","Canonsburg","Main"],12:["Hills","Canonsburg"]}};
const W121b={no:"121",at:"Canonsburg",boxes:{4:["Hills","Canonsburg","Main"],11:["Hills","Canonsburg"],
  17:["Joint with PIR work train between Hills and Canonsburg"]}};
const W125={no:"125",at:"Canonsburg",boxes:{1:["121"],2:["Canonsburg","Duff Junction","Main"],15:[]}};

/* ---------- questions, in the deck's words ---------- */
const Qs={
  yl:{sec:"yl",src:"GC · 6.13",where:"McKees Rocks",title:"Yard limits to Duff Junction",body:"The special instructions put the PIR main from McKees Rocks to Duff Junction inside yard limits. GCOR 6.13: yard limits are in effect…",right:"Continuously, unless special instructions or a bulletin say otherwise",wrong:[["Only while a yardmaster is on duty"],["Only while the dispatcher has a warrant out for the main"],["From the first train's arrival until it leaves"]],why:"GCOR 6.13: yard limits are in effect continuously unless special instructions or a bulletin say otherwise."},
  noWarrant:{sec:"twc",src:"TW · Selected rules",where:"Duff Junction",title:"Past the yard limit sign",body:"Past the sign at Duff Junction the Chartiers track has no signals. Who may occupy the main there without a warrant?",right:"Nobody, except within yard limits or restricted limits",wrong:[["Work extras"],["Trains moving under 20 MPH"],["Passenger trains"]],why:"Outside yard (or restricted) limits, nobody occupies the main track in TWC territory without a warrant (GCOR 14.1)."},
  call:{sec:"twc",src:"GC · 14.8",where:"Duff Junction",title:"Calling the dispatcher",body:"At the yard limit sign you call the dispatcher for a track warrant. What do you tell him?",right:"What movements you will make and, when necessary, which tracks and how much time you need",wrong:[["Your train's tonnage and car count"],["Only your train symbol; he works out the rest"],["The OK time you would like"]],why:"GCOR 14.8: tell the dispatcher what movements will be made and, when necessary, which tracks and how much time is required."},
  ok:{sec:"twc",src:"GC · 14.9",where:"Duff Junction",title:"The OK time",body:"The dispatcher has given the OK time and his initials. What do you do now?",right:"Write the OK time and initials on the warrant and repeat them",wrong:[["Tell the engineer to go; the warrant is good",{end:true,endText:"You left before the OK time and initials were on the warrant and repeated back."}],["Wait for a written copy at the next station"],["Read the box numbers back again"]],why:"GCOR 14.9 step 4: the employee writes the OK time and initials and repeats them. A warrant is not in effect until the OK time is shown on it."},
  copies:{sec:"twc",src:"GC · 14.9",where:"Duff Junction",title:"Copies",body:"Who must have a copy of warrant 114?",right:"The conductor and the engineer, each copy dated",wrong:[["Only you, the conductor"],["Only the engineer, who runs the train"],["The dispatcher keeps the only copy"]],why:"GCOR 14.9: the conductor and the engineer each have a copy, every crew member must read and understand it, and the copy shows the date."},
  box13:{sec:"twc",src:"GC · 14.0 form",where:"Carnegie to Bridgeville",title:"Box 13",body:"Warrant 114 has Box 13, “Do not exceed 20 MPH between Carnegie and Bridgeville.” The engineer has the train up to 25 MPH past Carnegie.",right:"Bring it down to 20 MPH or less",wrong:[["Hold 25; the limit starts at Bridgeville"],["Hold 25 until the next station"],["Drop to restricted speed"]],why:"Boxes 13 and 14 set a speed limit between the named points; Box 13 here covers Carnegie to Bridgeville."},
  last:{sec:"twc",src:"GC · 14.2",where:"Bridgeville",title:"Where does warrant 114 end?",body:"Bridgeville is the last named point, and Box 10 tells you to clear the main track there. Where does your authority end?",right:"At the first siding switch at Bridgeville, including it",wrong:[["At the Bridgeville station sign"],["At the last siding switch at Bridgeville",{end:true,endText:"You ran past the first siding switch at Bridgeville, out of your limits."}],["At the next station, Mayview",{end:true,endText:"You ran past the end of your authority at Bridgeville."}]],why:"GCOR 14.2: at the last named point, authority extends to and includes the first siding switch. First is last and last is first. GCOR 14.3: never foul a switch at either end where an opposing train may use it to clear."},
  clear:{sec:"twc",src:"GC · 14.7",where:"Bridgeville",title:"Reporting clear by a hand switch",body:"You report clear of warrant 114 after leaving the main through a hand-operated switch, outside yard limits. What must you tell the dispatcher?",right:"The position of the switch and that it is locked",wrong:[["Only that the train is clear"],["The time you passed the switch"],["Nothing more; the switch is not his concern"]],why:"GCOR 14.7: outside yard or restricted limits, tell the dispatcher the switch position and that it is locked when reporting clear. He repeats it and you confirm."},
  box7:{sec:"twc",src:"GC · 14.0 form",where:"Bridgeville",title:"Box 7",body:"Warrant 118 has its OK time. A headlight is coming: Local 2 is a mile out of Bridgeville. May you pull out of the siding?",right:"No. The warrant is not in effect until Local 2 has arrived at Bridgeville",wrong:[["Yes; the OK time is on the warrant",{end:true,endText:"You took the main before Local 2 arrived at Bridgeville. Box 7 kept warrant 118 out of effect."}],["Yes, at restricted speed"],["Yes, if you keep Local 2 in sight"]],why:"Box 7: Not in effect until after arrival of the named train at the named point."},
  other:{sec:"twc",src:"TW · Worked example",where:"Bridgeville",title:"The other warrant",body:"Local 2 has arrived at Bridgeville, the end of its own warrant. What happens to that warrant now?",right:"Local 2 reports clear of its limits, and the dispatcher voids its warrant",wrong:[["It stays in effect until midnight"],["It passes to your train with warrant 118"],["Nothing; the dispatcher keeps it open"]],why:"In the guide's worked example a warrant that was holding another train out of effect is reported clear and voided when that train arrives. Unless a Box 6 time ends it sooner, a warrant stays in effect until the crew releases it."},
  box8:{sec:"twc",src:"GC · 14.2",where:"Canonsburg",title:"The end of warrant 118",body:"Canonsburg is your last named point and Box 8, Hold main track at last named point, is checked. Where does your authority end?",right:"Short of the last siding switch at Canonsburg, not including it",wrong:[["At the first siding switch, including it"],["At the last siding switch, including it",{end:true,endText:"You fouled the far switch at Canonsburg that Local 2 needed."}],["At the station sign"]],why:"Box 8 extends the limit past the near switch, to but not including the last siding switch, so you hold the main while an opposing train uses the siding. GCOR 14.3: never foul that switch."},
  farSwitch:{sec:"twc",src:"GC · 14.3",where:"Canonsburg",title:"The far switch",body:"Stopped at the end of warrant 118, the engineer asks whether he may pull ahead far enough to foul the far siding switch at Canonsburg. Local 2 may use that switch to clear the main. May he?",right:"No; a train must not foul a switch at either end of its limits where an opposing train may use it to clear",wrong:[["Yes, if he stops short of the station sign"],["Yes, at restricted speed"],["Yes, after calling Local 2 on the radio"]],why:"GCOR 14.3: the train must not foul a switch at either end of its limits where an opposing train may use that switch to clear the main track. Box 8 already stops your limit short of that switch."},
  box4:{sec:"twc",src:"GC · 14.0 form",where:"Canonsburg",title:"Box 2 or Box 4?",body:"You will switch the plants both ways between Hills and Canonsburg. Which box lets you move both ways in your limits?",right:"Box 4, Work between",wrong:[["Box 2, Proceed from … to"],["Box 7, Not in effect until after arrival of"],["Box 10, Clear main track at last named point"]],why:"Box 2 is one direction only; backing up needs permission for a reverse move. Box 4, Work between, gives movement in both directions for locals and work trains."},
  rs:{sec:"gcor",src:"GC · 6.27",where:"Hills to Canonsburg",title:"How long at restricted speed?",body:"Box 12 puts you at restricted speed between Hills and Canonsburg. When may you resume speed?",right:"When the leading wheels pass the end of the restriction",wrong:[["When the rear car passes the end"],["When you see a clear signal"],["When the foreman waves you by"]],why:"GCOR 6.27: restricted speed applies until the leading wheels pass the point where it is no longer required. Not over 20 MPH, able to stop within half the range of vision."},
  joint:{sec:"twc",src:"GC · 14.0 form",where:"Hills to Canonsburg",title:"Joint with the work train",body:"Boxes 11 and 17 say you are joint with the PIR work train between Hills and Canonsburg. How do you run there?",right:"At restricted speed: the limits are occupied by a train",wrong:[["At 20 MPH; the work train will stay clear"],["Not over 30 MPH"],["Stop and wait for it to report clear"]],why:"Box 11: between the points, make all movements at restricted speed; limits occupied by train. Box 17 carries other instructions such as “joint with”. GCOR 6.27: not over 20 MPH, able to stop within half the range of vision."},
  box1:{sec:"twc",src:"GC · 14.0 form",where:"Canonsburg",title:"Box 1",body:"Warrant 125 has Box 1 checked, with the number 121. Box 1 is…",right:"Track warrant no. 121 is void",wrong:[["Proceed from … to … on Main track"],["Work between … and … on Main track"],["Other specific instructions"]],why:"Box 1: Track warrant no. __ is void. A warrant that voids another names its number there."},
  box15:{sec:"twc",src:"GC · 14.0 form",where:"Canonsburg",title:"Box 15",body:"Box 15 is checked on warrant 125: “Flag protection not required against following trains on the same track.” What does that tell you?",right:"The dispatcher protects your rear: you need not flag against following trains",wrong:[["You must flag against following trains"],["No other train is on the subdivision"],["You may back up without permission"]],why:"Box 15: flag protection not required against following trains on the same track."},
  dplate:{sec:"sig",src:"SG · Signal signage",where:"McKees Rocks",title:"The D plate",body:"A signal on the approach to the diamond at McKees Rocks carries a D plate. What does it tell you?",right:"Distant signal: it warns of an interlocking ahead in dark territory",wrong:[["SA: an interlocking signal with an ABS part; at stop, get permission from the operator"],["G: a grade signal that may be passed at restricted speed without stopping"],["P: a protective detector in the block that the crew must inspect"]],why:"Signal plates: D is a distant signal, warning of an interlocking ahead in dark territory. SA is an interlocking signal with an ABS part, G a grade signal and P a protective signal."},
  // the pools
  special:{sec:"gcor",src:"GC · 1.47B",where:"Duff Junction",title:"Cars that need special handling",body:"The Conrail local hands over nine cars, two of them stainless coil. Who checks with the conductor whether any cars need special handling?",right:"The engineer",wrong:[["The dispatcher"],["Nobody; it is on the waybills"],["The Conrail yardmaster"]],why:"GCOR 1.47B: the engineer must check with the conductor whether any cars or units need special handling."},
  bulletin:{sec:"def",src:"GC · Glossary",where:"Carnegie to Bridgeville",title:"A track bulletin",body:"Box 16 is checked on warrant 114: “Track bulletins in effect.” In the GCOR, a track bulletin is…",right:"A notice of conditions affecting train movement",wrong:[["A publication with instructions on train, engine, or equipment movement"],["Instructions contained in the timetable or other publication"],["An indicator that tells whether a length of track is occupied"]],why:"A track bulletin is a notice of conditions affecting train movement. It may also authorize movement against the current of traffic where Rule 9.14 is in effect."},
  remind:{sec:"gcor",src:"GC · 1.47A",where:"Carnegie to Bridgeville",title:"Reminding the engineer",body:"Bridgeville is the limit of your warrant. The conductor must remind the engineer of an approaching restriction…",right:"After passing the last station, but at least 2 miles before it",wrong:[["1 mile before it"],["When it comes into view"],["Only when asked"]],why:"GCOR 1.47A(3): the conductor reminds the engineer when approaching limits of authority, a track warrant, track bulletin or radio speed restriction, after passing the last station but at least 2 miles from the restriction."},
  blocking:{sec:"def",src:"GC · Glossary",where:"Carnegie to Bridgeville",title:"Keeping a following train off the main",body:"The engineer of Local 2 talks about a method to establish an absolute block for a following train in non-signaled territory by direct communication with a preceding train. It is…",right:"Radio blocking",wrong:[["Block register territory"],["Direct traffic control"],["Track warrant control"]],why:"Radio blocking: a method to establish an absolute block for a following train in non-signaled territory by direct communication with a preceding train."},
  siding:{sec:"twc",src:"TW · Selected rules",where:"Bridgeville",title:"Into the siding",body:"You head into the siding at Bridgeville. The warrant does not govern the siding. How fast may you move in it?",right:"At a speed that lets you stop within half the range of vision",wrong:[["Restricted speed under warrant 114"],["Maximum authorized speed"],["Yard speed"]],why:"Track warrants govern only the main track. In sidings and other tracks, move at a speed that lets you stop within half the range of vision short of any obstruction or improperly lined switch (GCOR 6.28)."},
  whole:{sec:"twc",src:"TW · Selected rules",where:"Bridgeville",title:"Reporting clear",body:"The engine is in the siding at Bridgeville. When can you report clear of warrant 114's limits?",right:"When the whole train is off the main and the switch is lined back to normal",wrong:[["Now; the engine is clear"],["When the engine passes the clearance point"],["When Local 2 is in sight"]],why:"Clear of the limits means the whole train, not just the engine, clear of the limits and off the main track, with switches restored to normal (except within yard limits)."},
  box9:{sec:"twc",src:"GC · 14.0 form",where:"Bridgeville",title:"Box 9",body:"Another crew's warrant has Box 9 checked with your train's symbol. What does Box 9 say?",right:"Do not foul limits ahead of the named train",wrong:[["Clear main track at last named point"],["Not in effect until after arrival of the named train"],["Joint with the named train"]],why:"Box 9: Do not foul limits ahead of __. Box 7 is Not in effect until after arrival of __ at __, and Box 10 is Clear main track at last named point."},
  norail:{sec:"twc",src:"GC · 14.7",where:"Bridgeville",title:"No caboose",body:"There is no crew on the rear of your train. Which shows the dispatcher your whole train is clear of the limits?",right:"A rear-end telemetry device, with air pressure on the head-end device showing brake pipe continuity",wrong:[["The engineer's word that the train felt complete"],["The time since you passed the last station"],["The head end passing the clearance point"]],why:"GCOR 14.7 lists: a rear-end telemetry device with air pressure on the head-end device showing brake pipe continuity, an employee verifying the marker, a crew member seeing the rear car with the marker, an inspection while stopped, or matching axle counts from two detectors."}
};
const POOL_1=[Qs.special];
const POOL_2=[Qs.bulletin,Qs.remind,Qs.blocking];
const POOL_3=[Qs.siding,Qs.whole,Qs.box9];

/* ---------- the run ---------- */
/* Box 5's question is made when it is asked, from the clock; the key lists it with the time left as a blank. */
const BOX5_WHY="Box 5: Not in effect until the time shown. Box 6 is the other timing box: This authority expires at the time shown.";
/* Box 5's question: the warrant takes effect at `until`, the clock reads `now`; `late` is the end text for leaving early. */
const box5Q=(until,now,late)=>({sec:"twc",src:"GC · 14.0 form",where:"Duff Junction",title:"Box 5",
  body:`Warrant 114 has its OK time, and Box 5 reads “Not in effect until ${until}.” It is ${now}. May you leave now?`,
  right:`No; wait until ${until}, when the warrant takes effect`,
  wrong:[["Yes; the OK time puts it in effect",{end:true,endText:late}],[`Yes, at restricted speed until ${until}`],
    ["Yes, if no train is in sight"]],
  why:BOX5_WHY});
const box5Key=box5Q("[varies]","[varies]","You took the main before Box 5's time.");

const run={group:"chartiers",covers:["def","sig","yl","twc","gcor"],code:"PIR Local",name:"the south turn",year:"1997",
  dateLine:"a weekday in 1997",start:360,end:840,endPlace:"POV Junction",tieUp:"The cut for CSX is on the interchange track at POV Junction at {t}.",
  coda:`The Pittsburgh Industrial Railroad, a RailTex company, bought about 32.7 miles of the Chartiers industrial track from Conrail and about 16.0 miles from the PC&amp;Y in December 1996, with incidental CSX trackage rights on Neville Island. RailAmerica bought RailTex in February 2000 and sold the PIR that December to Ohio Central, which renamed it the Pittsburgh &amp; Ohio Central. Norfolk Southern took over Conrail's Pittsburgh lines, and the Duff Junction interchange, on 1 June 1999 (${lib("Railroads of the Chartiers Valley")}).`,
  /* The warrants the run can give, for the answer key: a box to a line, as the dispatcher reads it. */
  warrants:[
    {no:"114",at:"Duff Junction",note:"Box 5 reads the next 5-minute mark at least 12 minutes after the call.",
      forms:[{label:"",w:W114("[varies]")}]},
    {no:"118",at:"Bridgeville",note:"Local 2 meets you at Bridgeville, or waits in the Canonsburg siding.",
      forms:[{label:"Local 2 arrives at Bridgeville",w:W118w},{label:"Local 2 is in the Canonsburg siding",w:W118h}]},
    {no:"121",at:"Canonsburg",note:"Men and equipment, or the work train.",
      forms:[{label:"Men and equipment",w:W121a},{label:"Joint with the work train",w:W121b}]},
    {no:"125",at:"Canonsburg",note:"Voids 121 and sends you back to Duff Junction.",forms:[{label:"",w:W125}]}],
  where(S){const G=S.road;return G?G.at:"McKees Rocks"},
  map(S){return map(S)},
  sheet(S){return sheet(S)},

  build(H){
    const S=H.S,rnd=H.rnd,R=()=>H.R();
    const G={pos:MKR,at:POINTS[MKR].n,sig:{},train:null,bag:{},warrants:[],hold:false,box5:0};
    S.road=G;
    const work=["Interchange with Conrail at Duff Junction","Work Bridgeville and meet Local 2","Work Canonsburg",
      "Return and interchange at Duff Junction","Leave the cut for CSX at POV Junction"];

    /* ----- the draws ----- */
    const meet=R()<.5;                       // M: Local 2 arrives at Bridgeville (Box 7), or waits in the Canonsburg siding (Box 8)
    const men=R()<.5;                        // W: Box 12, or Boxes 11 and 17 with the work train
    const waitL=rnd(10,18),waitX=rnd(4,10);
    G.hold=!meet;
    const w118=meet?W118w:W118h,w121=men?W121a:W121b;

    /* ----- every question the draws can reach, listed once for the answer key ----- */
    Object.values(Qs).forEach(H.key);
    H.key(box5Key);H.key(RE.plateQ("none","McKees Rocks","McKees Rocks"));
    const draw=(key,pool,p)=>RE.draw(G,R,H,key,pool,p);

    /* ----- moves ----- */
    const show=()=>{H.renderStatus();H.next()};
    const go=(i,min,note)=>()=>{
      H.addTime(min);G.pos=i;G.at=POINTS[i].n;
      if(note)H.log(note);
      show();
    };
    const seen=(k,arms)=>()=>{G.sig[k]=arms;show()};
    const train=t=>()=>{G.train=t;show()};
    const rel=no=>()=>{TW.release(G,no);H.log("Warrant "+no+" released");show()};
    const eff=no=>()=>{TW.effect(G,no);show()};
    const copy=w=>TW.copy(H,G,Object.assign({to:"PIR Local 1"},w));
    const info=(where,title,html,btn)=>H.info(where,title,html,btn);
    // Box 5: the next 5-minute mark at least 12 minutes after the call
    TW.resetTimes();
    const W114x=W114("");
    const setBox5=()=>{
      const t=Math.ceil((S.clock+12)/5)*5;
      G.box5=t;W114x.boxes[5]=[fmt(t)];TW.addTime(fmt(t));
      H.next();
    };
    const q7=()=>{
      const t=G.box5;
      if(S.clock>=t){H.next();return}   // wrong read-backs can use up the wait: nothing to ask
      const late=`You took the main before ${fmt(t)}. Box 5 kept warrant 114 out of effect until then.`;
      const wait=()=>{if(S.clock<t){H.log("Waited for "+fmt(t));H.addTime(t-S.clock)}};
      return H.ask(Object.assign(box5Q(fmt(t),fmt(S.clock),late),{after:wait}))();
    };

    const steps=[
      info("McKees Rocks","Called for 6:00",`<p>You are the conductor of PIR Local 1, the south turn, called at the McKees Rocks office with two road switchers and a cut of loads and empties. You run to Duff Junction and swap cars with Conrail. You work the mills at Bridgeville and the transformer plant at Canonsburg on the Chartiers track, then come back and leave a cut for CSX at POV Junction. There is no caboose: a rear-end device marks the train (${lib("Railroads of the Chartiers Valley")}).</p><p>The special instructions are on the sheet.</p>`,"Go to the yard"),
      H.ask(Qs.yl),
      go(MKR,5,"Brake test done"),
      info("McKees Rocks","Ready to leave",`<p>The brake test is done and the rear-end device is on the last car. The main runs from the office to Duff Junction, about four miles, inside yard limits with no signals.</p>`),
      go(DUFF,25,"At Duff Junction"),
      info("Duff Junction","The Conrail interchange",`<p>The Conrail local sets out nine cars and lifts six. The interchange is inside yard limits, and the Chartiers track begins at the sign beyond it.</p>`,"Wait for the Conrail local"),
      H.wait(45,"Waited for the Conrail interchange"),H.done(0),
      ...[draw("p1",POOL_1,.6)].filter(Boolean),
      info("Duff Junction","The yard limit sign",`<p>The sign stands at the end of the yard limits. South of it the Chartiers track runs to Arden with no signals, and every move is by track warrant from the dispatcher, whose initials, RK, end each warrant.</p>`,"Call the dispatcher"),
      H.ask(Qs.noWarrant),H.ask(Qs.call),
      setBox5,
      copy(W114x),
      H.ask(Qs.ok),H.ask(Qs.copies),
      q7,
      eff("114"),
      go(CAR,10,"At Carnegie"),
      info("Carnegie","Past Carnegie",`<p>The engineer opens the throttle past Carnegie and the speedometer reaches 25 MPH. Bridgeville is the last named point of the warrant.</p>`),
      H.ask(Qs.box13),
      ...[draw("p2",POOL_2,.7)].filter(Boolean),
      go(BRV,14,"At Bridgeville"),
      info("Bridgeville","Bridgeville",`<p>Bridgeville is the end of warrant 114. The mills are on the siding: a stainless mill and a glass plant. ${meet?"Local 2, the other PIR local, is coming up from Arden.":"Local 2, the other PIR local, has gone ahead to Canonsburg."}</p>`),
      H.ask(Qs.last),
      ...[draw("p3",POOL_3,.6)].filter(Boolean),
      info("Bridgeville","Into the siding",`<p>The cut goes into the siding by the hand-operated switch. The mills are worked from there.</p>`,"Work the mills"),
      H.wait(65,"Worked the mills at Bridgeville"),
      H.ask(Qs.clear),
      rel("114"),
      info("Bridgeville","Warrant 118",`<p>You report clear of 114 and ask the dispatcher for the main to Canonsburg.${meet?" Local 2 is on its way up from Arden and will meet you here.":" Local 2 is waiting in the siding at Canonsburg."}</p>`,"Copy the warrant"),
      copy(w118),
      ...(meet
        ?[H.ask(Qs.box7),H.wait(waitL,"Waited at Bridgeville for Local 2"),
          info("Bridgeville","Local 2 arrives",`<p>Local 2 comes in on the main and clears into the siding.</p>`),
          H.ask(Qs.other),eff("118")]
        :[eff("118"),H.ask(Qs.box8),H.ask(Qs.farSwitch)]),
      H.done(1),
      go(HIL,16,"At Hills"),
      go(CAN,11,"At Canonsburg"),
      rel("118"),
      info("Canonsburg","Canonsburg",`<p>The transformer plant is on the siding at Canonsburg. ${meet?"Warrant 118 ends here, and you report clear of it.":"Local 2 is in the siding with the main clear, and you report clear of 118."} The work is between Hills and Canonsburg, both ways, and the PIR has a work train out on that stretch.</p>`,"Call the dispatcher"),
      H.ask(Qs.box4),
      copy(w121),eff("121"),
      ...(men?[H.ask(Qs.rs)]:[H.ask(Qs.joint)]),
      info("Canonsburg","The plant",`<p>The cut goes to the plant and the empties come out. The work takes about an hour and a half.</p>`,"Work the plant"),
      H.wait(90,"Worked the transformer plant at Canonsburg"),
      info("Canonsburg","Warrant 125",`<p>The work is done. You call the dispatcher for the main back to Duff Junction.</p>`,"Copy the warrant"),
      copy(W125),rel("121"),eff("125"),
      H.ask(Qs.box1),H.ask(Qs.box15),
      H.done(2),
      go(DUFF,55,"At Duff Junction"),
      rel("125"),
      info("Duff Junction","The yard limit sign",`<p>The train is back at the sign and inside the yard limits. Warrant 125 ends here, and you report clear of it. The Conrail local is ready for the cars.</p>`,"Wait for the Conrail local"),
      H.wait(30,"Set out and lifted at the Conrail interchange"),H.done(3),
      go(MKR,25,"At McKees Rocks"),
      seen("dist","D"),
      info("McKees Rocks","The distant signal",`<p>A signal stands beside the main ahead of the diamond, with a D on its plate. The CSX main crosses the PIR a short way on.</p>`),
      H.ask(Qs.dplate),
      go(DIA,3,"At the McKees Rocks diamond"),
      seen("home","RRR"),train("xing"),
      info("McKees Rocks diamond","The diamond",`<p>The PIR crosses the CSX main here, about milepost 3.75 on the former Pittsburgh &amp; Lake Erie. A CSX train is on the diamond and the home signal is against you.</p>`),
      H.ask(RE.plateQ("none","McKees Rocks","McKees Rocks")),
      H.wait(waitX,"Waited at the diamond for the CSX train"),train(null),seen("home","GRR"),
      info("McKees Rocks diamond","The route clears",`<p>The CSX train is clear of the diamond and the operator lines the route. The home signal changes.</p>`),
      go(POV,10,"At POV Junction"),
      info("POV Junction","POV Junction",`<p>The cut goes onto the interchange track at Neville, about P&amp;LE milepost 5.7, for the CSX local.</p>`),
      H.done(4)
    ].filter(Boolean);
    return {work,steps,noPar:true,end:()=>`The cut for CSX is on the interchange track at POV Junction at {t}.${S.clock<=run.end+15?"":" "}`};
  }
};

/* ---------- the map ---------- */
/* An SVG element: attrs in order, self-closed with no inner text. */
const tag=(name,attrs,inner)=>{
  const at=Object.entries(attrs).map(([k,v])=>` ${k}="${v}"`).join("");
  return inner===undefined?`<${name}${at}/>`:`<${name}${at}>${inner}</${name}>`;
};
/* The bar over the track for a warrant in effect, between its points; Box 8 stops short of the last siding switch. */
function authorityBar(G,w){
  const X=i=>POINTS[i].x,[a,b]=AUTH[w.no];
  const x1=X(a),x2=X(b)+(b===CAN&&G.hold&&w.no==="118"?-8:0),xa=Math.min(x1,x2),xb=Math.max(x1,x2);
  return tag("rect",{x:xa,y:78,width:xb-xa,height:3,fill:"var(--rust)"})+
    tag("text",{x:(xa+xb)/2,y:73,"font-size":"5.8","text-anchor":"middle",fill:"var(--rust)","font-weight":700},w.no);
}
function map(S){
  const G=S.road,W=600,P=POINTS[G.pos],X=i=>POINTS[i].x;
  const weight=i=>G.pos===i?700:400;   // a place's label is bold while the engine stands there
  const aria=`Line sketch of the PIR south turn from McKees Rocks to Canonsburg and POV Junction, ${esc(S.def.code)} at ${esc(G.at)}`;
  const water={"font-size":"6.5"};
  const out=[
    `<svg viewBox="0 0 ${W} 122" role="img" aria-label="${aria}">`,
    tag("rect",{x:0,y:0,width:W,height:122,fill:"var(--land)"}),
    tag("path",{d:"M0 36 Q110 24 230 34 T420 30 T600 34",fill:"none",stroke:"var(--river)","stroke-width":3,opacity:".55"}),
    tag("text",{x:8,y:12,...water,class:"water",style:"fill:var(--muted)"},"CHARTIERS CREEK"),
    tag("text",{x:W-8,y:12,...water,"text-anchor":"end",class:"water",style:"fill:var(--muted)"},esc(S.def.year)),
    // yard limits shaded, McKees Rocks to Duff Junction; the dark territory outlined
    tag("rect",{x:380,y:46,width:96,height:52,fill:"var(--sheet-2)"}),
    tag("rect",{x:16,y:76,width:362,height:20,fill:"none",stroke:"var(--muted)","stroke-width":1,"stroke-dasharray":"4 3"}),
    // track: the Chartiers track, the 45 degree climb at Duff Junction, the PIR main to the diamond, the CSX main
    // (heavier), the siding stubs, Conrail
    `<g fill="none" stroke="var(--ink)" stroke-linecap="round" stroke-linejoin="round">`,
    tag("path",{"stroke-width":"2.2",d:`M${X(CAN)-12} 88 H385 L413 60 H482`}),
    tag("path",{"stroke-width":"3.4",d:`M498 60 H${X(POV)+14}`}),
    tag("path",{"stroke-width":"3.4",stroke:"var(--muted)",d:"M474 76 L506 44"}),
    `<g stroke-width="1.4">`,
    ...[CAN,HIL,BRV].map(i=>{const x=X(i);return tag("path",{d:`M${x-12} 88 L${x-6} 82 H${x+6} L${x+12} 88`})}),
    tag("path",{stroke:"var(--muted)",d:"M385 88 L371 74 H356"}),
    `</g></g>`,
    ...G.warrants.filter(w=>w.eff&&!w.released).map(w=>authorityBar(G,w)),
    tag("path",{d:"M490 55 L495 60 L490 65 L485 60 Z",fill:"var(--rust)",opacity:".85",stroke:"var(--ink)","stroke-width":".8"}),
    ...SIGS.map(sg=>RE.sigDots(G,sg)),
    G.train?tag("rect",{x:470,y:55,width:40,height:10,rx:2,fill:"var(--muted)",stroke:"#fff","stroke-width":".8",
      transform:"rotate(-45 490 60)"}):"",
    // labels, clear of track
    `<g class="lbl" font-size="6.3" text-anchor="middle">`,
    tag("text",{x:198,y:66},"DARK TERRITORY · TRACK WARRANTS"),
    ...[[CAN,"CANONSBURG",108],[HIL,"HILLS",118],[BRV,"BRIDGEVILLE",108],[CAR,"CARNEGIE",118],[DUFF,"DUFF JUNCTION",108]]
      .map(([i,t,y])=>tag("text",{x:X(i),y,"font-weight":weight(i)},t)),
    tag("text",{x:350,y:68,"text-anchor":"end"},"CONRAIL"),
    tag("text",{x:440,y:76,"font-weight":weight(MKR)},"MCKEES ROCKS"),
    tag("text",{x:490,y:86,"font-weight":weight(DIA)},"DIAMOND · P&amp;LE MP 3.75"),
    tag("text",{x:W-8,y:76,"text-anchor":"end","font-weight":weight(POV)},"POV JCT · P&amp;LE MP 5.7"),
    tag("text",{x:522,y:36},"CSX"),
    `</g>`,
    // the engine
    `<g transform="translate(${P.x} ${P.y-1})">`,
    tag("rect",{x:-13,y:-5,width:26,height:10,rx:2,fill:"var(--green)",stroke:"var(--glow)","stroke-width":"1.4"}),
    tag("text",{x:0,y:"2.4","font-size":"6.4","text-anchor":"middle",fill:"#fff","font-weight":700},"PIR"),
    `</g></svg>`];
  return out.join("");
}

/* ---------- the sheet ---------- */
/* The special instructions, as the sheet lists them. */
const SPECIAL_INSTRUCTIONS=`<ul>${[
  `Rules: yard limits, warrants and crew duties by the GCOR; the boxes of the warrant form by the track warrant guide; the plates on signals by the Signals guide.`,
  `McKees Rocks to Duff Junction: yard limits, no signals.`,
  `Duff Junction to Arden: track warrant control, no signals. Sidings at Bridgeville, Hills, Canonsburg, Houston and Arden.`,
  `Mileposts from Carnegie: Bridgeville 4.0, Hills 8.6, Canonsburg 11.8, Houston 15.3, Arden 20.0.`,
  `McKees Rocks, about P&amp;LE MP 3.75: crossing of the CSX main, an interlocking with a distant signal.`,
  `Neville, POV Junction, about P&amp;LE MP 5.7: interchange with CSX. Interchange with Conrail at Duff Junction.`,
].map(t=>`<li>${t}</li>`).join("")}</ul>`;
/* The special instructions, the warrants held, and the work. */
function sheet(S){
  const G=S.road;if(!G)return "";
  let h=`<h3>PIR Chartiers Subdivision</h3><div class="sub">Special instructions · McKees Rocks to Canonsburg · ${esc(S.def.dateLine)}</div>`;
  h+=`<div class="xw-si"><b>Special instructions</b>${SPECIAL_INSTRUCTIONS}</div>`;
  h+=TW.held(G);
  h+=`<div class="xw-orders"><b>Work</b>${S.jobs.map(j=>`<div class="ord${j.done?" done":""}">${j.done?"✓ ":""}${esc(j.t)}</div>`).join("")}</div>`;
  return h;
}

/* The points' names, for the play test's check that they are spelled as road-engine.js ST spells its stations. */
RE.pirPoints=Object.freeze(POINTS.map(p=>p.n));
window.NevilleRuns=Object.assign(window.NevilleRuns||{},{pir:run});
})();
