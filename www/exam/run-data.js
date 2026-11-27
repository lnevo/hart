/* Extra East's data: the railroad's stations, the regular trains, the time order, the train sheets' special
   instructions, the modern run's warrant plan and the semaphore picture. The game (run.js, run-modern.js) and its
   answer key (scripts/build_exam_answers.js) read the same tables: run.html loads this file before run.js, and in
   node require() gives the same object. */
(function(root){
"use strict";
/* The stations from Ashby (MP 100) to Ironton: n name, mp milepost, sd a siding, yl yard limits, off an open office. */
const STATIONS=[
  {n:"Ashby",mp:100.0,sd:1,yl:1,off:1},
  {n:"Birchwood",mp:106.0,sd:1},
  {n:"Cobb",mp:111.5,sd:1,off:1},
  {n:"Dunmore",mp:117.5,sd:1,off:1},
  {n:"Elk Gap",mp:123.0,sd:1},
  {n:"Fenwick",mp:128.5,sd:0},
  {n:"Granite",mp:134.0,sd:1,off:1},
  {n:"Hollis",mp:140.0,sd:1},
  {n:"Ironton",mp:146.0,sd:1,yl:1,off:1}];

/* The regular trains of time-table No 12: the first station's time (minutes from midnight), the spread drawn around it,
   and minutes per mile. makeTT draws their schedules in this order; the answer key names the first westward one. */
const REGULARS=[
  {id:"1",name:"No 1",dir:"W",cls:"First class",start:370,spread:[-4,8],f:2.6},
  {id:"2",name:"No 2",dir:"E",cls:"First class",start:420,spread:[-6,6],f:2.6},
  {id:"21",name:"No 21",dir:"W",cls:"Second class",start:470,spread:[-8,8],f:3.4}];

/* The time order an open office gives on a westward regular train still ahead: the range its number is drawn from, the
   minutes late it may name, and its words. The answer key shows it with the first of each. */
const TIME_ORDER={no:[11,19],late:[20,25,30,35],words:(train,L)=>`${train} run ${L} mins late Ironton to Ashby`};

/* The special instructions on each run's sheet, one list item each. The speed signals run puts the manual block first
   (sheetSignals). The answer key prints the 1949 list with the time-table. */
const SHEET_NOTES={
  tto:["Westward trains are superior to eastward trains of the same class.",
    "One time shown is the leaving time (Rule 5).","Ashby and Ironton are inside yard limits.",
    "Extras clear opposing regular trains by 5 minutes (Rule S-87).",
    "Double track Hollis to Ironton: D- rules apply there."],
  twc:["Main track between the yard limits is governed by track warrant (GCOR 14).",
    "Ashby and Ironton yard limits: GCOR 6.13.","Double track Hollis to Ironton: Main 1 eastward, Main 2 westward.",
    "Dispatcher: RK."],
  yard:["Ironton yard limits include Main 1 and Main 2 (GCOR 6.13).",
    "Main 1 eastward, Main 2 westward (current of traffic).",
    "Yard tracks and the Kestrel Feed spur are not main track: GCOR 6.28.","East of CP Ironton East: CTC."],
  signals:["Interlocking at Granite, where the line crosses another railroad.",
    "River bridge: high water detector, P plate signal.","The grade below Granite: G plate signal.",
    "Double track Hollis to Ironton."]};

/* The run's three warrants. boxes are on the warrant every run. Each draw is a pair of box sets, the first taken when
   the run draws true: box12 (Box 12, men or equipment; else Boxes 11 and 17, joint with work train 292) and hold (Box 8;
   else Box 10). Box 5 of 101 is null until the crew calls: setBox5 sets it box5Lead minutes on, rounded up to 5. */
const TWC_PLAN={box5Lead:12,warrants:{
  w1:{no:"101",at:"Ashby",boxes:{2:["Ashby","Dunmore","Main"],5:null,10:[],15:[]},
    draws:{box12:[{12:["Birchwood","Cobb"]},
      {11:["Birchwood","Cobb"],17:["Joint with work train 292 between Birchwood and Cobb"]}]}},
  w2:{no:"102",at:"Dunmore",boxes:{2:["Dunmore","Granite","Main"],6:["9:00"],7:["2211 West","Dunmore"]},
    draws:{hold:[{8:[]},{10:[]}]}},
  w3:{no:"103",at:"Granite",boxes:{1:["102"],2:["Granite","Hollis","Main"],3:["Hollis","Ironton","Main 2"],
    13:["40","Granite","Hollis"],14:["30","Hollis","Ironton"],16:[]}}}};

/* semaphore picture, angle in degrees (0 = horizontal, upper quadrant) */
function semSvg(a){
  const r=a*Math.PI/180;
  return `<svg viewBox="0 0 120 120" width="110" height="110" aria-label="Semaphore, blade at ${a} degrees" role="img" style="align-self:flex-start"><rect x="57" y="20" width="6" height="96" fill="#1d2733"/><circle cx="60" cy="16" r="5" fill="#1d2733"/><g transform="rotate(${-a} 60 40)"><rect x="60" y="34" width="52" height="11" fill="#a3302b" stroke="#1d2733" stroke-width="1.5"/><rect x="100" y="34" width="4" height="11" fill="#fff"/></g><circle cx="52" cy="40" r="6" fill="#f3ecbf" stroke="#1d2733" stroke-width="1.5"/></svg>`;
}

const api={STATIONS,REGULARS,TIME_ORDER,SHEET_NOTES,TWC_PLAN,semSvg};
root.ExtraEastData=api;
if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window!=="undefined"?window:globalThis);
