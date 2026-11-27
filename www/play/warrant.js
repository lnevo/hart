/* The track warrant form of Extra East: HART Railroad, "Up the Chartiers", for the 1997 PIR run. The dispatcher reads a
   warrant out a line at a time; the player checks the boxes he gives, fills in their blanks and repeats it back. The
   form, its check and the copy scene are js/track-warrant.js, shared with the exam's modern run; this file gives them
   this run's places, trains and times. A wrong copy costs 2 minutes and one miss (GCOR 14.9), not a mark.
   It loads after road-engine.js and js/track-warrant.js and before pir.js, and adds RoadEngine.twc.
 */
(function(){
"use strict";
const RE=window.RoadEngine;
const {esc}=RE;
const mins=t=>{const [h,m]=t.split(":");return +h*60+ +m};
const BASE_TIMES=["6:30","7:00","7:15","7:20","7:25","7:30","8:00"];
const reduced=typeof matchMedia==="function"&&matchMedia("(prefers-reduced-motion: reduce)").matches;

/* The choices in the blanks of the form: stations, tracks, warrant numbers, trains, speeds, the times and the "other
   specific instructions" the run's warrants use. time grows when a Box 5 time is read (see addTime). */
const TW_SEL={s:["Duff Junction","McKees Rocks","Carnegie","Bridgeville","Hills","Canonsburg","Houston","Arden"],t:["Main"],w:["112","114","118","121","125"],
  train:["Local 1","Local 2","PIR work train"],time:BASE_TIMES.slice(),mph:["10","15","20","25","30"],
  txt:["Joint with PIR work train between Hills and Canonsburg","Joint with Local 2 between Bridgeville and Canonsburg","Joint with Local 1 between Duff Junction and Bridgeville"]};
/* The form's boxes, the dispatcher's words, the form and its check, and the copy scene: www/js/track-warrant.js. */
const {BOXES,SAY,readForm,compare,boxLines,copyScene}=window.TrackWarrant;
const api={BOXES,SAY,TW_SEL,compare,
  /* The form as the player filled it in. The play-through test replaces this, since its fake page has no checkboxes. */
  read(w,el){return readForm(el)},
  /* The words of one warrant, a box to a line, as the sheet prints them. */
  words:boxLines,
  /* A new run starts with the printed list of times. */
  resetTimes(){TW_SEL.time.length=0;TW_SEL.time.push(...BASE_TIMES)},
  /* The dispatcher's call: a time the warrant takes effect shows in the blank list. */
  addTime(t){if(!TW_SEL.time.includes(t)){TW_SEL.time.push(t);TW_SEL.time.sort((a,b)=>mins(a)-mins(b))}},
  /* A warrant is in effect once its OK time is on it, unless Box 5 or Box 7 holds it back. */
  effect(G,no){const w=G.warrants.find(x=>x.no===no);if(w)w.eff=true},
  release(G,no){const w=G.warrants.find(x=>x.no===no);if(w){w.released=true;w.eff=false}},
  /* The warrants held, for the sheet. */
  held(G){
    if(!G.warrants.length)return "";
    return `<div class="xw-orders"><b>Warrants held</b>${G.warrants.map(w=>`<div class="ord">No ${esc(w.no)}: ${w.words.map(esc).join(" ")}<span class="ok">${w.released?"released":"OK "+esc(w.ok)+" RK"}</span></div>`).join("")}</div>`;
  },
  /* The copy scene (js/track-warrant.js copyScene). w: no, at (the named point where it is read), to (the train it is
     addressed to), boxes. G.warrants records it once the OK time is on it. */
  copy(H,G,w){
    if(typeof w.to!=="string"||!w.to)throw new TypeError(`warrant ${w.no}: no train it is addressed to (to)`);
    return copyScene(H,w,{sel:TW_SEL,to:w.to,date:"Oct 15 1997",reduced,
      intro:"The dispatcher reads the warrant at copying speed, slowly enough for you to write it down. Check each box he gives and fill in its blanks, then repeat it back.",
      read:(el,tries)=>api.read(w,el,tries),
      onRight:ok=>G.warrants.push({no:w.no,ok,words:api.words(w),boxes:w.boxes,eff:!(w.boxes[5]||w.boxes[7]),released:false})});
  }};
RE.twc=api;
})();
