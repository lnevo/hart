/* Extra East: the 1949 run's event pools, drawn on the road and at stations by run.js (drawRoad, drawStation). The
   run itself is in run-tto.js.
   Runs inside its own function. It takes the names it uses from run.js with ExtraEast.take and hands back its own with
   ExtraEast.give (see run.js, GIVES). */
(function(){
"use strict";
const X=window.ExtraEast;
const {semSvg,ask}=X.take("run-1949.js",["semSvg","ask"]);
/* ---------- events on the road and at stations (1949) ---------- */
const ROAD_TTO=[
  ()=>ask({sec:"sig",src:"SC · Rule 14(l)",title:"Crossing at grade",
    body:"A public road crosses the line ahead at grade. Which whistle does the engineman sound?",
    right:"— — o —, prolonged or repeated until the crossing is reached",wrong:[["— o o o"],["o o o"],["— —"]],
    why:"Rule 14(l): — — o — approaching public crossings at grade. — o o o calls the flagman to protect "+
      "the rear; o o o when standing is back; — — is release brakes, proceed."}),
  ()=>ask({sec:"sem",src:"SM",title:"Semaphore ahead",body:"A semaphore block signal ahead shows its blade horizontal.",
    extra:semSvg(0),right:"Stop",
    wrong:[["Approach, prepared to stop at the next signal"],["Clear"],
      ["It depends on whether it is upper or lower quadrant"]],
    why:"A horizontal semaphore blade is always stop, upper or lower quadrant."}),
  ()=>ask({sec:"sem",src:"SM",title:"An old lower-quadrant blade",
    body:"The fireman notes the next signal is a lower-quadrant semaphore. Why is a lower-quadrant blade not fail-safe?",
    right:"If the mechanism fails, gravity drops the blade toward a proceed position",
    wrong:[["Its lamp burns out easily"],["It can show only two positions"],["Snow freezes it at stop"]],
    why:"On a lower-quadrant signal the blade drops to clear (0°, 30°, 60°), so a broken linkage can turn "+
      "stop into approach or clear. Upper-quadrant blades rise (0°, 45°, 90°)."}),
  ()=>ask({sec:"sig",src:"SC · Rule 12(b)",title:"A signal from the ground",
    body:"A section foreman beside the track holds his flag out horizontally at arm's length.",right:"Reduce speed",
    wrong:[["Stop"],["Proceed"],["Back up"]],
    why:"Rule 12: held horizontally at arm's length is reduced speed. Swung at right angle to the track is "+
      "stop, raised and lowered vertically is proceed, swung in a circle is back."}),
  ()=>ask({sec:"def",src:"SC · Definitions",title:"Restricted speed",
    body:"A bulletin says to run at restricted speed over a bridge being repaired. Under the Standard Code that means…",
    right:"Proceed prepared to stop short of train, obstruction or switch not properly lined, and look out "+
      "for broken rail",
    wrong:[["Not over 20 MPH"],["Half the maximum authorized speed"],
      ["Not over 15 MPH, prepared to stop at the next signal"]],
    why:"The Standard Code gives no mph figure. GCOR 6.27 adds half the range of vision and 20 MPH."}),
  ()=>ask({sec:"sig",src:"SG · Signal signage",title:"Automatic block signal",
    body:"In the automatic block between stations, a signal with a number plate shows stop.",
    right:"Stop, then proceed at restricted speed",
    wrong:[["Wait for the dispatcher's permission"],["Pass at reduced speed without stopping"],
      ["Wait 5 minutes, then proceed at track speed"]],
    why:"A number plate marks a permissive signal: after stopping, you may proceed at restricted speed. An "+
      "A plate or no plate is absolute."}),
  ()=>ask({sec:"sup",src:"SC · Rule 99",title:"Slow on the grade",
    body:"Extra 812 East is crawling up the grade below Granite, and a superior train may come up behind you "+
      "while you are still moving. How does the flagman protect the rear?",
    right:"He drops lighted fusees at proper intervals",
    wrong:[["He goes back and places two torpedoes while the train keeps moving"],
      ["None is needed while the train is moving"],["The engineman sounds — o o o every mile"]],
    why:"Rule 99: a moving train that may be overtaken is protected by the flagman dropping lighted fusees "+
      "at proper intervals. Torpedoes are for a stopped train."}),
  ()=>ask({sec:"sig",src:"SG · Signal signage",title:"Stop on the hill",
    body:"Halfway up the grade, an automatic signal with a G plate and a number plate shows stop.",
    right:"Pass it at restricted speed without stopping",
    wrong:[["Stop and wait for permission"],["Stop, then proceed at restricted speed"],["Pass it at track speed"]],
    why:"A G plate marks a grade signal: a train may pass it at restricted speed without stopping."}),
  ()=>ask({sec:"sig",src:"SG · Signal signage",title:"A P plate",
    body:"The signal ahead carries a P plate and shows stop.",
    right:"There is a detector in the block, such as high water or a slide, and the crew must inspect it",
    wrong:[["It is a permissive signal; after stopping, proceed at restricted speed"],["A passenger station is ahead"],
      ["A pilot is required"]],
    why:"A P plate marks a protective signal: a detector in the block that the crew must check."}),
  ()=>ask({sec:"sup",src:"SC · Rule 251",title:"Block signals ahead",
    body:"From Granite east the time-table names the track as governed by block signals for trains in the "+
      "same direction. What decides how you run ahead of No 2 there?",
    right:"The block signal indications, which supersede superiority",
    wrong:[["Superiority by class, as before"],["A train order for each block"],
      ["Whoever reaches the next signal first"]],
    why:"Rule 251: on designated tracks, trains run with reference to other trains in the same direction by "+
      "block signals, whose indications supersede the superiority of trains."}),
  ()=>ask({sec:"def",src:"SC · Definitions",title:"Approach signal",
    body:"A fixed signal a mile out warns you of the home signal at the next interlocking. What is it called?",
    right:"An approach signal",wrong:[["A block signal"],["A train order signal"],["An interlocking signal"]],
    why:"Standard Code: an approach signal is a fixed signal used in connection with one or more signals to "+
      "govern the approach to them."}),
  ()=>ask({sec:"sig",src:"SC · Rule 12a",title:"A lamp across the track",
    body:"Ahead, a man on the ground swings a lamp at right angle to the track.",right:"Stop",
    wrong:[["Proceed"],["Reduce speed"],["Back up"]],why:"Rule 12(a): swung at right angle to the track means stop."}),
  ()=>ask({sec:"sig",src:"SC · Rule 12c",title:"Up and down",
    body:"The head brakeman at the switch raises and lowers his lamp vertically.",right:"Proceed",
    wrong:[["Stop"],["Back up"],["Release brakes"]],why:"Rule 12(c): raised and lowered vertically means proceed."}),
  ()=>ask({sec:"sig",src:"SC · Rule 14(a)",title:"One short",body:"The engineman sounds one short blast: o.",
    right:"Apply brakes, stop",wrong:[["Release brakes, proceed"],["Acknowledge"],["Back up"]],
    why:"Standard Code Rule 14(a): one short is apply brakes, stop. The GCOR uses one long (—) for brakes "+
      "applied when stopped."}),
  ()=>ask({sec:"sig",src:"SC · Rule 14(b)",title:"Two longs",body:"After the stop, the engineman sounds — —.",
    right:"Release brakes, proceed",wrong:[["Flagman protect rear"],["Back up"],["Approaching a crossing"]],
    why:"Rule 14(b): two longs mean release brakes, proceed. The same in the GCOR."}),
  ()=>ask({sec:"sig",src:"SC · Rule 14(h)",title:"Three shorts, standing",
    body:"Standing in the siding, the engineman sounds o o o.",right:"Back",
    wrong:[["Proceed"],["Flagman go out"],["Apply brakes"]],
    why:"Rule 14(h): o o o when standing means back, the answer to hand signal 12(d). When running it "+
      "answers the communicating signal."}),
  ()=>ask({sec:"sig",src:"SC · Rule 14(c)",title:"Long and three shorts",
    body:"The train stops short on the main and the engineman sounds — o o o.",right:"Flagman protect rear of train",
    wrong:[["Back up"],["Approaching a crossing"],["Release brakes, proceed"]],
    why:"Rule 14(c): — o o o calls the flagman to protect the rear of the train."}),
  ()=>ask({sec:"sig",src:"SG · Definitions",title:"Aspect and indication",
    body:"The fireman calls out “yellow.” Is he naming the aspect or the indication?",
    right:"The aspect: what the signal looks like. The indication is what it tells you to do",
    wrong:[["The indication"],["Both; they are the same"],["The name of the signal rule"]],
    why:"Aspect is what you see; indication is what it tells you (stop, approach, clear); the name is the "+
      "railroad's label, usually by rule number."}),
  ()=>ask({sec:"sig",src:"SG · Definitions",title:"Route or speed?",
    body:"The Kestrel Valley's signals tell you which route you are lined for and how clear the blocks are, "+
      "and speeds come from the time-table. What is that system?",right:"Route signaling",
    wrong:[["Speed signaling"],["APB"],["Cab signaling"]],
    why:"Route signaling gives the route and the state of the blocks ahead; diverging speeds come from the "+
      "time-table. Speed signaling tells you how fast to go past the signal."}),
  ()=>ask({sec:"sig",src:"SG · Definitions",title:"Opposing signals",
    body:"On this stretch, once you pass the head block signal at a siding, every opposing signal goes to "+
      "stop through to the next siding. What system is that?",right:"APB, Absolute Permissive Block",
    wrong:[["Plain ABS"],["CTC"],["An interlocking"]],
    why:"APB: when a train passes a head block at a siding, all opposing signals go to stop through to the "+
      "head block at the next siding. ABS has the blocks without that rule."}),
  ()=>ask({sec:"sig",src:"SG · Signal chart",title:"A green signal",
    body:"The next block signal shows a single green.",right:"Clear: next two blocks are unoccupied",
    wrong:[["Approach: next block is unoccupied"],["Proceed on the diverging route"],["Proceed at restricted speed"]],
    why:"Basic Signal Indication Chart: green is Clear, next two blocks are unoccupied. Yellow is Approach, "+
      "next block is unoccupied."}),
  ()=>ask({sec:"sig",src:"SG · Signal chart",title:"A yellow signal",
    body:"The block signal ahead shows a single yellow.",right:"Approach: next block is unoccupied",
    wrong:[["Clear: next two blocks are unoccupied"],["Stop and proceed"],["Diverging route"]],
    why:"Basic Signal Indication Chart: yellow is Approach, next block is unoccupied. Green is Clear, next "+
      "two blocks are unoccupied."}),
  ()=>ask({sec:"sig",src:"SC · Fixed Signals",title:"How signals show",
    body:"Which of these is NOT a way the Standard Code says a fixed signal can show its aspect?",
    right:"By the sound of a bell",
    wrong:[["By the position of semaphore arms"],["By the color of lights"],["By flashing of lights"]],
    why:"Standard Code: fixed signal aspects are shown by position of semaphore arms, color of lights, "+
      "position of lights, flashing of lights, or a combination."}),
  ()=>ask({sec:"sem",src:"SM",title:"Behind the blade",
    body:"The colored glass lenses on a semaphore are the roundels. What holds them?",right:"The spectacle",
    wrong:[["The blade"],["The housing"],["The lamp"]],
    why:"Semaphore parts: blade, roundels (the lenses), spectacle (holds the roundels), lamp, actuating "+
      "mechanism, housing."}),
  ()=>ask({sec:"sem",src:"SM",title:"Upper quadrant",
    body:"The signal ahead is an upper-quadrant semaphore. Through what positions does its blade move?",
    right:"0°, 45° and 90°, rising from horizontal",
    wrong:[["0°, 30° and 60°, dropping"],["0°, 60° and 90°"],["0° and 90° only"]],
    why:"Upper-quadrant blades rise to clear through 0°, 45° and 90°, and came about around 1900. "+
      "Lower-quadrant blades drop through 0°, 30° and 60°."}),
  ()=>ask({sec:"sem",src:"SM",title:"Fixed at 45 degrees",
    body:"Before the river bridge stands a semaphore whose blade never moves from 45°. What is it?",
    right:"A single-position signal: a permanent approach warning of something ahead",
    wrong:[["A broken signal to report"],["A train order board"],["A stop signal"]],
    why:"Single-position semaphores were fixed at 45° as a permanent warning of something ahead such as a "+
      "bridge, commonly for a restricting indication."}),
  ()=>ask({sec:"sem",src:"SM",title:"Old signals",
    body:"The fireman says these semaphores are as old as the railroad. When was the semaphore patented?",
    right:"In the 1840s",wrong:[["Around 1900"],["In the 1870s"],["In the 1930s"]],
    why:"The semaphore was patented in the 1840s and first lit by kerosene, later by electric bulbs. The "+
      "upper quadrant came around 1900."})
];
const STN_TTO=[
  ()=>ask({sec:"sig",src:"SC · Rule 12(d)",title:"Hand signal",
    body:"The head brakeman on the ground swings his lamp vertically in a circle at right angle to the "+
      "track. What does he want?",right:"Back up",wrong:[["Proceed"],["Stop"],["Apply air brakes"]],
    why:"Rule 12(d): swung vertically in a circle at right angle to the track is back. The engineman "+
      "answers with o o o (Rule 14(h))."}),
  ()=>ask({sec:"sup",src:"SC · Rule S-89",title:"Backing into the siding",
    body:"The west switch here is blocked by a car, so you must back into the siding from the east end. What "+
      "does Rule S-89 require?",right:"Protect the train as prescribed by Rule 99",
    wrong:[["Get a train order first"],["Sound — — o — while backing"],
      ["Nothing, if the superior train is not in sight"]],
    why:"Rule S-89: if the inferior train must back in, it is protected as prescribed by Rule 99, unless "+
      "otherwise provided."}),
  ()=>ask({sec:"to",src:"SC · Rule 206",title:"How the operator names you",
    body:"The operator here asks how your train will be named in any order. What is right?",right:"Extra 812 East",
    wrong:[["No 812 East"],["East Extra 812"],["Work Extra 812"]],
    why:"Rule 206: extras are named by engine number and direction. Work extras are “Work Extra” and the "+
      "engine number."}),
  ()=>ask({sec:"sup",src:"SC · Rule 82",title:"A very late train",
    body:"The operator says No 3, a regular train, is more than 12 hours behind its schedule at this "+
      "station. What is its standing now?",right:"It has lost both right and schedule and may move only by train order",
    wrong:[["It became an extra automatically"],["It keeps its schedule but loses right"],
      ["It runs on its schedule at restricted speed"]],
    why:"Rule 82: a regular train more than 12 hours behind its time at any station loses both right and schedule."}),
  ()=>ask({sec:"sup",src:"SC · Rule 94",title:"A disabled train",
    body:"Word comes of an eastbound freight disabled ahead and unable to move. If needed, your train may…",
    right:"Pass it if practicable, and if necessary take its schedule and orders",
    wrong:[["Push it to the next siding"],["Wait until the dispatcher annuls its orders"],["Become a work extra"]],
    why:"Rule 94: pass the disabled train if practicable; if necessary assume its schedule and take its "+
      "train orders, then report from the next point of communication."}),
  ()=>ask({sec:"to",src:"SC · Rule 220",title:"How long an order lasts",
    body:"The fireman asks how long an order you hold stays in force.",
    right:"Until it is fulfilled, superseded or annulled",
    wrong:[["Until midnight"],["Until you reach Ironton"],["12 hours after it was issued"]],
    why:"Rule 220: a train order is in effect until fulfilled, superseded or annulled. Orders are numbered "+
      "each day from midnight (Rule 203), but that does not end them."}),
  ()=>ask({sec:"to",src:"SC · Form S-C",title:"A right-over order",
    body:"The operator reads you another crew's order: “No 21 has right over Extra 640 East Granite to "+
      "Hollis.” If they meet at Granite or Hollis, which train takes the siding?",
    right:"The first-named train, No 21, unless the order says otherwise",
    wrong:[["Extra 640 East, the inferior train"],["Whichever arrives last"],
      ["Neither; they wait for a meet order"]],
    why:"Form S-C: the first-named train holds the right, and at either named point it takes the siding "+
      "unless the order says otherwise."}),
  ()=>ask({sec:"to",src:"SC · Rule 207",title:"On the wire",
    body:"Standing at the office, you hear the dispatcher call: “31, East, copy 3.” What is he doing?",
    right:"Sending a train order with signal 31, direction East, three copies",
    wrong:[["Giving order number 31"],["Calling train No 31 east"],["Asking for three clearances"]],
    why:"Rule 207: the transmitting signal is “31” or “19”, then the direction, then the number of copies, "+
      "given to each office addressed."}),
  ()=>ask({sec:"to",src:"SC · Rule 211",title:"The wire goes down",
    body:"The operator has all your orders complete, but the wire fails before the dispatcher gives the OK "+
      "on the clearance.",right:"He may deliver them with the clearance marked “Wire has failed”",
    wrong:[["You must wait until the wire is restored"],["The orders are void and must be sent again"],
      ["He gives you a verbal OK and you go"]],
    why:"Rule 211: if all orders for the train are complete, the operator may deliver them with Clearance "+
      "Form A marked “Wire has failed”, acted on as though OK had been given."}),
  ()=>ask({sec:"to",src:"SC · Form S-H",title:"A work extra ahead",
    body:"The operator reads you the work train's order: “Eng 292 works extra 7 00 am until 5 00 pm between "+
      "Elk Gap and Fenwick.” Inside those limits, who protects against your extra?",
    right:"The work extra protects itself against extras in both directions",
    wrong:[["You must flag through the limits"],["Nobody; work extras have right over extras"],
      ["The dispatcher, by holding you at Elk Gap"]],
    why:"Form S-H: within the working limits the work extra, standing or moving, protects itself against "+
      "extra trains in both directions, and it must clear the time of regular trains."}),
  ()=>ask({sec:"to",src:"SC · Form L",title:"An annulled order",
    body:"The operator says order 9 was annulled this morning. May the dispatcher issue a new order under "+
      "number 9 later today?",right:"No; an annulled order is never reissued under its number",
    wrong:[["Yes, once the annulment is delivered"],["Yes, if the dispatcher initials it"],["Only for extras"]],
    why:"Form L: an annulled order must not be reissued under its original number. Orders are numbered each "+
      "day from midnight (Rule 203)."}),
  ()=>ask({sec:"to",src:"SC · Form S-P",title:"Instead of",
    body:"An order reads “No 21 meet Extra 640 East at Hollis instead of Granite.” What has happened?",
    right:"An earlier meet at Granite is superseded; the meet is now at Hollis",
    wrong:[["There are now two meets, at Granite and Hollis"],["The Granite order is annulled and no meet remains"],
      ["No 21 waits at Granite, then at Hollis"]],
    why:"Form S-P: the words “instead of” supersede an order or part of one. A superseded order is not "+
      "reissued under its number."}),
  ()=>ask({sec:"to",src:"SC · Form G",title:"And return",
    body:"Another crew's order reads “Eng 640 run extra Ironton to Cobb and return to Hollis.” Where must "+
      "Extra 640 go before turning back?",right:"All the way to Cobb",
    wrong:[["To Hollis, then back"],["Anywhere between Ironton and Cobb"],["Only to the first open office"]],
    why:"Form G: “…and return” means the extra must go all the way out to the far point before returning."}),
  ()=>ask({sec:"to",src:"SC · Rule 222",title:"The operator's report",
    body:"As you leave, the operator picks up the phone to the dispatcher. What must he report about your train?",
    right:"Its time of arrival and departure, and the direction of an extra",
    wrong:[["Only the number of cars"],["Nothing, unless you had orders"],["Its tonnage and crew names"]],
    why:"Rule 222: operators promptly record and report the time of arrival and departure of all trains and "+
      "the direction of extra trains."}),
  ()=>ask({sec:"sup",src:"SC · Rule S-71",title:"What makes a train superior?",
    body:"The operator quizzes you while you wait. On single track, how is one train superior to another?",
    right:"By right, class or direction; right, given by train order, beats class or direction",
    wrong:[["By class only"],["By direction, then class, then right"],["By engine number"]],
    why:"Rule S-71: right is conferred by train order, class and direction by time-table. Right is superior "+
      "to class or direction, and direction counts only between trains of the same class."}),
  ()=>ask({sec:"sup",src:"SC · Rule S-72",ref:"tt",title:"Same class, opposite ways",
    body:"No 1 West and an eastward passenger, both first class, are due to meet. With nothing in the "+
      "orders, which is superior?",
    right:"No 1: the time-table makes westward trains superior between trains of the same class",
    wrong:[["The eastward train, which is running late"],["Whichever left its terminal first"],
      ["Neither; they need a meet order"]],
    why:"Rule S-72: trains in the direction specified by the time-table are superior to trains of the same "+
      "class in the opposite direction. On the Kestrel Valley that is westward."}),
  ()=>ask({sec:"sup",src:"SC · Rule 72",title:"First and second class",
    body:"No 1 is first class and No 21 is second class. Which is superior?",
    right:"No 1: first class is superior to second",
    wrong:[["No 21, being a freight"],["They are equal; direction decides"],["Whichever is closer to its schedule"]],
    why:"Rule 72: trains of the first class are superior to those of the second, second to third, and so on."}),
  ()=>ask({sec:"sup",src:"SC · Rule 85",title:"Sections passing",
    body:"First 2 is delayed here, and Second 2 wants to go around it. What must happen first?",
    right:"The two sections exchange train orders, signals and numbers",
    wrong:[["Second 2 gets a train order from the dispatcher"],["Second 2 waits 10 minutes"],
      ["First 2 takes down its green flags"]],
    why:"Rule 85: a section must not pass another section of the same schedule without first exchanging "+
      "train orders, signals and numbers with it, and the change is reported from the next point of "+
      "communication."}),
  ()=>ask({sec:"sup",src:"SC · Rule 92",title:"Ready early",
    body:"No 2 is ready to leave here four minutes before its schedule time. May it go?",
    right:"No; a train must not leave a station before its schedule leaving time",
    wrong:[["Yes, first-class trains may run early"],["Yes, if the dispatcher says so by phone"],
      ["Yes, if no opposing train is due"]],
    why:"Rule 92: a train must not leave a station in advance of its schedule leaving time."}),
  ()=>ask({sec:"sup",src:"TT · Appendix",title:"Before you leave",
    body:"A TT&TO crew must know four things before departure: its own schedule if regular, the superior "+
      "trains due, whether they have arrived or left, and…",
    right:"Whether it can make the next meeting point before a superior train is due",
    wrong:[["The tonnage of the train behind"],["The name of the next operator"],
      ["Whether the next office is open"]],
    why:"TT&TO primer appendix: your schedule, the superior trains due, whether they have arrived or left, "+
      "and whether you can make the next meeting point before a superior train is due."}),
  ()=>ask({sec:"to",src:"SC · Form S-C (2)",title:"Right over a regular train",
    body:"The operator reads you another crew's order: “Extra 640 East has right over No 1 Cobb to Granite.” "+
      "What must No 1 do?",right:"Not go beyond Granite until Extra 640 East has arrived",
    wrong:[["Wait at Cobb for Extra 640 East"],["Take the siding at Granite on arrival"],
      ["Clear Extra 640 East's time by 5 minutes"]],
    why:"Form S-C (2): the regular train must not go beyond the point last named until the extra has "+
      "arrived, unless authorized by train order."}),
  ()=>ask({sec:"to",src:"SC · Form S-C (3)",title:"Right over, with a wait",
    body:"The operator reads you another crew's order: “Extra 640 East has right over Extra 70 West Ashby to "+
      "Ironton and wait at Elk Gap until 8 10 am.” What does it mean for Extra 640 East?",
    right:"It must not pass Elk Gap before 8:10 unless Extra 70 West has arrived",
    wrong:[["It stops at Elk Gap and waits for Extra 70 West whatever the time"],["It must reach Elk Gap by 8:10"],
      ["Extra 70 West must wait at Elk Gap until 8:10"]],
    why:"Form S-C with wait times: the first-named extra must not pass the waiting points before the times "+
      "given unless the second-named extra has arrived. The second-named extra clears those times by not "+
      "less than five minutes."}),
  ()=>ask({sec:"to",src:"SC · Form D",title:"Right over, same direction",
    body:"The operator reads you another crew's order: “No 2 has right over Extra 640 East Cobb to Granite,” "+
      "with no times. What must Extra 640 East do?",right:"Not leave Cobb ahead of No 2",
    wrong:[["Clear No 2's time by 10 minutes"],["Take the siding at Granite"],["Nothing; No 2 is behind it"]],
    why:"Form D gives right over a train in the same direction. If no time is given, the second-named train "+
      "must not leave the first-named point ahead of the first-named train."}),
  ()=>ask({sec:"to",src:"SC · Form F",title:"Running sections",
    body:"An order reads “Eng 20 display signals and run as First 2 Ashby to Ironton. Eng 25 run as Second 2 "+
      "Ashby to Ironton.” Which engine carries the green flags?",right:"Eng 20, First 2",
    wrong:[["Eng 25, Second 2"],["Both engines"],["Neither; the order replaces the flags"]],
    why:"Form F runs sections. Rule 20: every section except the last displays two green flags, two green "+
      "lights at night, to show another section follows."}),
  ()=>ask({sec:"to",src:"SC · Form D-H",title:"Work extra on double track",
    body:"An order lets Work Extra 292 work on Main 1 between Hollis and Ironton. Against which trains does "+
      "it protect itself?",right:"Extras moving with the current of traffic on Main 1; it still clears regular trains",
    wrong:[["Extras in both directions on both tracks"],["Nobody; it holds the track"],["Regular trains only"]],
    why:"Form D-H: the work extra protects itself within the limits against extras moving with the current "+
      "of traffic on the named track, and the time of regular trains must be cleared."}),
  ()=>ask({sec:"to",src:"SC · Rule 203",title:"Order numbers",
    body:"The operator notes today's orders started again at No 1. When does the numbering restart?",
    right:"Each day at midnight",
    wrong:[["At each shift change"],["At the start of each time-table"],["Never; numbers run through the year"]],
    why:"Rule 203: train orders are numbered consecutively each day, beginning at midnight."}),
  ()=>ask({sec:"def",src:"SC · Rule 5",title:"One time on the schedule",
    body:"The time-table shows only one time for No 1 at Cobb. Unless marked otherwise, that is its…",
    right:"Leaving time",wrong:[["Arriving time"],["Meeting time"],["Time to be in the clear"]],
    why:"Rule 5: not more than two times are given for a train at a station. One time is the leaving time; "+
      "two times are arriving and leaving."}),
  ()=>ask({sec:"def",src:"SC · Definitions",title:"A section",
    body:"The operator says No 2 is running in two sections today. What is a section?",
    right:"One of two or more trains running on the same schedule",
    wrong:[["A length of track between two signals"],["Part of the time-table for one subdivision"],
      ["A train running extra over part of the line"]],
    why:"Standard Code: a section is one of two or more trains running on the same schedule, displaying "+
      "signals or for which signals are displayed."}),
  ()=>ask({sec:"def",src:"SC · Definitions",title:"Main track and siding",
    body:"Your train is on the siding here. How does the Standard Code define a siding?",
    right:"A track auxiliary to the main track for meeting or passing trains",
    wrong:[["Any track off the main"],["A track used only for switching"],["A main track used in one direction"]],
    why:"Standard Code: a siding is a track auxiliary to the main track for meeting or passing trains. The "+
      "main track extends through yards and between stations and is used by time-table, train order or "+
      "block signals."}),
  ()=>ask({sec:"def",src:"SC · Definitions",title:"Single track",
    body:"Ashby to Hollis is single track. What does that mean?",right:"A main track used by trains in both directions",
    wrong:[["A main track with one siding"],["A track used in one direction only"],
      ["Any track outside a block system"]],
    why:"Standard Code: single track is a main track upon which trains are operated in both directions."}),
  ()=>ask({sec:"def",src:"TT · What is TT&TO",title:"After the operators",
    body:"The old Cobb operator says his job is going away. What replaced TT&TO on lines like this?",
    right:"Track warrants and DTC given by radio, and CTC where traffic paid for it",
    wrong:[["Automatic train stop"],["Longer time-tables"],["More train order offices"]],
    why:"TT&TO lasted about 150 years, to nearly the 1980s. Radio-delivered Direct Traffic Control and "+
      "track warrants replaced the agent-operators; CTC and interlockings went in where traffic paid for them."}),
  ()=>ask({sec:"def",src:"SC · Definitions",title:"An interlocking",
    body:"West of Granite the line crosses another railroad under an interlocking. What is an interlocking?",
    right:"Signals and appliances connected so their movements must follow in proper sequence",
    wrong:[["A siding with a switch at each end"],["Any signal with two heads"],["A block with automatic signals"]],
    why:"Standard Code: an interlocking is an arrangement of signals and signal appliances so "+
      "interconnected that their movements must succeed each other in proper sequence. It may be worked by "+
      "hand or automatically."})
];
X.give("run-1949.js",{ROAD_TTO,STN_TTO});
})();
