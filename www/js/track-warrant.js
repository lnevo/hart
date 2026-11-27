/* The GCOR track warrant form, shared by the two track warrant games: the exam's modern run (exam/run-modern.js) and
   play's PIR run (play/warrant.js). BOXES are the seventeen boxes with their blanks; SAY is what the dispatcher says for
   each box, from the values in its blanks. One copy, so the two games cannot drift apart (the exam's lacked Box 4).
   Loaded before either game; it sets window.TrackWarrant. */
(function(){
"use strict";
/* The seventeen boxes of the form, with their blanks. */
const BOXES=[
  [1,"Track warrant no. {w} is void"],
  [2,"Proceed from {s} to {s} on {t} track"],
  [3,"Proceed from {s} to {s} on {t} track"],
  [4,"Work between {s} and {s} on {t} track"],
  [5,"Not in effect until {time}"],
  [6,"This authority expires at {time}"],
  [7,"Not in effect until after arrival of {train} at {s}"],
  [8,"Hold main track at last named point"],
  [9,"Do not foul limits ahead of {train}"],
  [10,"Clear main track at last named point"],
  [11,"Between {s} and {s} make all movements at restricted speed. Limits occupied by train."],
  [12,"Between {s} and {s} make all movements at restricted speed. Limits occupied by men or equipment."],
  [13,"Do not exceed {mph} MPH between {s} and {s}"],
  [14,"Do not exceed {mph} MPH between {s} and {s}"],
  [15,"Flag protection not required against following trains on the same track"],
  [16,"Track bulletins in effect"],
  [17,"Other specific instructions: {txt}"]];
/* What the dispatcher says for each box, from the values in its blanks. */
const SAY={1:v=>`Track warrant number ${v[0].split("").join(" ")} is void`,2:v=>`Proceed from ${v[0]} to ${v[1]} on ${v[2]} track`,3:v=>`Proceed from ${v[0]} to ${v[1]} on ${v[2]} track`,
  4:v=>`Work between ${v[0]} and ${v[1]} on ${v[2]} track`,5:v=>`Not in effect until ${v[0]}`,6:v=>`This authority expires at ${v[0]}`,7:v=>`Not in effect until after arrival of ${v[0]} at ${v[1]}`,
  8:()=>"Hold main track at last named point",9:v=>`Do not foul limits ahead of ${v[0]}`,10:()=>"Clear main track at last named point",
  11:v=>`Between ${v[0]} and ${v[1]} make all movements at restricted speed, limits occupied by train`,12:v=>`Between ${v[0]} and ${v[1]} make all movements at restricted speed, limits occupied by men or equipment`,
  13:v=>`Do not exceed ${v[0]} MPH between ${v[1]} and ${v[2]}`,14:v=>`Do not exceed ${v[0]} MPH between ${v[1]} and ${v[2]}`,
  15:()=>"Flag protection not required against following trains on the same track",16:()=>"Track bulletins in effect",17:v=>`Other specific instructions: ${v[0]}`};
window.TrackWarrant=Object.freeze({BOXES,SAY});
})();
