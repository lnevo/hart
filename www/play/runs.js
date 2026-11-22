/* The shifts of Extra East: Neville Island. The jobs, their hours, the tracks and the moves come from
   Mark Connolly's P&OV blog (see library/pittsburgh-ohio-valley-railway.html); the order of each shift,
   the draws and the events around them are invented for the game. Each decision names its source:
   GC/YL are the C&E study deck's GCOR and Yard Limits cards, PV a post on the blog.
   Plant names follow the year of each shift (data/plants-lineage.json). */
(function(){
"use strict";
/* ---------- decisions shared by several shifts (GCOR, in the study deck's words) ---------- */
const Q={
  speed:{sec:"gcor",src:"GC · 6.28",title:"Speed on plant track",right:"A speed that allows stopping within half the range of vision",
    wrong:[["Restricted speed, not over 20 MPH, looking out for broken rail"],["Not over 10 MPH, whatever the view ahead"],["Yard speed, unless the track is known to be clear"]],
    why:"GCOR 6.28: except on a main track or where a block system is in effect, move at a speed that allows stopping within half the range of vision short of a train, engine, car, men or equipment fouling the track, stop signal, or derail or switch lined improperly."},
  clear:{sec:"def",src:"GC · Glossary",title:"Clear of the switch",right:"Clear of the clearance point: where it is safe for equipment, and a person riding the side of equipment, to pass on the adjacent track",
    wrong:[["Just past the switch points"],["One car length from the switch, whatever the track"],["Anywhere, as long as the switch is lined back"]],
    why:"GCOR glossary: the clearance point is the location closest to a switch where it is safe for equipment, and a person riding the side of equipment, to pass equipment on an adjacent track."},
  foul:{sec:"def",src:"GC · Glossary",title:"Left short",right:"Equipment fouling a track",
    wrong:[["A cut in the clear"],["A reverse movement"],["Working limits"]],
    why:"GCOR glossary: equipment fouling a track is the end of rolling equipment left between the clearance point and the switch points leading to the track on which the equipment is standing."},
  men:{sec:"sig",src:"GC · 5.8.2",title:"The track gang",right:"Long, short (— o), then two shorts (o o) at intervals until the head end has passed them",
    wrong:[["A succession of short sounds"],["Two long sounds"],["Nothing: plant track has no whistle rules"]],
    why:"GCOR 5.8.2, signal (8): approaching men or equipment on or near the track, regardless of whistle prohibitions, sound — o, then (4) intermittently until the head end has passed them."},
  before:{sec:"sig",src:"GC · 5.8.2",title:"Before moving",right:"Sound the required whistle signal before moving",
    wrong:[["Nothing: these are not main tracks"],["Move at restricted speed without a signal"],["Ring the bell only"]],
    why:"GCOR 5.8.2: the whistle may be used at any time as a warning regardless of any whistle prohibitions. When other employees are working in the immediate area, sound the required whistle signal before moving."},
  variable:{sec:"def",src:"GC · Glossary",title:"The switch with the yellow bowl",right:"Where the wheels forced them, so it must be lined back by hand",
    wrong:[["Back in their first position, returned by a spring"],["Locked in the reversed position"],["Half open, until the next movement"]],
    why:"GCOR glossary: a variable switch, marked with a V or a bowl painted yellow, leaves the points where they were forced when it is trailed through. A spring switch returns them to their original position."},
  working:{sec:"def",src:"GC · Glossary",title:"Working limits",right:"Only as permitted by the employee in charge of the working limits",
    wrong:[["At restricted speed, not over 20 MPH"],["Freely, since it is not main track"],["Only after sounding signal (8)"]],
    why:"GCOR glossary: working limits are a segment of track within definite boundaries on which movements may be made only as permitted by the employee in charge."},
  conductor:{sec:"gcor",src:"GC · 1.47A",title:"Whose instructions?",right:"The conductor's, unless they endanger the safety of the train or violate the rules",
    wrong:[["The engineer's, on everything"],["The brakeman's, who is on the ground"],["The senior man's, whatever his job"]],
    why:"GCOR 1.47A: the conductor supervises the operation and administration of the train; everyone on it obeys the conductor's instructions unless they endanger the train's safety or violate the rules. On operating the engine itself, the crew obey the engineer (1.47B)."}
};
const ask=(H,base,o)=>H.ask(Object.assign({},base,o));
/* plant names by year, from the industry chart */
const plants=y=>[
  y<1990?"Shenango Inc.: coke plant, blast furnaces A and B, and the pig machine at A":"Shenango Inc.: coke plant and B furnace; A is being cut up",
  y<1990?"Shenango-Penn foundry, about two miles west":"Shenango-Penn foundry, closed 30 November 1990",
  y<1982?"Marquette Cement (Gulf & Western), tower on the East Runner":"Lone Star Cement, tower on the East Runner",
  y<1986?"USS Chemicals, the chemical plant":"Aristech Chemical, the chemical plant",
  y<1985?"Calgon Corporation (Merck), activated carbon":"Calgon Carbon, activated carbon",
  "A. Stucki, an occasional boxcar",
  "PC&Y at the Y Interchange: half P&LE, half "+(y<1976?"Penn Central":"Conrail")];
const SI=["Plant tracks are not main track. Off the East Runner Main, GCOR 6.28 applies.",
  "For the game: the East Runner Main is main track inside yard limits (GCOR 6.13). There are no block signals.",
  "Weigh what the switching order says at the yard office scale. Cars cross it at a walk."];

const NevilleRuns={

/* ===================== #105, the ore job ===================== */
j105:{pace:4,code:"#105",name:"ore job",year:"1981",dateLine:"a weekday in 1981",start:420,end:930,engine:"#4",units:{"#4":"syard"},
  cement:"Marquette",plants:plants(1981),si:SI,endPlace:"West Yard",
  tieUp:"#105 tied up at {t}.",
  coda:"The ore job was the one men wanted: daylight, Monday to Friday, on the clean end of the plant, and the senior men held it. In the early 1980s its engine was SW9 #4 (<a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/809168349703602176\" rel=\"noopener\">p.2</a>, <a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/96556993685\" rel=\"noopener\">p.37</a>).",
  build(H){
    const drags=H.rnd(2,3),gang=H.R()<.5,relief=H.R()<.5;
    const work=["Make up a ten-car ore drag on the South Runner"];
    for(let i=1;i<=drags;i++)work.push(`Shove drag ${i} of ${drags} to the car dumper`);
    work.push("Fuel #4 at South Yard between trips","Tie up in the West Yard by 3:30");
    const steps=[
      H.info("South Yard","On duty, 7:00",`<p>You are the conductor of #105, the ore job, with SW9 #4. Iron ore for Shenango's blast furnaces comes onto the island over the PC&amp;Y from Scully Yard. Your job shoves it from the West Yard to the Shenango car dumper in ten-car drags.</p><p>The trainmaster has written today's switching orders: ${drags} drags. Mark Connolly called this the clean end of the plant.</p>`,"Go to work"),
      ask(H,Q.conductor,{body:"Your brakeman is new to #105 and the engineer has his own way of making up a drag. For the work on the switching order, whose instructions do they follow?"}),
      ask(H,Q.before,{title:gang?"The track gang at S1":"The car knocker",body:gang?"The track gang is working at the west end of S1, beside the South Runner. #4 is ready to move. What does the engineer do first?":"The car knocker is inspecting hoppers on the next track. #4 is ready to move. What does the engineer do first?"}),
      H.mv("srun",14,"Ten loads made up on the South Runner"),H.done(0),
      H.ask({sec:"pov",src:"PV p.84",url:"46501750755",title:"Where the brakeman rides",body:"The drag is ready: ten loaded hoppers, #4 on the west end, shoving east toward the dumper. Where is the brakeman supposed to ride?",
        right:"On the fifth car",wrong:[["In the cab, out of the ore dust",{min:5,marks:1},"Mark Connolly's caption: the brakeman was supposed to ride the fifth car, \"but we all know that if you hide in the cab you become invisible and no one in the yard office can see you.\""],["On the last car, next to the engine"],["On the ground, walking ahead of the shove"]],
        why:"On #105 the brakeman was supposed to ride the fifth car of the ore drag."}),
      H.ask({sec:"sig",src:"GC · 5.8.2",title:"Backing up",body:"#4 stands with its cab to the east, coupled to the drag. To shove east toward the dumper, the engine backs up. Which whistle signal does the engineer sound before the move?",
        right:"Three short sounds (o o o): when stopped, back up",wrong:[["Two long sounds (— —): release brakes, proceed"],["Two short sounds (o o): acknowledgment"],["One long sound (—): air brakes applied"]],
        why:"GCOR 5.8.2: (5) o o o, when stopped, back up. (3) — — is release brakes and proceed, (4) o o an acknowledgment, (2) — air brakes applied, pressure equalized."}),
      ask(H,Q.speed,{title:"Up to the coke yard switch",body:"You shove the drag along the plant tracks toward the coke yard switch. This is not main track and there are no block signals. At what speed?"}),
      H.mv("cokelead",10,"Drag 1 at the coke yard switch"),
      ask(H,Q.variable,{body:"The coke yard switch has its bowl painted yellow. The brakeman calls that the drag trailed through it on the last trip and nobody lined it back. Where are its points?"}),
      H.mv("dumper",8,"Drag 1 shoved up to the car dumper"),H.done(1),
      H.ask({sec:"pov",src:"PV p.39",url:"87216028880",title:"Coming down from the dumper",body:"At the dumper the hoppers are turned over on E2. How do the empties get back down the hill?",
        right:"A car rider rides them down in strings, braking by hand",wrong:[["#4 pulls each empty back off the trestle"],["They roll down by themselves into the East Yard"],["The Shenango transfer car carries them down"]],
        why:"The car riders worked the dumper side and rode the empties down the hill in strings, braking by hand. John Iwanonkiw was a car rider."}),
      H.info("furnace lead","Coffee",`<p>Mid-morning. After a drag to the dumper, around 10:00 or 10:30, the ore job stopped at the millwrights on the furnace lead and brought coffee back for the yard office. A four-cup holder hung on the bulletin board there.</p>`,"Back to work",()=>{H.addTime(10);H.S.parAdd+=10*H.S.pace;H.log("Coffee from the millwrights for the yard office")}),
      H.mv("syard",10,"#4 fueled at South Yard"),H.done(drags+1),
      H.ask({sec:"pov",src:"PV p.58",url:"61429804213",title:"Between trips",body:"Between drags #4 needs fuel. Where does the ore job's engine take it?",
        right:"In the South Yard",wrong:[["At the P&LE shop in McKees Rocks"],["At the scale house, by the bucket"],["On E1 by the river"]],
        why:"Captions show the ore job's engine spotted for fuel in the South Yard between trips. Sand went on at S9 by the bucket, and heavy repairs went to the P&LE shops in McKees Rocks."}),
      H.mv("srun",8,"Drag 2 made up"),
      ask(H,Q.men,{title:"Men by the coke plant lead",body:"Shoving drag 2, you come up on the track gang working beside the coke plant lead. What does the engineer sound?"}),
      H.mv("dumper",16,"Drag 2 at the car dumper"),H.done(2)
    ];
    if(drags===3)steps.push(
      H.mv("srun",14,"Drag 3 made up"),
      H.ask({sec:"sig",src:"GC · 5.8.1",title:"The main crossing",body:"Drag 3 goes over the main crossing, the road crossing by the yard office. When does the engineer ring the bell?",
        right:"Start at the crossing sign and ring until the crossing is occupied",wrong:[["Only if road traffic is in sight"],["Only on a train, not an engine with cars"],["From the yard office to the dumper, the whole way"]],
        why:"GCOR 5.8.1: ring the bell before moving (except momentary stop-and-start switching), as a warning when necessary, approaching men or equipment, and approaching public crossings, starting at the sign and ringing until the crossing is occupied."}),
      H.mv("dumper",16,"Drag 3 at the car dumper"),H.done(3));
    steps.push(ask(H,Q.clear,{title:"The last empties",body:"The last string of empties comes down and you set it on the West Yard track off the ladder. Where must the last car stand?"}),
      H.mv("wyard",12,"Empties set over in the West Yard"));
    if(relief)steps.push(H.info("West Yard","Relief on the footboard",`<p>The second-trick crew comes out early. Their engineer steps up on the footboard and offers to take the last move so your crew can get home a little early. Crews on the P&amp;OV did that for each other: weigh the cars, or take one more drag.</p>`,"Take the early quit",()=>{H.addTime(-8);H.S.parAdd-=8*H.S.pace;H.log("Relieved on the footboard: an early quit")}));
    steps.push(H.done(drags+2));
    return {work,steps,end:()=>relief?"#105 tied up at {t}: an early quit.":"#105 tied up at {t}."};
  }},

/* ===================== #110, the furnace job ===================== */
j110:{pace:3.5,code:"#110",name:"furnace job",year:"1984",dateLine:"January 1984",start:420,end:930,engine:"#6",units:{"#6":"eyard"},
  cement:"Lone Star",plants:plants(1984),si:SI,endPlace:"East Yard",tieUp:"#110 tied up at {t}.",
  coda:"The furnace job worked the east end, which Mark Connolly called a graphite and coke dust area: the two blast furnaces, the pig machine and the coke plant. John Doubt ran it often enough that a caption names it the Furnace Job (<a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/809168349703602176\" rel=\"noopener\">p.2</a>, <a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/44864748783\" rel=\"noopener\">p.139</a>).",
  build(H){
    const ladles=3,spread=H.R()<.6,cast=H.pick(["9:40","10:10","10:40"]);
    const work=["Pull furnace coke at the battery, weigh it, take it to F1","Switch the ladles into the furnace's order","Take three ladles of hot metal out of the ladle house","Pull the two loads at the A pig machine; spot pig iron on E1","Bring the empty pig gons out of the East Yard"];
    const steps=[
      H.info("East Yard","On duty, 7:00",`<p>January 1984, daylight. You are the conductor of #110, the furnace job. The blog names no engine for it; the game gives you SW9 #6. Your territory is the east end: Shenango's two blast furnaces, A and B, the pig machine at A, the ladle house and the coke battery.</p><p>The trainmaster's orders say B furnace will cast about ${cast}. Before then the furnace needs its coke and its ladles in order.</p>`,"Go to work"),
      H.mv("coke",8,"At the coke battery"),
      H.ask({sec:"pov",src:"PV p.130",url:"45184819646",title:"Furnace coke",body:"You pull a string of furnace coke from the battery. Where does it go before F1 at the furnace?",
        right:"Across the yard office scale, to be weighed",wrong:[["Straight to F1: the furnace weighs its own coke"],["To the Y Interchange for the PC&Y"],["To E1 for the barge"]],
        why:"Furnace coke was pulled from the Shenango coke plant, weighed on the yard office scale, and taken to F1 at the blast furnace. Almost every P&OV car crossed that scale."}),
      H.mv("xing",8),
      H.ask({sec:"sig",src:"GC · 5.8.1",title:"The main crossing",body:"The coke string comes up to the main crossing, the road crossing by the yard office. When does the engineer ring the bell?",
        right:"Start at the crossing sign and ring until the crossing is occupied",wrong:[["Only if road traffic is in sight"],["Only on a train, not an engine with cars"],["Not at all on plant track"]],
        why:"GCOR 5.8.1: ring the bell approaching public crossings, starting at the sign and ringing until the crossing is occupied."}),
      H.mv("scale",4),
      H.ask({sec:"pov",src:"PV p.95",url:"45908061832",title:"On the Toledo scale",body:"The coke string is on the scale at the yard office. The trainmaster is at the beam. What does the crew do now?",
        right:"Cut away and back the engine off the scale; the weight is read as soon as it is clear",wrong:[["Stay coupled, so the engine is weighed with the cars"],["Roll the whole string across without stopping"],["Uncouple every car and weigh them one at a time with the brakeman's help"]],
        why:"Mark Connolly on the weighers: \"You no sooner cut away and backed off the scale and bam the buzzer was off.\" Wayne Amber, Bill McEwen and Denny Jarvis could weigh anything in a heartbeat."}),
      H.mv("f1",10,"Furnace coke spotted on F1"),
      H.ask({sec:"pov",src:"PV p.130",url:"45184819646",title:"Up to F1",body:"Shoving the coke to F1, the furnace job lines the crossing for the move. Who rides the lead hopper?",
        right:"The conductor",wrong:[["The car rider from the dumper"],["Nobody: the engineer watches from the cab"],["A Shenango furnace hand"]],
        why:"On the coke move to F1 the furnace job lined the crossing, and the conductor rode the lead hopper. Sam Lacenere is pictured doing it."}),
      H.done(0),
      H.ask({sec:"pov",src:"PV p.91",url:"46331368911",title:"Ladles in order",body:"The ladles are rarely in the order the furnace wants. Where are they switched into order before they are spotted for the cast?",
        right:"From E6 to E4",wrong:[["On E9, the heat track"],["On E1, by the river"],["At the Y Interchange"]],
        why:"Ladles were switched from E6 to E4 to spot for the furnace cast, because they were rarely in the order the furnace wanted. E9 was the heat track, where they were heated first."}),
      H.mv("eyard",12,"Ladles switched E6 to E4"),H.done(1)
    ];
    if(spread)steps.push(
      H.info("East Yard","E9 has spread",`<p>On E9, the heat track in the East Yard scrap yard, ladles stand until they are very hot. This January the heat has spread the rails. In January 1984 that happened on the real E9 (<a href="https://www.tumblr.com/pittsburghohiovalleyrailroad/47021729095" rel="noopener">p.77</a>). The track gang comes out and puts working limits on E9.</p>`),
      ask(H,Q.working,{title:"Working limits on E9",body:"You need one more hot ladle off E9. The track gang's foreman has working limits on the track. How may #6 move inside them?"}));
    steps.push(
      H.mv("ladle",6,"At the ladle house"),
      H.ask({sec:"pov",src:"PV p.14",url:"139367141870",title:"Out of the house",body:"You switch hot metal out of the ladle house. How many ladles at a time, and what is the weight a worry for?",
        right:"Two at a time; with too much weight the cut can run on to the quench car at the battery",wrong:[["Four at a time, to save trips",{min:10,marks:1}],["One at a time, because of the crane"],["Two at a time, because the scale takes only two"]],
        why:"Hot metal left the ladle house two ladles at a time, and the crew had to watch the weight or the cut would reach the quench car at the battery."}),
      H.ask({sec:"pov",src:"PV p.14",url:"139367141870",title:"B is still casting",body:`It is past ${cast} and B furnace has not finished its cast. Where does the crew wait?`,
        right:"At the rear of the Furnace Runner, short of the bumping block",wrong:[["On F1, beside the furnace"],["On the East Runner Main"],["Inside the ladle house"]],
        why:"While B furnace finished a cast, the crew waited at the rear of the Furnace Runner, short of the bumping block."}),
      H.mv("bump",14,"B furnace cast; ladles spotted"),
      H.ask({sec:"pov",src:"PV p.138",url:"44865298831",title:"The split",body:"Three ladles of hot metal are out of the house. What is the usual split?",
        right:"One to the foundry, one to the pig machine, one for recast",
        wrong:[["All of them to the pig machine"],["All of them to the foundry"],["Half to the barge on E1"]],
        why:"Mark Connolly's split: one to the foundry, one to the pig machine, one for recast."}),
      H.mv("gulf",16,"Foundry ladle out by the pig-yard lead"),
      H.ask({sec:"sig",src:"GC · 5.8.2(7)",title:"The Gulf Crossing",body:"Iron for the foundry, at the other end of the island, leaves by the pig-yard lead at the Gulf Crossing. Your move starts a few car lengths from the crossing. No road traffic is approaching or stopped there. Must the crossing signal start 15 seconds before you enter?",
        right:"No: starting less than 1/4 mile away, it may be sounded less than 15 seconds before when no traffic is approaching or stopped",wrong:[["Yes: always 15 to 20 seconds"],["Yes, and from 1/4 mile away"],["No signal is needed at a plant crossing"]],
        why:"GCOR 5.8.2(7): when a movement starts less than 1/4 mile from a crossing, the signal may be sounded less than 15 seconds before the crossing when it is clearly seen traffic is not approaching or stopped at the crossing, or when crossing gates are fully lowered."}),
      H.mv("yint",6,"At the Y Interchange"),
      H.ask({sec:"pov",src:"PV p.105",url:"45668500339",title:"At the Y Interchange",body:"Empty ladles and gons change roads with the PC&Y just west of the Gulf Crossing. What do the crews do to them there before they move?",
        right:"Bleed them: release the air",wrong:[["Weigh them on the interchange track"],["Set every hand brake"],["Nothing; the PC&Y does it all"]],
        why:"At the Y Interchange crews bled the ladles and gons, releasing the air, before they moved. John Iwanonkiw is pictured doing it."}),
      H.done(2),
      H.mv("pig",18,"At the A furnace pig machine"),
      H.ask({sec:"pov",src:"PV p.110",url:"45279964421",title:"The pig machine",body:"At A furnace the pig machine drops bars into gondolas, two loads at a time. You pull the two loads. What must stay clear of the East Runner?",
        right:"The safety car",wrong:[["The empty ladles"],["Nothing: the East Runner is plant track"],["Only the engine"]],
        why:"The crew pulled the two loads and kept the safety car clear of the East Runner."}),
      H.mv("e1",8,"Pig iron spotted on E1 for the barge"),
      ask(H,Q.foul,{title:"On E1's grade",body:"E1 is a steep grade with a lot of weight on it. You leave the pig iron loads there for the barge, but the last car stands between the clearance point and the switch points of E1. What is that?",src:"GC · Glossary"}),
      H.done(3),
      H.mv("eyard",12,"Empty pig gons out of the East Yard"),H.done(4));
    return {work,steps};
  }},

/* ===================== #115, the relief job ===================== */
j115:{pace:3.5,code:"#115",name:"relief job",year:"1979",dateLine:"a Saturday in August 1979",start:420,end:930,engine:"#6",units:{"#6":"syard"},
  cement:"Marquette",plants:plants(1979),si:SI,endPlace:"South Yard",tieUp:"#115 tied up at {t}.",
  coda:"Mark Connolly lists the relief job's week: Monday and Tuesday midnight, Wednesday on the second trick, Saturday and Sunday daylight. In August 1979 Larry Obusek had SW9 #6 on it, with Joe Adamcik on the front of the engine, about to roll across the scale (<a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/45196985396\" rel=\"noopener\">p.126</a>).",
  build(H){
    const tanks=H.rnd(2,4),signal=H.R()<.5;
    const work=["Shove one ore drag to the car dumper",`Run around ${tanks} outbound tank cars from the chemical plant`,"Weigh the tank cars and set them out for the PC&Y","Furnace coke to F1"];
    const steps=[
      H.info("South Yard","Saturday, 7:00",`<p>August 1979. #105 and #110 are off on weekends, so #115, the relief job, is the daylight crew today and works east or west as the plant needs. You have SW9 #6.</p><p>No trainmaster is on duty this Saturday. His switching orders were written on Friday.</p>`,"Go to work"),
      H.ask({sec:"yl",src:"YL",title:"Who is in charge?",body:"With no trainmaster or yardmaster on duty, who is generally in charge inside the yard limits?",
        right:"The conductor or switch crew foreman of the first train there",wrong:[["Whoever has the most seniority on the island"],["The PC&Y crew, as the connecting road"],["Nobody; every crew works alone"]],
        why:"Yard Limits guide: inside yard limits the yardmaster or agent is in charge if one is on duty; otherwise generally the conductor or switch crew foreman of the first train there."}),
      H.mv("srun",14,"Ore drag made up"),
      H.ask({sec:"def",src:"GC · Glossary",title:"Who is crew?",body:"The car knocker, the yard clerk and your brakeman are all at South Yard this morning. Which of them is a crew member under GCOR?",
        right:"The brakeman",wrong:[["The car knocker"],["The yard clerk"],["All three"]],
        why:"GCOR glossary: crew members are conductors, assistant conductors, brakemen, engineers, remote control operators, yard engine foremen, switchmen, and yard helpers."}),
      H.ask({sec:"sig",src:"GC · 5.8.2",title:"Lost in the dust",body:"Shoving toward the dumper, the engineer loses sight of the brakeman's hand signal in the dust and cannot tell what it was. Which whistle signal asks for it again?",
        right:"Four short sounds (o o o o): request for a signal to be given or repeated",wrong:[["Two short sounds (o o)"],["Three short sounds (o o o)"],["A succession of short sounds"]],
        why:"GCOR 5.8.2: (6) o o o o, request for a signal to be given or repeated. (4) o o is an acknowledgment and (5) o o o is back up."}),
      H.mv("dumper",16,"Ore drag at the dumper"),H.done(0),
      H.mv("chem",14,"At the chemical plant"),
      H.ask({sec:"gcor",src:"GC · 1.47B",title:"Tank cars",body:`${tanks} loaded tank cars from USS Chemicals are going out to the PC&Y. What must the engineer check with the conductor before handling them?`,
        right:"Whether any cars need special handling",wrong:[["Only the car numbers for the time sheet"],["Nothing: that is the conductor's paperwork"],["The weights, before they are weighed"]],
        why:"GCOR 1.47B: the engineer must check with the conductor whether any cars or units need special handling."}),
      H.mv("s9",8),
      H.ask({sec:"pov",src:"PV p.90",url:"46415908175",title:"Run around them",body:"The engine has to get to the other end of the tank cars. Where does it run around them?",
        right:"On S9, just west of the scale",wrong:[["On E1"],["On the dumper track, E2"],["At the Y Interchange"]],
        why:"S9, just west of the scale, was the run-around for outbound tank cars, and also the sand spot."}),
      H.done(1),
      signal?H.ask({sec:"gcor",src:"GC · 6.28",title:"The scale is thrown red",body:"You start to roll the tank cars toward the scale. The signal at the scale has been thrown red. What do you do?",
        right:"Stop short of it: the move must be able to stop short of a stop signal",wrong:[["Keep rolling at a walk: it only means weighing is in progress",{min:10,marks:2}],["Sound two shorts and go across"],["Back off and go around by the East Runner"]],
        why:"GCOR 6.28: off main track, move at a speed that allows stopping within half the range of vision short of a train, engine, car, men or equipment fouling the track, stop signal, or derail or switch lined improperly. Mark Connolly thought the scale had been thrown red in the 1979 photo of #6."})
        :H.ask({sec:"pov",src:"PV p.95",url:"45908061832",title:"Weighing",body:"The tank cars go over the scale. When is each weight read?",
        right:"As soon as the cars are clear of the engine: cut away, back off, and the buzzer goes",wrong:[["After the whole cut has stood on the scale for a minute"],["At the PC&Y's own scale, later"],["When the engine is on the scale with them"]],
        why:"\"You no sooner cut away and backed off the scale and bam the buzzer was off.\""}),
      H.mv("scale",8,"Tank cars weighed"),
      H.mv("yint",16,"Tank cars set out for the PC&Y"),
      ask(H,Q.clear,{title:"For the PC&Y",body:"You set the tank cars on the interchange track for the PC&Y. Where must the last car stand?"}),
      H.done(2),
      H.mv("coke",18,"At the coke battery"),
      H.mv("scale",12,"Furnace coke weighed"),
      ask(H,Q.speed,{title:"Up the furnace lead",body:"You take the weighed coke up the furnace lead to F1. No block signals, not main track. At what speed?"}),
      H.mv("f1",12,"Furnace coke spotted on F1"),H.done(3)
    ];
    return {work,steps};
  }},

/* ===================== #205, second trick ===================== */
j205:{pace:3,code:"#205",name:"second trick",year:"1987",dateLine:"an evening in 1987",start:960,end:1440,engine:"#3",units:{"#3":"scale"},
  cement:"Lone Star",plants:plants(1987),si:SI,endPlace:"the yard office",tieUp:"#205 tied up at {t}.",
  coda:"Elmer Picard held the second trick as a steady job and came to work in a sport coat and tie. Mark Connolly said he looked like he owned the place when he filled out his time sheet (<a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/44871790060\" rel=\"noopener\">p.67</a>).",
  build(H){
    const crane=H.R()<.6,boxcar=H.R()<.6;
    const work=["Pull the interchange from the PC&Y at the Y Interchange","Weigh the interchange at the yard office"];
    if(boxcar)work.push("Spot a boxcar at Stucki");
    work.push("Run around the Aristech tank cars on S9","Empty ladles back to the Y Interchange","Tie up by midnight");
    const steps=[
      H.info("the yard office","On duty, 4:00 p.m.",`<p>1987. You are the conductor of #205, the second trick: 4:00 p.m. to midnight, east end and west end as the plant needs. You have switcher #3. On the bulletin board in the yard office are the trainmaster's switching orders for the night, a lantern, the base radio and the track cards.</p>`,"Go to work"),
      H.ask({sec:"gcor",src:"GC · 1.46",title:"The trainmaster's orders",body:"For the game, a yardmaster is on duty tonight. Under GCOR, whose instructions do the yard crews follow?",
        right:"The yardmaster's: he directly supervises the yard crews",wrong:[["The conductor's, on everything"],["The PC&Y conductor's at the interchange"],["The engineer's, who runs the engine"]],
        why:"GCOR 1.46: the yardmaster directly supervises yard crews, clerks and others in the yard, and where a yardmaster is on duty, train, engine and yard crews follow the yardmaster's instructions. On the P&OV the trainmaster wrote the switching orders."}),
      H.mv("yint",16,"Interchange pulled from the Y"),
      H.ask({sec:"sig",src:"GC · 5.8.2",title:"A lantern in the dusk",body:"The brakeman gives a lantern signal that the engineer understands and there is no whistle signal for it. How does the engineer acknowledge it?",
        right:"Two short sounds (o o)",wrong:[["Two long sounds (— —)"],["One long sound (—)"],["Four short sounds (o o o o)"]],
        why:"GCOR 5.8.2: (4) o o, acknowledgment of any signal not otherwise provided for."}),
      H.mv("scale",16,"Interchange weighed"),H.done(0),H.done(1)
    ];
    if(boxcar)steps.push(H.mv("stucki",14,"Boxcar spotted at Stucki"),
      ask(H,Q.clear,{title:"At Stucki",body:"An occasional boxcar for Stucki. You spot it at the plant. Where must it stand so the next move can pass it?",src:"GC · Glossary"}),H.done(2));
    const k=boxcar?3:2;
    steps.push(
      H.mv("chem",12,"At Aristech"),
      ask(H,Q.before,{title:"The car knocker at Aristech",body:"The car knocker is still working between two of the Aristech tank cars when your engine is ready to couple. What does the engineer do first?"}),
      H.ask({sec:"gcor",src:"GC · 1.47A",title:"A restriction on a car",body:"The car knocker has put a restriction on one of the Aristech tank cars. What must the conductor do with it?",
        right:"Advise the engineer of the restriction",wrong:[["Nothing: the car knocker's tag is enough"],["Leave the car where it stands without telling anyone"],["Tell the PC&Y crew only, when the car is handed over"]],
        why:"GCOR 1.47A: the conductor must advise the engineer and train dispatcher of any restriction placed on equipment being handled."}),
      H.mv("s9",8,"Tank cars run around on S9"),H.done(k),
      H.info("East Runner","Dark on the East Runner","<p>It is dark when you head east along the back channel on the East Runner Main, past the Lone Star cement tower toward the ladle house.</p>"),
      H.ask({sec:"yl",src:"GC · 6.13",title:"No block signals",body:"For the game the East Runner Main is main track inside yard limits, with no block signals. At what speed do you run?",
        right:"Restricted speed: able to stop within half the range of vision, not over 20 MPH",wrong:[["Track speed, since no train is lined up against you"],["Any speed: yard limits need no protection"],["10 MPH, as on a yard track"]],
        why:"GCOR 6.13: within yard limits, all movements at restricted speed unless under a block signal more favorable than Approach. GCOR 6.27: restricted speed allows stopping within half the range of vision, looking out for broken rail, not over 20 MPH."}));
    if(crane)steps.push(H.info("East Runner","A crane on the main",`<p>Your headlight picks up a Shenango track crane, hung up on the East Runner Main with five loads. At restricted speed you stop short of it. In 1987 Jack Burik found the same thing there; the union grieved it and won (<a href="https://www.tumblr.com/pittsburghohiovalleyrailroad/65065960371" rel="noopener">p.49</a>).</p><p>You wait while it is moved.</p>`,"Wait it out",()=>{H.addTime(25);H.S.parAdd+=25*H.S.pace;H.log("Held for the Shenango crane on the East Runner")}));
    steps.push(
      H.mv("ladle",14,"Empty ladles lifted at the house"),
      H.ask({sec:"sig",src:"GC · 5.8.3",title:"The whistle fails",body:"At 10 p.m. #3's whistle fails, and there is no other unit to lead. You still have the main crossing ahead. What now?",
        right:"Continue with the bell ringing continuously, and stop before each public crossing so a crew member can warn traffic",wrong:[["Tie up: an engine may not move without a whistle"],["Continue normally and use the radio at crossings"],["Run through the crossing quickly to keep clear of traffic"]],
        why:"GCOR 5.8.3: if no other unit can lead, continue with the bell ringing continuously and stop before each public crossing so a crew member can warn traffic, unless the gates are fully down or no traffic is approaching or stopped."}),
      H.ask({sec:"sig",src:"GC · 5.8.2",title:"Someone on the track",body:"Pulling the empty ladles west in the dark, you see a man walking on the track ahead, not at a crossing. What does the engineer sound?",
        right:"A succession of short sounds",wrong:[["Two long sounds"],["Long, short (— o)"],["Nothing; just ring the bell"]],
        why:"GCOR 5.8.2: (1) a succession of short sounds, persons or livestock on the track other than at crossings, or warning employees of an emergency."}),
      H.mv("yint",22,"Empty ladles set at the Y for the PC&Y"),H.done(k+1),
      H.mv("scale",16,"Back at the yard office"),H.done(k+2));
    return {work,steps};
  }},

/* ===================== #305, midnight ===================== */
j305:{pace:3.2,code:"#305",name:"midnight job",year:"early 1980s",dateLine:"a winter night, early 1980s",start:0,end:420,engine:"#3",units:{"#3":"scale"},
  cement:"Marquette",plants:plants(1981),si:SI,endPlace:"S9",tieUp:"#305 tied up at {t}, its engine on S9 for sand.",
  coda:"The one task a caption names for the midnight job is the last one: the crew spotted the engine on S9 for sand and went home. In a 1980 photo that engine is #3, just west of the scale, with the track gang loading sand by the bucket (<a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/45830819194\" rel=\"noopener\">p.99</a>).",
  build(H){
    const work=["Pull the night's coke from the battery and weigh it","Coke to F1 for the morning","Line the West Yard over C9 for #105's first drag","Set the engine on S9 for sand"];
    const steps=[
      H.info("the yard office","On duty, midnight",`<p>It is ten below zero. You are the conductor of #305, the midnight job: midnight to 7:00 a.m., east and west. Switcher #3 is idling outside the yard office with its doors iced.</p>`,"Go to work"),
      H.ask({sec:"sig",src:"GC · 5.8.2",title:"Air in the cold",body:"#3 has pumped up the coke string and the brakeman has finished the air test. The engineer is ready to go. Which whistle signal means release brakes, proceed?",
        right:"Two long sounds (— —)",wrong:[["One long sound (—)"],["Three short sounds (o o o)"],["Two short sounds (o o)"]],
        why:"GCOR 5.8.2: (3) — —, release brakes, proceed. (2) — is when stopped, air brakes applied, pressure equalized; (5) o o o is back up; (4) o o an acknowledgment."}),
      H.ask({sec:"sig",src:"GC · 5.8.1",title:"A quick move",body:"You make a string of short stop-and-start moves on the coke plant lead. Must the bell be rung before each one?",
        right:"No: momentary stop-and-start switching is excepted",wrong:[["Yes, before every movement"],["Only between midnight and 6:00"],["Only when the whistle has failed"]],
        why:"GCOR 5.8.1: ring the bell before moving, except momentary stop-and-start switching, as a warning when necessary, approaching men or equipment, and approaching public crossings."}),
      H.mv("coke",14,"Night coke pulled"),
      H.mv("scale",14,"Coke weighed"),H.done(0),
      ask(H,Q.speed,{title:"In the dark",body:"Your headlight lights only a short way into the steam off the quench tower. You take the coke up the furnace lead. What speed?"}),
      H.mv("f1",14,"Coke on F1 for the morning"),H.done(1),
      H.ask({sec:"gcor",src:"GC · 1.47C",title:"Not slowing",body:"Heading for the West Yard, the brakeman has called a switch lined against you ahead. The engineer, tired at 4:00 a.m., is not slowing. You are in the cab. What must you do?",
        right:"Remind him at once and, if he still does not act, stop the movement, with the emergency brake valve if necessary",wrong:[["Nothing: running the engine is the engineer's job"],["Report it to the trainmaster at the end of the shift"],["Wait to see whether he notices in time"]],
        why:"GCOR 1.47C: crew members in the engine compartment communicate restrictions and known conditions in time for the engineer to act, and remind him if proper action is not being taken. When the engineer fails to comply, they must immediately take action to ensure safety, using the emergency brake valve to stop the train if necessary."}),
      H.mv("wyard",18,"At the West Yard"),
      H.ask({sec:"gcor",src:"GC · 6.28",title:"C9 is frozen",body:"C9 will not come over. You and the brakeman both bar on it and the points stop short of the stock rail. May #3 move over it?",
        right:"No: the move must stop short of a switch lined improperly",wrong:[["Yes, slowly, and let the wheels push the points over",{end:true,endText:"#3 went on the ground at the frozen C9 switch."}],["Yes, if the brakeman stands on the lever"],["Yes, at restricted speed"]],
        why:"GCOR 6.28: off main track, move at a speed that allows stopping short of a train, engine, car, men or equipment fouling the track, stop signal, or derail or switch lined improperly."}),
      H.info("West Yard","Ten below","<p>In the early 1980s at −10 °F, Mark Connolly and John Iwanonkiw could not throw the frozen C9 switch. Bill McEwen Sr. told them: “If I could have thrown that switch you two would have both been up on the road.” Mark adds: “In this case we really could not throw the switch over.”</p><p>You report it to the yard office for the track gang and work the other ladder.</p>",
        "Work around it",()=>{H.addTime(20);H.S.parAdd+=20*H.S.pace;H.log("C9 frozen; reported, worked around")}),
      H.done(2),
      H.mv("srun",16),
      ask(H,Q.men,{title:"The track gang at daybreak",body:"Near 6:30 the track gang is out by S1 with buckets for the sand. You come up on them with #3. What does the engineer sound?"}),
      H.mv("s9",14,"#3 on S9 for sand"),
      H.ask({sec:"pov",src:"PV p.99",url:"45830819194",title:"The last move",body:"What is the midnight job's last move of the shift?",
        right:"Spot the engine on S9 for sand and go home",wrong:[["Take one more drag to the dumper"],["Run light to the P&LE shop for fuel"],["Leave the engine at the Y Interchange"]],
        why:"The crew spotted the engine on S9 for sand and went home; the track gang loaded the sand by the bucket."}),
      H.done(3)
    ];
    return {work,steps};
  }},

/* ===================== EXTRA ===================== */
extra:{pace:4,code:"EXTRA",name:"called off the extra board",year:"1988",dateLine:"1988",start:780,end:1260,engine:"#4",units:{"#4":"scale"},
  cement:"Lone Star",plants:plants(1988),si:SI,endPlace:"the yard office",tieUp:"The extra tied up at {t}.",
  coda:"An extra was called when the plant was super busy or the scale was down. Asked in 1988 why railroad employees were not guaranteed 40 hours a week, John Iwanonkiw answered: “Cause we were on the extra board for all those years!” (<a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/809168349703602176\" rel=\"noopener\">p.2</a>, <a href=\"https://www.tumblr.com/pittsburghohiovalleyrailroad/60848620277\" rel=\"noopener\">p.62</a>).",
  build(H){
    const why=H.pick(["busy","scale"]);
    const work=why==="scale"?["Water #4 at the scale house","Hold the cars for weighing on S9 until the scale is back","Extra ore drag to the dumper","Weigh the held cars when the scale returns"]
      :["Water #4 at the scale house","Extra ore drag to the dumper","Extra furnace coke to F1","Empty pig gons out of the East Yard"];
    const steps=[
      H.info("the yard office","The call, 1:00 p.m.",`<p>1988. You have been on the extra board for weeks, third out most of the time. The phone rings: ${why==="scale"?"the scale is down":"the plant is super busy"}, and the trainmaster wants an extra. You report to the yard office for engine #4.</p>`,"Take the call"),
      H.info("the scale house","Water, the hard way","<p>#4 is low on water. In 1988 Scott Morrison, who was usually third out, added water to #4 the hard way at the scale house, by hand. You add water to #4 by hand.</p>","Done",()=>{H.addTime(10);H.S.parAdd+=10*H.S.pace;H.log("Water added to #4 by hand at the scale house")}),
      H.done(0),
      H.ask({sec:"gcor",src:"GC · 1.47B",title:"An engineer off the board",body:"Your engineer has not run #4 in a month. Who is responsible for operating the engine safely and efficiently?",
        right:"The engineer; the crew obey his instructions about operating it",wrong:[["The conductor, who supervises the job"],["The trainmaster, who called the extra"],["Whoever is senior in the cab"]],
        why:"GCOR 1.47B: the engineer is responsible for safely and efficiently operating the engine, and the crew obey the engineer's instructions about operating it."}),
      H.ask({sec:"def",src:"GC · Glossary",title:"New to the east end",body:"Your engineer came over from another road and has never worked the east end. The trainmaster sends a regular man to ride with him and show him the tracks. Under GCOR, what is that man?",
        right:"A pilot",wrong:[["A flagman"],["A student engineer"],["A foreman"]],
        why:"GCOR glossary: a pilot is an employee assigned to a train to assist an engineer or conductor who is unfamiliar with the rules or the portion of railroad the train will operate on."})
    ];
    if(why==="scale")steps.push(
      H.info("the scale house","The scale is down","<p>The scale men are working on the Toledo scale and hold the scale track. Today's order is to hold the cars that need weighing on S9 until it is back.</p>"),
      ask(H,Q.working,{title:"The scale track",body:"The scale men hold working limits on the scale track. You need to cross it to reach S9. How may you move inside their limits?"}),
      H.mv("s9",8,"Cars for weighing held on S9"),H.done(1));
    steps.push(H.mv("srun",14,"Extra drag made up"),
      ask(H,Q.men,{title:"The gandydancers",body:"Shoving the extra drag past the track gang shed by S1, the gang is out on the next track. What does the engineer sound?"}),
      H.mv("dumper",18,"Extra drag at the dumper"),H.done(why==="scale"?2:1));
    if(why==="scale")steps.push(
      H.wait(40,"The scale is back"),
      H.mv("scale",16,"Held cars weighed"),
      H.ask({sec:"pov",src:"PV p.95",url:"45908061832",title:"Catching up",body:"The scale is back and the held cars go across. Who does the weighing?",
        right:"The yard clerk or the trainmaster, at the beam in the yard office",wrong:[["The conductor, from the footboard"],["The PC&Y crew, at the interchange"],["The plant's own weighmaster at the furnace"]],
        why:"Weighing belonged to the yard clerks and the trainmasters, at the Toledo scale in the yard office: Wayne Amber, Bill McEwen and Denny Jarvis."}),
      ask(H,Q.foul,{title:"Back on S9",body:"You shove the weighed cars back onto S9 and the last one stops between the clearance point and the switch points. What is it now?"}),H.done(3));
    else steps.push(
      H.mv("coke",14),H.mv("scale",12,"Extra coke weighed"),
      ask(H,Q.variable,{body:"Going up the furnace lead you trail through a switch with a yellow bowl. Where are its points after the cut has passed?"}),
      H.mv("f1",12,"Extra coke on F1"),H.done(2),
      H.mv("eyard",14,"At the East Yard, near West View Water"),
      ask(H,Q.clear,{title:"Pig gons",body:"You pull the empty pig gons and leave the rest of the East Yard track clear for the next move. Where must the last car you leave stand?"}),
      H.mv("pig",12,"Empty gons to the pig machine"),H.done(3));
    return {work,steps};
  }},

/* ===================== South Yard: the yardmaster ===================== */
ym:{pace:3,code:"YM",name:"yardmaster at South Yard",year:"1990",dateLine:"early December 1990",start:420,end:930,engine:"YM",units:{"YM":"scale","#4":"wyard","#6":"eyard"},
  cement:"Lone Star",plants:plants(1990),foundryClosed:true,si:["You are the yardmaster in the yard office by South Yard. On the P&OV the trainmaster wrote the switching orders and did the weighing; for the game that is your desk.",SI[0],SI[1]],
  endPlace:"the yard office",tieUp:"The day's work at South Yard was done at {t}.",
  coda:"B furnace's last casts came in December 1990, when the <i>Post-Gazette</i> expected it to run dry on the 5th or 6th, and the foundry had closed on 30 November by the same report. After that the east end was a coke plant (<a href=\"../library/pittsburgh-ohio-valley-railway.html\">the P&amp;OV page</a>).",
  build(H){
    const lad=H.R()<.5;
    const work=["Give #4 (#105) and #6 (#110) their orders","Weigh #4's coke and the scrap loads","Spot gons for the scrap at A furnace","Take the PC&Y interchange","Keep the leads clear of fouled cars"];
    const moveU=(u,to,min,note)=>H.mv(to,min,note,u);
    const steps=[
      H.info("the yard office","7:00, the yard office",`<p>Early December 1990. You are the yardmaster at South Yard. The yard office: a Toledo scale, a lantern, the base radio, phones, track cards, a hardhat, and a horseshoe above the door. “Yep, that's a yard office alright.”</p><p>A furnace is being cut up for scrap. B is running its last days. #105 has SW9 #4 in the West Yard; the game gives #110 SW9 #6, in the East Yard.</p>`,"Open the day"),
      H.ask({sec:"gcor",src:"GC · 1.46",title:"Your job",body:"What does a yardmaster answer for?",
        right:"Prompt movement of cars and proper make-up of trains, supervising the yard crews and clerks",wrong:[["Running the engines when the crews are short"],["Inspecting and repairing cars"],["Authorizing trains on the PC&Y"]],
        why:"GCOR 1.46: the yardmaster directly supervises yard crews, clerks and others in the yard, and is responsible for prompt movement of cars and proper make-up of trains."}),
      H.done(0),
      H.ask({sec:"pov",src:"PV p.60",url:"61428754567",title:"Scrap at A furnace",body:"A furnace is coming down. Where do you have #110 spot the gons to load the scrap?",
        right:"On the old pig-iron holding track, beside the East Runner",wrong:[["On F1, where the coke goes"],["On E9, the heat track"],["On the dumper track, E2"]],
        why:"When A was being cut up, the gons sat on the old pig-iron holding track, the East Runner beside them, with B still standing behind."}),
      moveU("#6","pig",20,"#6: scrap gons spotted at A furnace"),H.done(2)
    ];
    if(lad)steps.push(H.ask({sec:"pov",src:"PV p.91",url:"46331368911",title:"B's last casts",body:"B furnace casts this morning, and #110 reports the ladles are in the wrong order again. What do you tell them?",
        right:"Switch them from E6 to E4 into the furnace's order before the cast",wrong:[["Spot them as they are; the furnace can sort them"],["Take them to E9 and leave them"],["Send them to the Y Interchange"]],
        why:"Ladles were switched from E6 to E4 to spot for the furnace cast, because they were rarely in the order the furnace wanted."}),
      moveU("#6","ladle",14,"#6: ladles switched E6 to E4"));
    steps.push(
      H.info("the yard office","No foundry ladle","<p>The Shenango foundry closed on 30 November, by the <i>Post-Gazette</i>'s report. No ladle goes to the other end of the island today.</p>"),
      moveU("#4","coke",22,"#4: coke pulled at the battery"),
      moveU("#4","scale",12,"#4 on the scale"),
      H.ask({sec:"pov",src:"PV p.95",url:"45908061832",title:"At the beam",body:"#4's coke string is on the scale. When can you read the weight?",
        right:"As soon as the crew cuts away and backs the engine off",wrong:[["Only with the engine on the scale too"],["After every car has stood alone for a minute"],["At the furnace, later"]],
        why:"Mark Connolly on the weighers: \"You no sooner cut away and backed off the scale and bam the buzzer was off.\""}),
      H.done(1),
      H.ask({sec:"gcor",src:"GC · 1.47A",title:"A bad hopper",body:"The car knocker restricts one hopper in #4's string: it must not go up the dumper. Who must tell #4's engineer?",
        right:"The conductor: he must advise the engineer of any restriction on equipment being handled",wrong:[["Nobody; the tag on the car is enough"],["The PC&Y, when the car is interchanged"],["The engineer finds out at the dumper"]],
        why:"GCOR 1.47A: the conductor must advise the engineer and train dispatcher of any restriction placed on equipment being handled."}),
      moveU("#4","f1",14,"#4: coke on F1"),
      H.info("the yard office","The PC&Y is coming","<p>The radio: the PC&amp;Y is bringing ore from Scully Yard. For the game, a PC&amp;Y transfer runs the main track from the Y Interchange, inside yard limits.</p>"),
      H.ask({sec:"yl",src:"GC · 6.13",title:"Who gives way?",body:"#6 wants to use the same main track to bring scrap loads west while the PC&Y transfer, a train, approaches. Inside yard limits, who gives way?",
        right:"#6: engines give way to trains as they approach",wrong:[["The PC&Y transfer, since it is a guest on the island"],["Whoever got there first"],["Neither: inside yard limits nobody gives way"]],
        why:"GCOR 6.13: trains and engines may use the main track without protecting against other trains or engines, but engines give way to trains as they approach and must not delay passenger trains."}),
      H.wait(18,"PC&Y transfer in at the Y Interchange"),H.done(3),
      H.ask({sec:"def",src:"GC · Glossary",title:"Engine or train?",body:"The PC&Y transfer displays a marker and is authorized on the main track. #4 with its cut of hoppers displays none. Under GCOR, what is #4 with its cut?",
        right:"An engine with cars, not a train",wrong:[["A train, since it has cars"],["An extra train"],["A work train"]],
        why:"GCOR glossary: a train is one or more engines coupled, with or without cars, displaying a marker, and authorized to operate on a main track. An engine is a unit propelled by any form of energy."}),
      moveU("#6","eyard",18,"#6: scrap loads to the East Yard"),
      ask(H,Q.foul,{title:"The East Yard lead",body:"#6 has left the last scrap load short: its end stands between the clearance point and the switch points. What do you call that, before you tell #6 to shove it in?"}),
      moveU("#6","scale",16,"#6: scrap loads weighed"),H.done(4),
      ask(H,Q.working,{title:"The track gang at C9",body:"The track gang has working limits at C9 for the afternoon. #4 needs to get through to the West Yard. How may it move inside the limits?"}),
      moveU("#4","wyard",16,"#4 tied up in the West Yard")
    );
    return {work,steps};
  }}
};
window.NevilleRuns=NevilleRuns;
})();
