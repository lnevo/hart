/* The road runs of Extra East: HART Railroad, "Up the Chartiers". The line, its stations, mileposts and junctions come
   from library/chartiers-valley-railroads.html and the sources it lists; the time-table, the other trains, the
   orders and the offices are the game's own. The engine is Extra East's time-table and train-order machinery
   (exam/run.js: makeTT, checkMove, departTTO, orderBoard), rewritten for a line run both ways with single and
   double track. Every question is a rule from the C&E study deck (exam/deck-data.js), in the deck's words.
   Needs exam/signals.js (the speed-signal chart and its drawings) loaded first. */
(function(){
"use strict";
const LIB="../library/chartiers-valley-railroads.html";
const WIKI="https://en.wikipedia.org/wiki/Chartiers_Branch";
const lib=t=>`<a href="${LIB}">${t}</a>`;

/* ---------- the line ---------- */
/* Carnegie (Mansfield) to Washington. mp: milepost from Carnegie. sd: siding. off: train order office. il: interlocking.
   Double track Carnegie to Houston (HOU), single track beyond. The stations and the mileposts of Bridgeville, Hills,
   Houston and Washington are the sources'; the other mileposts are placed between them. */
const ST=[
  {n:"Carnegie",mp:0,sd:1,off:1,yl:1,reg:1},
  {n:"Glenn",mp:0.9,sd:0},
  {n:"Woodville",mp:2.0,sd:0},
  {n:"Bower Hill",mp:2.9,sd:0},
  {n:"Kirwan",mp:3.5,sd:0},
  {n:"Bridgeville",mp:4.0,sd:1,off:1,il:1},
  {n:"Mayview",mp:5.6,sd:0},
  {n:"Boyce",mp:6.9,sd:1},
  {n:"Hills",mp:8.6,sd:1,off:1,il:1},
  {n:"Canonsburg",mp:11.8,sd:1,off:1},
  {n:"Houston",mp:15.3,sd:1,off:1},
  {n:"Arden",mp:20.0,sd:1},
  {n:"Washington",mp:23.6,sd:1,off:1,yl:1,il:1}];
const LAST=ST.length-1,HOU=10,ARD=11,BV=5,HIL=8;
const MAXMARKS=5;

/* ---------- questions, in the deck's words ---------- */
/* Asked in the same place on every run. */
const Qs={
  s83:{sec:"sup",src:"SC · Rule S-83",title:"Before leaving Carnegie",body:"Carnegie is your initial station and a register station. What must you find out before Extra 4619 South leaves?",right:"Whether all superior trains that are due have arrived or left",wrong:[["That the block ahead shows clear"],["Whether all extras on the division have reported clear"],["The dispatcher's OK on a track warrant"]],why:"Rule S-83: a train must not leave its initial station on any division or subdivision, or a junction, or pass from two or more tracks to single track, until it has been ascertained whether all superior trains due have arrived or left. Register stations are designated by time-table, and the train register there records the arrival and departure of trains."},
  r73:{sec:"sup",src:"SC · Rule 73",title:"Reading the time-table",body:"No 92 is a second-class freight. Your train is an extra. Which is superior?",right:"No 92: extra trains are inferior to regular trains",wrong:[["Your extra, since it has no schedule to keep"],["Neither; the first to reach a siding decides"],["Your extra, being southward"]],why:"Rule 73: extra trains are inferior to regular trains. Rule 72: first class is superior to second, second to third."},
  r84:{sec:"sup",src:"SC · Rule 84",title:"Ready to go",body:"The register shows no superior train due. The engineer has steam up. When may he start the train?",right:"When a proper signal is given",wrong:[["As soon as the brake test is done"],["At once, since extras have no schedule"],["After whistling — — o —"]],why:"Rule 84: a train must not start until a proper signal is given."},
  ylWho:{sec:"yl",src:"YL",title:"Who is in charge here?",body:"Your train stands on the main track inside the Carnegie yard limits, and a yardmaster is on duty. Who is in charge of the moves?",right:"The yardmaster",wrong:[["The dispatcher"],["The conductor of the first train there"],["The engineer of the longest train"]],why:"Yard Limits guide: the yardmaster or agent if one is on duty; otherwise generally the conductor or switch crew foreman of the first train there."},
  bvSem:{sec:"sem",src:"SM",title:"The home signal at Bridgeville",body:"At Bridgeville, where the Bridgeville &amp; McDonald branch leaves and the P&amp;WV is close by, the home signal of the interlocking shows its blade horizontal.",extra:semSvg(0),right:"Stop",wrong:[["Approach, prepared to stop at the next signal"],["Clear"],["It depends on whether it is upper or lower quadrant"]],why:"A horizontal semaphore blade is always stop, upper or lower quadrant."},
  ilDef:{sec:"def",src:"SC · Definitions",title:"An interlocking",body:"The Montour Railroad joins the line at Hills under an interlocking. What is an interlocking?",right:"Signals and appliances connected so their movements must follow in proper sequence",wrong:[["A siding with a switch at each end"],["Any signal with two heads"],["A block with automatic signals"]],why:"Standard Code: an interlocking is an arrangement of signals and signal appliances so interconnected that their movements must succeed each other in proper sequence. It may be worked by hand or automatically."},
  s71:{sec:"sup",src:"SC · Rule S-71",title:"Onto single track",body:"At Houston the line goes from two tracks to one. On single track, how is one train superior to another?",right:"By right, class or direction; right, given by train order, beats class or direction",wrong:[["By class only"],["By direction, then class, then right"],["By engine number"]],why:"Rule S-71: right is conferred by train order, class and direction by time-table. Right is superior to class or direction, and direction counts only between trains of the same class."},
  sh:{sec:"to",src:"SC · Form S-H",title:"A work extra on the single track",body:"The operator at Houston reads you an order held for another crew: “Eng 292 works extra 7 00 am until 5 00 pm between Houston and Arden.” Inside those limits, who protects against your extra?",right:"The work extra protects itself against extras in both directions",wrong:[["You must flag through the limits"],["Nobody; work extras have right over extras"],["The dispatcher, by holding you at Houston"]],why:"Form S-H: within the working limits the work extra, standing or moving, protects itself against extra trains in both directions, and it must clear the time of regular trains."},
  sa:{sec:"to",src:"SC · Form S-A",title:"The meet order",body:"Your order reads “Extra 4619 South meet Extra 2231 North at Arden.” What does it require?",right:"Neither train may proceed past Arden until both have arrived",wrong:[["Extra 2231 North waits at Houston for you"],["The train that arrives first goes on at once"],["Both trains clear each other's time by 5 minutes at Arden"]],why:"Form S-A fixes a meeting point for opposing trains. Neither train may proceed past it until both have arrived. Normally the superior train holds the main and the inferior takes the siding."},
  siding:{sec:"def",src:"SC · Definitions",title:"Main track and siding",body:"Your train stands in the siding at Houston. How does the Standard Code define a siding?",right:"A track auxiliary to the main track for meeting or passing trains",wrong:[["Any track off the main"],["A track used only for switching"],["A main track used in one direction"]],why:"Standard Code: a siding is a track auxiliary to the main track for meeting or passing trains. The main track extends through yards and between stations and is used by time-table, train order or block signals."},
  r104:{sec:"sup",src:"SC · Rule 104",title:"The Westland switch",body:"Your head brakeman lined the switch for the Westland branch and the engine took the empties in. Who is responsible for that switch now?",right:"You, the conductor: it must be lined back for the main track",wrong:[["The section foreman"],["The engineman"],["Nobody; leave it open for the next train"]],why:"Rule 104: conductors are responsible for the position of switches used by them and their crews, except where switch tenders are stationed. A switch must not be left open for another train unless a member of that train's crew is in charge of it."},
  s88:{sec:"sup",src:"SC · Rule S-88",title:"Meeting Extra 2231 North",body:"Extra 2231 North is at Arden, and your order says the two extras meet there. Northward trains are superior by direction. Which extra takes the siding?",right:"Extra 4619 South, the train in the inferior time-table direction",wrong:[["Extra 2231 North, because it is the opposing train"],["Whichever arrives first"],["The one with the higher engine number"]],why:"Rule S-88: when two extras meet, the train in the inferior time-table direction takes the siding, unless otherwise provided. On Form S-A, neither train goes past Arden until both have arrived."},
  back:{sec:"sig",src:"SC · Rule 12(d)",title:"At the Manifold switch",body:"At the Manifold switch the head brakeman swings his lamp vertically in a circle at right angle to the track. What does he want?",right:"Back up",wrong:[["Proceed"],["Stop"],["Apply air brakes"]],why:"Rule 12(d): swung vertically in a circle at right angle to the track is back. The engineman answers with o o o (Rule 14(h))."},
  back2:{sec:"sig",src:"SC · Rule 14(h)",title:"Answering the brakeman",body:"The engine is standing and the brakeman's signal is back. Which whistle signal answers it?",right:"o o o",wrong:[["— —"],["o"],["— o o o"]],why:"Rule 14(h): o o o when standing means back, the answer to hand signal 12(d). When running it answers the communicating signal."},
  d71:{sec:"sup",src:"SC · Rule D-71",title:"Onto double track",body:"North of Houston the line is double track. On two or more tracks, how is a train superior?",right:"By right or class only; direction no longer counts",wrong:[["By right, class or direction, as on single track"],["By direction only"],["By class or direction"]],why:"Rule D-71: on two or more tracks a train is superior by right or class only. Right is conferred by train order, class by time-table, and right is superior to class. The S- rules are the single-track versions."},
  board2:{sec:"to",src:"SC · Rule 221",title:"The board at Houston",body:"Going north through Houston, the train order signal at the office shows proceed. What does that tell you?",right:"The operator has no orders for any train in your direction",wrong:[["The operator wants you to stop and sign the register"],["Orders are waiting, and you may take them on the fly"],["The block ahead is clear as far as Hills"]],why:"Rule 221: the train order signal shows stop while an operator is on duty, and is changed to proceed only to let a train pass when there are no orders for any train in that direction."},
  r93:{sec:"yl",src:"SC · Rule 93",title:"Into yard limits",body:"You pass the yard limit sign at Carnegie. A switch engine may be working on the main. At what speed do you run?",right:"Yard speed, unless the main track is known to be clear",wrong:[["Maximum authorized speed; you have no more trains to clear"],["Restricted speed, not over 20 MPH"],["Any speed, with the bell ringing"]],why:"Standard Code Rule 93: within yard limits, protection against ____ class (left blank in the Code; the TT&TO primer fills in second class), extra trains and engines is not required; they move at yard speed unless the main track is known to be clear. The 20 MPH figure is GCOR 6.27, not the Standard Code."},
  ylWhat:{sec:"yl",src:"YL",title:"What are yard limits?",body:"The Carnegie yard limits end at a sign. What are yard limits?",right:"A section of main track, defined in the time-table and marked by signs, within which movements follow the yard limit rule",wrong:[["Any track in the yard, including the yard tracks"],["The tracks between the outer signals of an interlocking"],["A siding where trains meet or pass"]],why:"Yard Limits guide: yard limits are a section of main track, usually defined by mileposts in the timetable and marked by signs (such as a forked stick), within which movements follow the yard limit rule (Standard Code Rule 93)."}
};
/* The speed signals at the interlockings: rule, where, title. */
const ASP={bvS:["285","Bridgeville","The signal at Bridgeville"],hilS:["281","Hills","The signal at Hills"],hilN:["283","Hills","Hills, northbound"],bvN:["292","Bridgeville","Bridgeville, northbound"]};
function aspectQ(key){
  const [r,where,title]=ASP[key],a=ASPECTS.find(x=>x.r===r),by=Object.fromEntries(ASPECTS.map(x=>[x.r,x]));
  return {sec:"sig",src:"SC · Rule "+r,title,body:`The signal ahead at ${where} shows, arms top to bottom: ${armWords(a.arms)}. What does it indicate?`,extra:`<div class="xw-fig">${sigFig(a.arms)}</div>`,
    right:a.ind,wrong:a.w.map(x=>[by[x].ind]),why:`Rule ${a.r}, ${a.name}.`};
}

/* Drawn on the road (between stations) and at a station, from a shuffled bag so a question does not come twice. */
const ROAD=[
  {sec:"sig",src:"SC · Rule 14(l)",title:"Crossing at grade",body:"A public road crosses the line ahead at grade. Which whistle does the engineman sound?",right:"— — o —, prolonged or repeated until the crossing is reached",wrong:[["— o o o"],["o o o"],["— —"]],why:"Rule 14(l): — — o — approaching public crossings at grade. — o o o calls the flagman to protect the rear; o o o when standing is back; — — is release brakes, proceed."},
  {sec:"sem",src:"SM",title:"Semaphore ahead",body:"A semaphore block signal ahead shows its blade horizontal.",extra:semSvg(0),right:"Stop",wrong:[["Approach, prepared to stop at the next signal"],["Clear"],["It depends on whether it is upper or lower quadrant"]],why:"A horizontal semaphore blade is always stop, upper or lower quadrant."},
  {sec:"sem",src:"SM",title:"An old lower-quadrant blade",body:"The fireman notes the next signal is a lower-quadrant semaphore. Why is a lower-quadrant blade not fail-safe?",right:"If the mechanism fails, gravity drops the blade toward a proceed position",wrong:[["Its lamp burns out easily"],["It can show only two positions"],["Snow freezes it at stop"]],why:"On a lower-quadrant signal the blade drops to clear (0°, 30°, 60°), so a broken linkage can turn stop into approach or clear. Upper-quadrant blades rise (0°, 45°, 90°)."},
  {sec:"sig",src:"SC · Rule 12(b)",title:"A signal from the ground",body:"A section foreman beside the track holds his flag out horizontally at arm's length.",right:"Reduce speed",wrong:[["Stop"],["Proceed"],["Back up"]],why:"Rule 12: held horizontally at arm's length is reduced speed. Swung at right angle to the track is stop, raised and lowered vertically is proceed, swung in a circle is back."},
  {sec:"def",src:"SC · Definitions",title:"Restricted speed",body:"A bulletin says to run at restricted speed over a bridge being repaired. Under the Standard Code that means…",right:"Proceed prepared to stop short of train, obstruction or switch not properly lined, and look out for broken rail",wrong:[["Not over 20 MPH"],["Half the maximum authorized speed"],["Not over 15 MPH, prepared to stop at the next signal"]],why:"The Standard Code gives no mph figure. GCOR 6.27 adds half the range of vision and 20 MPH."},
  {sec:"sup",src:"SC · Rule 99",title:"Slow on the grade",body:"Extra 4619 is crawling up a grade, and a superior train may come up behind you while you are still moving. How does the flagman protect the rear?",right:"He drops lighted fusees at proper intervals",wrong:[["He goes back and places two torpedoes while the train keeps moving"],["None is needed while the train is moving"],["The engineman sounds — o o o every mile"]],why:"Rule 99: a moving train that may be overtaken is protected by the flagman dropping lighted fusees at proper intervals. Torpedoes are for a stopped train."},
  {sec:"def",src:"SC · Definitions",title:"Approach signal",body:"A fixed signal a mile out warns you of the home signal at the next interlocking. What is it called?",right:"An approach signal",wrong:[["A block signal"],["A train order signal"],["An interlocking signal"]],why:"Standard Code: an approach signal is a fixed signal used in connection with one or more signals to govern the approach to them."},
  {sec:"sig",src:"SC · Rule 12(a)",title:"A lamp across the track",body:"Ahead, a man on the ground swings a lamp at right angle to the track.",right:"Stop",wrong:[["Proceed"],["Reduce speed"],["Back up"]],why:"Rule 12(a): swung at right angle to the track means stop."},
  {sec:"sig",src:"SC · Rule 12(c)",title:"Up and down",body:"The head brakeman at the switch raises and lowers his lamp vertically.",right:"Proceed",wrong:[["Stop"],["Back up"],["Release brakes"]],why:"Rule 12(c): raised and lowered vertically means proceed."},
  {sec:"sig",src:"SC · Rule 14(a)",title:"One short",body:"The engineman sounds one short blast: o.",right:"Apply brakes, stop",wrong:[["Release brakes, proceed"],["Acknowledge"],["Back up"]],why:"Standard Code Rule 14(a): one short is apply brakes, stop. The GCOR uses one long (—) for brakes applied when stopped."},
  {sec:"sig",src:"SC · Rule 14(b)",title:"Two longs",body:"After the stop, the engineman sounds — —.",right:"Release brakes, proceed",wrong:[["Flagman protect rear"],["Back up"],["Approaching a crossing"]],why:"Rule 14(b): two longs mean release brakes, proceed. The same in the GCOR."},
  {sec:"sig",src:"SC · Rule 14(c)",title:"Long and three shorts",body:"The train stops short on the main and the engineman sounds — o o o.",right:"Flagman protect rear of train",wrong:[["Back up"],["Approaching a crossing"],["Release brakes, proceed"]],why:"Rule 14(c): — o o o calls the flagman to protect the rear of the train."},
  {sec:"sig",src:"SC · Fixed Signals",title:"How signals show",body:"Which of these is NOT a way the Standard Code says a fixed signal can show its aspect?",right:"By the sound of a bell",wrong:[["By the position of semaphore arms"],["By the color of lights"],["By flashing of lights"]],why:"Standard Code: fixed signal aspects are shown by position of semaphore arms, color of lights, position of lights, flashing of lights, or a combination."},
  {sec:"sem",src:"SM",title:"Behind the blade",body:"The colored glass lenses on a semaphore are the roundels. What holds them?",right:"The spectacle",wrong:[["The blade"],["The housing"],["The lamp"]],why:"Semaphore parts: blade, roundels (the lenses), spectacle (holds the roundels), lamp, actuating mechanism, housing."},
  {sec:"sem",src:"SM",title:"Upper quadrant",body:"The signal ahead is an upper-quadrant semaphore. Through what positions does its blade move?",right:"0°, 45° and 90°, rising from horizontal",wrong:[["0°, 30° and 60°, dropping"],["0°, 60° and 90°"],["0° and 90° only"]],why:"Upper-quadrant blades rise to clear through 0°, 45° and 90°, and came about around 1900. Lower-quadrant blades drop through 0°, 30° and 60°."},
  {sec:"sem",src:"SM",title:"Fixed at 45 degrees",body:"Before a river bridge stands a semaphore whose blade never moves from 45°. What is it?",right:"A single-position signal: a permanent approach warning of something ahead",wrong:[["A broken signal to report"],["A train order board"],["A stop signal"]],why:"Single-position semaphores were fixed at 45° as a permanent warning of something ahead such as a bridge, commonly for a restricting indication."},
  {sec:"sem",src:"SM",title:"Old signals",body:"The fireman says these semaphores are as old as the railroad. When was the semaphore patented?",right:"In the 1840s",wrong:[["Around 1900"],["In the 1870s"],["In the 1930s"]],why:"The semaphore was patented in the 1840s and first lit by kerosene, later by electric bulbs. The upper quadrant came around 1900."}
];
const STN=[
  {sec:"sig",src:"SC · Rule 12(d)",title:"Hand signal",body:"The head brakeman on the ground swings his lamp vertically in a circle at right angle to the track. What does he want?",right:"Back up",wrong:[["Proceed"],["Stop"],["Apply air brakes"]],why:"Rule 12(d): swung vertically in a circle at right angle to the track is back. The engineman answers with o o o (Rule 14(h))."},
  {sec:"sup",src:"SC · Rule S-89",title:"Backing into the siding",body:"The switch at the north end of this siding is blocked by a car, so you must back into the siding from the south end. What does Rule S-89 require?",right:"Protect the train as prescribed by Rule 99",wrong:[["Get a train order first"],["Sound — — o — while backing"],["Nothing, if the superior train is not in sight"]],why:"Rule S-89: if the inferior train must back in, it is protected as prescribed by Rule 99, unless otherwise provided."},
  {sec:"to",src:"SC · Rule 206",title:"How the operator names you",body:"The operator here asks how your train will be named in any order. What is right?",right:"Extra 4619 South",wrong:[["No 4619 South"],["South Extra 4619"],["Work Extra 4619"]],why:"Rule 206: extras are named by engine number and direction. Work extras are “Work Extra” and the engine number."},
  {sec:"sup",src:"SC · Rule 82",title:"A very late train",body:"The operator says No 93, a regular train, is more than 12 hours behind its schedule at this station. What is its standing now?",right:"It has lost both right and schedule and may move only by train order",wrong:[["It became an extra automatically"],["It keeps its schedule but loses right"],["It runs on its schedule at restricted speed"]],why:"Rule 82: a regular train more than 12 hours behind its arriving or leaving time at any station loses both right and schedule."},
  {sec:"sup",src:"SC · Rule 94",title:"A disabled train",body:"Word comes of a southward freight disabled ahead and unable to move. If needed, your train may…",right:"Pass it if practicable, and if necessary take its schedule and orders",wrong:[["Push it to the next siding"],["Wait until the dispatcher annuls its orders"],["Become a work extra"]],why:"Rule 94: pass the disabled train if practicable; if necessary assume its schedule and take its train orders, then report from the next point of communication."},
  {sec:"to",src:"SC · Rule 220",title:"How long an order lasts",body:"The fireman asks how long an order you hold stays in force.",right:"Until it is fulfilled, superseded or annulled",wrong:[["Until midnight"],["Until you reach Carnegie"],["12 hours after it was issued"]],why:"Rule 220: a train order is in effect until fulfilled, superseded or annulled. Orders are numbered each day from midnight (Rule 203), but that does not end them."},
  {sec:"to",src:"SC · Form S-C",title:"A right-over order",body:"The operator reads you another crew's order: “No 92 has right over Extra 640 South Canonsburg to Houston.” If they meet at Canonsburg or Houston, which train takes the siding?",right:"The first-named train, No 92, unless the order says otherwise",wrong:[["Extra 640 South, the inferior train"],["Whichever arrives last"],["Neither; they wait for a meet order"]],why:"Form S-C: the first-named train holds the right, and at either named point it takes the siding unless the order says otherwise."},
  {sec:"to",src:"SC · Rule 207",title:"On the wire",body:"Standing at the office, you hear the dispatcher call: “31, South, copy 3.” What is he doing?",right:"Sending a train order with signal 31, direction South, three copies",wrong:[["Giving order number 31"],["Calling train No 31 south"],["Asking for three clearances"]],why:"Rule 207: the transmitting signal is “31” or “19”, then the direction, then the number of copies, given to each office addressed."},
  {sec:"to",src:"SC · Rule 211",title:"The wire goes down",body:"The operator has all your orders complete, but the wire fails before the dispatcher gives the OK on the clearance.",right:"He may deliver them with the clearance marked “Wire has failed”",wrong:[["You must wait until the wire is restored"],["The orders are void and must be sent again"],["He gives you a verbal OK and you go"]],why:"Rule 211: if all orders for the train are complete, the operator may deliver them with Clearance Form A marked “Wire has failed”, acted on as though OK had been given."},
  {sec:"to",src:"SC · Form L",title:"An annulled order",body:"The operator says order 9 was annulled this morning. May the dispatcher issue a new order under number 9 later today?",right:"No; an annulled order is never reissued under its number",wrong:[["Yes, once the annulment is delivered"],["Yes, if the dispatcher initials it"],["Only for extras"]],why:"Form L: an annulled order must not be reissued under its original number. Orders are numbered each day from midnight (Rule 203)."},
  {sec:"to",src:"SC · Form S-P",title:"Instead of",body:"An order reads “No 92 meet Extra 640 South at Houston instead of Canonsburg.” What has happened?",right:"An earlier meet at Canonsburg is superseded; the meet is now at Houston",wrong:[["There are now two meets, at Canonsburg and Houston"],["The Canonsburg order is annulled and no meet remains"],["No 92 waits at Canonsburg, then at Houston"]],why:"Form S-P: the words “instead of” supersede an order or part of one. A superseded order is not reissued under its number."},
  {sec:"to",src:"SC · Form G",title:"And return",body:"Another crew's order reads “Eng 640 run extra Carnegie to Hills and return to Bridgeville.” Where must Extra 640 go before turning back?",right:"All the way to Hills",wrong:[["To Bridgeville, then back"],["Anywhere between Carnegie and Hills"],["Only to the first open office"]],why:"Form G: “…and return” means the extra must go all the way out to the far point before returning."},
  {sec:"to",src:"SC · Rule 222",title:"The operator's report",body:"As you leave, the operator picks up the phone to the dispatcher. What must he report about your train?",right:"Its time of arrival and departure, and the direction of an extra",wrong:[["Only the number of cars"],["Nothing, unless you had orders"],["Its tonnage and crew names"]],why:"Rule 222: operators promptly record and report the time of arrival and departure of all trains and the direction of extra trains."},
  {sec:"sup",src:"SC · Rule S-72",title:"Same class, opposite ways",body:"No 305 South and No 302 North, both first class, are due to meet. With nothing in the orders, which is superior?",right:"No 302: the time-table makes northward trains superior between trains of the same class",wrong:[["The southward train, which is running late"],["Whichever left its terminal first"],["Neither; they need a meet order"]],why:"Rule S-72: trains in the direction specified by the time-table are superior to trains of the same class in the opposite direction. On the Chartiers Branch time-table that is northward."},
  {sec:"sup",src:"SC · Rule 72",title:"First and second class",body:"No 305 is first class and No 92 is second class. Which is superior?",right:"No 305: first class is superior to second",wrong:[["No 92, being a freight"],["They are equal; direction decides"],["Whichever is closer to its schedule"]],why:"Rule 72: trains of the first class are superior to those of the second, second to third, and so on."},
  {sec:"sup",src:"SC · Rule 85",title:"Sections passing",body:"First 305 is delayed here, and Second 305 wants to go around it. What must happen first?",right:"The two sections exchange train orders, signals and numbers",wrong:[["Second 305 gets a train order from the dispatcher"],["Second 305 waits 10 minutes"],["First 305 takes down its green flags"]],why:"Rule 85: a section must not pass another section of the same schedule without first exchanging train orders, signals and numbers with it, and the change is reported from the next point of communication."},
  {sec:"sup",src:"SC · Rule 92",title:"Ready early",body:"No 302 is ready to leave here four minutes before its schedule time. May it go?",right:"No; a train must not leave a station before its schedule leaving time",wrong:[["Yes, first-class trains may run early"],["Yes, if the dispatcher says so by phone"],["Yes, if no opposing train is due"]],why:"Rule 92: a train must not leave a station in advance of its schedule leaving time."},
  {sec:"sup",src:"SC · Rule 20",title:"Two green flags",body:"A southward passenger train goes by with two green flags on the front of the engine. What do they tell you?",right:"Another section of that train follows on the same schedule",wrong:[["It is running late"],["It has right over all trains"],["The track ahead is clear for two blocks"]],why:"Rule 20: all sections except the last display two green flags, and two green lights at night. A section is one of two or more trains running on the same schedule."},
  {sec:"def",src:"SC · Rule 5",title:"One time on the schedule",body:"The time-table shows only one time for No 305 at Hills. Unless marked otherwise, that is its…",right:"Leaving time",wrong:[["Arriving time"],["Meeting time"],["Time to be in the clear"]],why:"Rule 5: not more than two times are given for a train at a station. One time is the leaving time; two times are arriving and leaving times."},
  {sec:"def",src:"SC · Definitions",title:"A section",body:"The operator says No 305 is running in two sections today. What is a section?",right:"One of two or more trains running on the same schedule",wrong:[["A length of track between two signals"],["Part of the time-table for one subdivision"],["A train running extra over part of the line"]],why:"Standard Code: a section is one of two or more trains running on the same schedule, displaying signals or for which signals are displayed."},
  {sec:"def",src:"SC · Definitions",title:"Single track",body:"Houston to Washington is single track. What does that mean?",right:"A main track used by trains in both directions",wrong:[["A main track with one siding"],["A track used in one direction only"],["Any track outside a block system"]],why:"Standard Code: single track is a main track upon which trains are operated in both directions."},
  {sec:"def",src:"SC · Definitions",title:"A schedule",body:"The conductor of No 92 says the time-table is his authority. What does the schedule part of a time-table give a regular train?",right:"Its class, direction, number and movement",wrong:[["Only its running times"],["Its right over extras on train order"],["Its crew and engine"]],why:"Standard Code: a schedule is that part of a time-table which prescribes class, direction, number and movement for a regular train."}
];

/* ---------- drawings ---------- */
/* Semaphore, blade at a degrees (0 is horizontal, upper quadrant). */
function semSvg(a){
  return `<svg viewBox="0 0 120 120" width="110" height="110" aria-label="Semaphore, blade at ${a} degrees" role="img" style="align-self:flex-start"><rect x="57" y="20" width="6" height="96" fill="#1d2733"/><circle cx="60" cy="16" r="5" fill="#1d2733"/><g transform="rotate(${-a} 60 40)"><rect x="60" y="34" width="52" height="11" fill="#a3302b" stroke="#1d2733" stroke-width="1.5"/><rect x="100" y="34" width="4" height="11" fill="#fff"/></g><circle cx="52" cy="40" r="6" fill="#f3ecbf" stroke="#1d2733" stroke-width="1.5"/></svg>`;
}

const fmt=m=>{m=Math.round(m);m=((m%1440)+1440)%1440;return Math.floor(m/60)+":"+String(m%60).padStart(2,"0")};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* ---------- the coal extra ---------- */
const coal={group:"chartiers",covers:["def","sup","to","sig","sem","yl"],code:"Extra 4619 South",name:"the coal extra",year:"1949",
  dateLine:"a weekday in 1949",start:420,end:900,endPlace:"Carnegie",tieUp:"{t}",
  coda:`The Chartiers Branch ran from Carnegie (Mansfield) to Washington, double track to Houston by 1904. Coal branches left it at Bridgeville, Houston, and later at Palanka and Manifold (${lib("Railroads of the Chartiers Valley")}, <a href="${WIKI}" rel="noopener">Wikipedia: Chartiers Branch</a>).`,
  where(S){const G=S.road;if(!G)return "Carnegie";return G.moving?"between "+G.moving:ST[G.pos].n+(G.inSiding&&G.pos>0&&G.pos<LAST?" (siding)":"")},

  map(S){
    const G=S.road,W=600,xs=ST.map((s,i)=>26+i*44),y=72,y2=79;
    const at=G.pos,me=xs[at];
    let s=`<svg viewBox="0 0 ${W} 122" role="img" aria-label="Line sketch of the Chartiers Branch from Carnegie to Washington, ${esc(S.def.code)} at ${esc(S.def.where(S))}">`;
    s+=`<rect x="0" y="0" width="${W}" height="122" fill="var(--land)"/>`;
    s+=`<path d="M0 36 Q110 24 230 34 T420 30 T600 34" fill="none" stroke="var(--river)" stroke-width="3" opacity=".55"/><text x="8" y="12" font-size="6.5" class="water" style="fill:var(--muted)">CHARTIERS CREEK</text><text x="${W-8}" y="12" font-size="6.5" text-anchor="end" class="water" style="fill:var(--muted)">${esc(S.def.year)}</text>`;
    // yard limits at the two ends
    s+=`<rect x="${xs[0]-14}" y="${y-12}" width="34" height="30" fill="var(--sheet-2)"/><rect x="${xs[LAST]-20}" y="${y-12}" width="34" height="30" fill="var(--sheet-2)"/>`;
    s+=`<g fill="none" stroke="var(--ink)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M${xs[0]-14} ${y} H${xs[LAST]+14}"/><path d="M${xs[0]-14} ${y2} H${xs[HOU]+6}"/></g>`;
    // sidings, and the branches and connections at 45 degrees
    s+=`<g fill="none" stroke="var(--ink)" stroke-width="1.4" stroke-linecap="round">`;
    ST.forEach((st,i)=>{if(st.sd&&i>0&&i<LAST){const x=xs[i];s+=i<=HOU?`<path d="M${x-12} ${y} L${x-6} ${y-6} H${x+6} L${x+12} ${y}"/>`:`<path d="M${x-12} ${y} L${x-6} ${y+6} H${x+6} L${x+12} ${y}"/>`}});
    const lab=[];
    const up=(x,l)=>{s+=`<path d="M${x+14} ${y} L${x+26} ${y-12} H${x+40}"/>`;lab.push([x+28,y-16,l])};
    up(xs[1],"PC&amp;Y");up(xs[2],"PC&amp;Y");up(xs[BV],"B&amp;McD");up(xs[7],"PALANKA");up(xs[HIL],"MONTOUR");
    s+=`<path d="M${xs[BV]-14} ${y} L${xs[BV]-26} ${y-12} H${xs[BV]-38}"/>`; // P&WV, close by Bridgeville
    s+=`<path d="M${xs[ARD]} ${y} L${xs[ARD]+12} ${y-12} H${xs[ARD]+24}"/>`; // Manifold, leaving at Arden
    s+=`<path d="M${xs[HOU]+8} ${y} L${xs[HOU]+20} ${y+12} H${xs[HOU]+34}"/>`; // Westland
    s+=`<path d="M${xs[LAST]+4} ${y} L${xs[LAST]+14} ${y+10} H${xs[LAST]+24}"/>`; // Tylerdale Connecting to the B&O
    s+=`</g>`;
    // stations
    ST.forEach((st,i)=>{const x=xs[i];s+=`<line x1="${x}" y1="${y+9}" x2="${x}" y2="${y+13}" stroke="var(--ink)" stroke-width="1.2"/>`;
      s+=`<text x="${x}" y="${i%2?112:101}" font-size="6.3" text-anchor="middle" class="lbl" font-weight="${i===at&&!G.moving?700:400}">${esc(st.n.toUpperCase())}</text>`;
      if(st.il)s+=`<rect x="${x-3}" y="${y-5}" width="6" height="6" fill="var(--rust)" opacity=".85"/>`});
    lab.forEach(([x,yy,t])=>{s+=`<text x="${x}" y="${yy}" font-size="5.8" class="lbl">${t}</text>`});
    s+=`<text x="${xs[ARD]+16}" y="${y-16}" font-size="5.8" class="lbl">MANIFOLD</text><text x="${xs[BV]-40}" y="${y-16}" font-size="5.8" text-anchor="end" class="lbl">P&amp;WV</text><text x="${xs[HOU]+36}" y="${y+25}" font-size="5.8" class="lbl">WESTLAND</text><text x="${xs[LAST]+26}" y="${y+13}" font-size="5.8" class="lbl">B&amp;O</text>`;
    // the engine, the job's own lit
    s+=`<g transform="translate(${me} ${y-1})"><rect x="-13" y="-5" width="26" height="10" rx="2" fill="var(--green)" stroke="var(--glow)" stroke-width="1.4"/><text x="0" y="2.4" font-size="6.4" text-anchor="middle" fill="#fff" font-weight="700">4619</text></g>`;
    return s+`</svg>`;
  },

  sheet(S){
    const G=S.road;if(!G)return "";
    const tr=G.tt.trains,cols=[...tr.filter(t=>t.dir===1),...tr.filter(t=>t.dir===-1)],short={"First class":"1st","Second class":"2nd"};
    let h=`<h3>Chartiers Branch</h3><div class="sub">Time-table · double track Carnegie to Houston, single track beyond · D = open office</div><div class="xw-tt" tabindex="0"><table><thead><tr><th>Station</th>`;
    cols.forEach(t=>h+=`<th>${esc(t.name)}<small>${t.dir===1?"South":"North"} · ${esc(short[t.cls]||t.cls)}</small></th>`);
    h+=`<th>X 4619<small>run min</small></th></tr></thead><tbody>`;
    ST.forEach((st,i)=>{
      h+=`<tr class="${i===G.pos&&!G.moving?"here":""}"><td class="stn">${esc(st.n)}<small>MP ${st.mp.toFixed(1)}${st.off?" · D":""}${st.sd?"":" · no siding"}${st.il?" · interlocking":""}</small></td>`;
      cols.forEach(t=>{
        const known=G.orders.some(o=>o.tr===t);
        h+=`<td>${known&&t.late&&t.lateAt&&t.lateAt[i]?`<span class="late"><s>${fmt(t.t[i])}</s><b>${fmt(t.t[i]+t.late)}</b></span>`:fmt(t.t[i])}</td>`});
      h+=`<td class="pencil">${i<LAST?G.tt.leg[i]:""}</td></tr>`;
    });
    h+=`</tbody></table></div><div class="xw-si"><b>Special instructions</b><ul><li>Northward trains are superior to southward trains of the same class.</li><li>One time shown is the leaving time (Rule 5).</li><li>Carnegie and Washington are inside yard limits.</li><li>Extras clear opposing regular trains by 5 minutes (Rule S-87).</li><li>Double track Carnegie to Houston: D- rules apply there.</li><li>Interlockings at Bridgeville, Hills and Washington.</li></ul></div>`;
    if(G.orders.length)h+=`<div class="xw-orders"><b>Orders held</b>${G.orders.map(o=>`<div class="ord">No ${o.no}: ${esc(o.text)}<span class="ok">OK</span></div>`).join("")}</div>`;
    h+=`<div class="xw-orders"><b>Work</b>${S.jobs.map(j=>`<div class="ord${j.done?" done":""}">${j.done?"✓ ":""}${esc(j.t)}</div>`).join("")}</div>`;
    return h;
  },

  build(H){
    const S=H.S,rnd=H.rnd,R=()=>H.R();
    const G={pos:0,dir:1,limit:HOU,inSiding:true,moving:null,orders:[],used:new Set(),bag:{},legs:0,depAt:0};
    S.road=G;
    /* ----- the time-table: our running times, and the other regular trains anchored at Houston ----- */
    const leg=[];for(let i=0;i<LAST;i++)leg[i]=Math.max(1,Math.round((ST[i+1].mp-ST[i].mp)*3.5)+rnd(-1,2));
    const run=(a,b)=>{let m=0;for(let i=Math.min(a,b);i<Math.max(a,b);i++)m+=leg[i];return m};
    const H0=coal.start+run(0,HOU);
    const mk=(id,name,dir,cls,f,anchor)=>{
      const t=ST.map(s=>Math.round(anchor+(dir===1?1:-1)*(s.mp-ST[HOU].mp)*f)),act=t.slice();
      return {id,name,dir,cls,t,act,late:0};
    };
    const trains=[
      mk("305","No 305",1,"First class",2.2,coal.start+rnd(16,32)+Math.round(ST[HOU].mp*2.2)), // follows us out of Carnegie
      mk("302","No 302",-1,"First class",2.2,H0+rnd(46,58)),
      mk("92","No 92",-1,"Second class",3.2,H0+rnd(70,90)),
      mk("307","No 307",1,"First class",2.2,H0+rnd(95,115)),
      mk("309","No 309",1,"First class",2.2,H0+rnd(135,160)),
      mk("304","No 304",-1,"First class",2.2,H0+rnd(150,185))];
    G.tt={trains,leg};
    G.run=run;
    const work=["Take the empties up the double track to Houston","Work the Westland branch","Run the single track to Arden and meet Extra 2231 North","Work the Manifold branch","Bring the loads back to Carnegie"];

    /* ----- Check a move from k to j: leaves at c, arrives at a. Returns the problems, worst first. ----- */
    function checkMove(k,j,c,a){
      const d=j>k?1:-1,probs=[];
      for(const tr of G.tt.trains){
        if(tr.dir===-d){ // opposing
          if(Math.max(k,j)<=HOU)continue; // all on double track: opposing trains use the other main (Rule D-71)
          const ent=d===1?Math.max(k,HOU):k,ext=d===1?j:Math.max(j,HOU); // the single-track part: where we enter and leave it
          const tEnt=c+run(k,ent),tExt=c+run(k,ext);
          if(tr.act[ent]<=tEnt)continue; // it has already cleared the end we enter by
          if(tr.act[ext]<tExt)probs.push({kind:"headon",tr}); // it leaves the far end before we reach it
          else if(tExt>tr.act[ext]-5)probs.push({kind:"margin",tr,by:Math.round(tr.act[ext]-tExt),at:ext});
        }else{ // same direction
          if(tr.act[k]<=c)continue; // already ahead of us
          // Rule 86: clear at j by the time it is due to leave k, the station in its rear
          if(a>tr.act[k]){
            if(tr.act[j]<=a)probs.push({kind:"rear",tr});
            else probs.push({kind:"r86",tr,by:Math.round(a-tr.act[k])});
          }
        }
      }
      const rank={headon:3,rear:3,margin:1,r86:1};
      probs.sort((x,y)=>rank[y.kind]-rank[x.kind]);
      return probs;
    }

    /* ----- the questions that depend on the draw: shown to the player, and listed once for the answer key ----- */
    const q={
      margin:(name,where,mins)=>({miss:true,sec:"sup",src:"SC · Rule S-87",title:"Too close to "+name,body:`You got into the siding at ${where} only ${mins} minutes ahead of ${name}'s time there. By how much must an extra clear the time of an opposing regular train?`,right:"Not less than 5 minutes",wrong:[["Any margin, as long as it is in the clear"],["Not less than 2 minutes"],["Only to the leaving time"]],ok:{marks:1},okText:"Right, and you did not.",why:"Rule S-87: extras must clear the time of opposing regular trains by not less than 5 minutes unless otherwise provided. The TT&TO primer quotes 10 minutes."}),
      r86:(name,where)=>({miss:true,sec:"sup",src:"SC · Rule 86",title:name+" was close behind",body:`${name} was due to leave the station behind you before you were in the clear at ${where}. When must an inferior train running ahead of a superior train be clear?`,right:"When the superior train is due to leave the next station in the rear where time is shown",wrong:[["5 minutes before the superior train is due at the station ahead"],["When the superior train comes in sight"],["At the superior train's arriving time at the station ahead"]],ok:{marks:1},okText:"Right, and you were not.",why:"Rule 86: unless otherwise provided, the inferior train must be clear at the time the superior train is due to leave the next station in the rear where time is shown."}),
      board:()=>({sec:"to",src:"SC · Rule 221",where:"Houston",title:"The train order board",body:"Coming into Houston, the semaphore at the open office shows its blade horizontal.",extra:semSvg(0),right:"Stop: an operator is on duty, and you must not leave without a Clearance Form A",wrong:[["Slow down and take orders on the fly"],["Proceed: it is only a block signal"],["Whistle — — and keep going"]],why:"Rule 221: the train order signal shows stop while an operator is on duty, and trains must not leave without a Clearance Form A. The semaphore guide adds that a horizontal blade is always stop."}),
      fix:(shown,nums)=>({sec:"to",src:"SC · Rule 211",title:"Check the clearance",body:`The clearance lists Nos ${shown}, but you hold Nos ${nums}. What do you do?`,right:"Do not leave; have the operator correct it with the dispatcher",wrong:[["Leave; the orders in hand are what count"],["Cross out the number and write the right one in"],["Leave and report it from the next office"]],why:"Rule 211: Clearance Form A is filled out without erasure or alteration, and conductors, enginemen and firemen must see that its information matches the orders received."}),
      who:(shown,nums)=>({sec:"to",src:"SC · Rule 211",title:"Check the clearance",body:`The clearance lists Nos ${shown} and you hold Nos ${nums}. Who on your crew must check that they match?`,right:"The conductor, the engineman and the fireman",wrong:[["Only the conductor"],["Only the engineman"],["The operator alone"]],why:"Rule 211: conductors, enginemen and firemen, and trainmen when practicable, must see that the information on Clearance Form A matches the train orders received."}),
      late:(no,text,name,L,where)=>({sec:"to",src:"SC · Form E",title:"Order No "+no,body:`“${text}.” What does this order do for you?`,right:`Run with respect to ${name}'s schedule ${L} minutes later`,wrong:[[`Ignore ${name} until Carnegie`],[`Wait at ${where} for ${name}`],[`You now have right over ${name}`]],why:"Form E, a time order: any train receiving it runs with respect to the later time exactly as it would to the regular schedule. The time-table on the right now shows the new times in red."})
    };
    // the answer key lists each draw-dependent question once
    [q.margin("[varies]","[varies]","[varies]"),q.r86("[varies]","[varies]"),q.board(),q.fix("[varies]","[varies]"),q.who("[varies]","[varies]"),q.late("[varies]","[varies] run [varies] mins late Washington to Carnegie","[varies]","[varies]","Houston")].forEach(H.key);
    Object.values(Qs).forEach(o=>H.key(o));ROAD.forEach(o=>H.key(o));STN.forEach(o=>H.key(o));
    ["bvS","hilS","hilN","bvN"].forEach(k=>H.key(aspectQ(k)));

    /* ----- a draw from a pool, each question once per run ----- */
    function draw(key,pool,p){
      if(R()>p)return null;
      let b=G.bag[key];if(!b||!b.length)b=G.bag[key]=H.shuffle(pool.map((_,i)=>i),R);
      return H.ask(pool[b.pop()]);
    }

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

    /* what lies between k and j: the signals at the interlockings, an order board going north, a question from the road */
    function passing(k,j){
      const d=j>k?1:-1,out=[];
      if(k===HOU&&d===1)out.push(H.ask(Qs.s71));
      for(let i=k+d;i!==j+d;i+=d){
        if(i===BV&&d===1&&!G.used.has("bvS")){G.used.add("bvS");out.push(H.ask(Qs.bvSem),H.wait(4,"Waited for the route at Bridgeville"),H.ask(aspectQ("bvS")))}
        if(i===BV&&d===-1&&!G.used.has("bvN")){G.used.add("bvN");out.push(H.ask(aspectQ("bvN")),H.wait(4,"Waited for the route at Bridgeville"))}
        if(i===HIL&&d===1&&!G.used.has("hilS")){G.used.add("hilS");out.push(H.ask(Qs.ilDef),H.ask(aspectQ("hilS")))}
        if(i===HIL&&d===-1&&!G.used.has("hilN")){G.used.add("hilN");out.push(H.ask(aspectQ("hilN")))}
        if(i===HOU&&d===-1&&!G.used.has("hou2")){G.used.add("hou2");out.push(H.ask(Qs.board2),H.ask(Qs.d71))}
      }
      if(!out.length){const ev=draw("road",ROAD,.45);if(ev)out.push(ev)}
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

    /* ----- the ends of the three stretches ----- */
    function endOfPhase(){
      if(G.phase==="A")houston();else if(G.phase==="B")arden();else carnegieEnd();
    }
    function houston(){
      G.phase="done-A";
      // orders: a time order on a regular train still to pass Houston northward, and the meet with Extra 2231 North
      const n1=rnd(11,19),orders=[];
      const cand=G.tt.trains.filter(tr=>tr.dir===-1&&tr.act[HOU]>S.clock+10);
      let late=null;
      if(cand.length&&R()<.7){
        const tr=cand[Math.floor(R()*cand.length)],L=[20,25,30,35][Math.floor(R()*4)];
        late={no:n1,text:`${tr.name} run ${L} mins late Washington to Carnegie`,tr,L};orders.push(late);
      }
      const meetNo=n1+orders.length;
      orders.push({no:meetNo,text:"Extra 4619 South meet Extra 2231 North at Arden"});
      const nums=orders.map(o=>o.no),wrongClear=R()<.5;
      const shown=wrongClear?nums.map((x,i)=>i===nums.length-1?x+3:x):nums;
      const clearTxt=`CLEARANCE FORM A\nTo Extra 4619 South  at HOUSTON\nI have ${shown.length} order${shown.length>1?"s":""} for your train.\nNos ${shown.join(", ")}\nOK  ${fmt(S.clock+3)}  RK, dispatcher`;
      const ordTxt=orders.map(o=>`<span class="no">Order No ${o.no}</span>\n${esc(o.text)}`).join("\n\n");
      const scenes=[
        H.done(0),
        H.info("Houston","Houston","<p>Extra 4619 South stands on the main at Houston, where the Westland branch leaves. The empties go to the mine; the order board is next.</p>"),
        H.ask(q.board()),
        H.info("Houston","Orders","<p>The operator hands up the orders and the clearance.</p><div class='xw-tele'>"+ordTxt+"</div><div class='xw-clear'>"+esc(clearTxt)+"</div>","Check them"),
        wrongClear?H.ask(q.fix(shown.join(", "),nums.join(", "))):H.ask(q.who(shown.join(", "),nums.join(", ")))];
      scenes.push(()=>{
        orders.forEach(o=>{G.orders.push(o);if(o.tr){const tr=o.tr;tr.late+=o.L;tr.lateAt=tr.act.map(x=>x>S.clock);tr.act=tr.act.map(x=>x>S.clock?x+o.L:x)}});
        if(wrongClear)H.addTime(6);
        H.log("Orders "+nums.join(", ")+" received");H.next()});
      if(late)scenes.push(H.ask(q.late(late.no,late.text,late.tr.name,late.L,"Houston")));
      scenes.push(H.ask(Qs.sa),
        H.ask(Qs.sh),
        H.info("Houston","The Westland branch",`<p>The Westland branch leaves the main at Houston (${lib("the Chartiers Branch's coal branches")}). Your crew pulls the empties off the main and sets them where the mine crew wants them, and picks up the loads.</p>`),
        H.ask(Qs.r104),H.ask(Qs.siding),
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
        H.ask(Qs.back),H.ask(Qs.back2),
        H.wait(30,"Manifold branch worked: loads out"),H.done(3),
        ()=>{G.phase="C";G.limit=0;G.dir=-1;G.inSiding=true;G.orders=G.orders.filter(o=>o.tr);H.log("Extra 4619 North ready at Arden");stationRoad()});
      H.next();
    }
    function carnegieEnd(){
      G.phase="done-C";
      H.front(H.ask(Qs.r93),H.ask(Qs.ylWhat),H.done(4));H.next();
    }

    const steps=[
      H.info("Carnegie","Called for 7:00",`<p>You are the conductor of Extra 4619 South, a freight extra from Carnegie, the Mansfield end of the Pennsylvania Railroad's Chartiers Branch. The branch runs south to Washington (${lib("Railroads of the Chartiers Valley")}). It has been double track as far as Houston since 1904.</p><p>The time-table on the right shows the regular trains. Northward trains are superior to southward trains of the same class, and your extra is inferior to every regular train. You have empties for the mines at Houston and Arden, and loads to bring back.</p>`,"Go to the caboose"),
      H.ask(Qs.ylWho),H.ask(Qs.s83),H.ask(Qs.r73),H.ask(Qs.r84),
      ()=>{G.phase="A";G.limit=HOU;G.dir=1;H.log("Extra 4619 South ready at Carnegie");stationRoad()}
    ];
    return {work,steps,noPar:true,end:()=>"Extra 4619 North is in the clear at Carnegie at {t}."};
  }
};

window.NevilleRuns=Object.assign(window.NevilleRuns||{},{coal});
})();
