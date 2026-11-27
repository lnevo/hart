/* The track warrant form of Extra East: HART Railroad, "Up the Chartiers", for the 1997 PIR run. The dispatcher reads a
   warrant out a line at a time; the player checks the boxes he gives, fills in their blanks and repeats it back. It is the
   form of the Extra West game (exam/run.js: BOXES, SAY, the copy step), ported with this run's places and trains. The pure
   check is compare() and the blank form formHtml(), both from js/track-warrant.js; copy() is the scene. A wrong copy costs 2 minutes and one miss (GCOR 14.9), not a mark.
   It loads after road-engine.js and js/track-warrant.js (the form's BOXES and SAY) and before pir.js, and adds
   RoadEngine.twc.
 */
(function(){
"use strict";
const RE=window.RoadEngine;
const {esc,fmt}=RE;
const mins=t=>{const [h,m]=t.split(":");return +h*60+ +m};
const BASE_TIMES=["6:30","7:00","7:15","7:20","7:25","7:30","8:00"];
const reduced=typeof matchMedia==="function"&&matchMedia("(prefers-reduced-motion: reduce)").matches;

/* The choices in the blanks of the form: stations, tracks, warrant numbers, trains, speeds, the times and the "other
   specific instructions" the run's warrants use. time grows when a Box 5 time is read (see addTime). */
const TW_SEL={s:["Duff Junction","McKees Rocks","Carnegie","Bridgeville","Hills","Canonsburg","Houston","Arden"],t:["Main"],w:["112","114","118","121","125"],
  train:["Local 1","Local 2","PIR work train"],time:BASE_TIMES.slice(),mph:["10","15","20","25","30"],
  txt:["Joint with PIR work train between Hills and Canonsburg","Joint with Local 2 between Bridgeville and Canonsburg","Joint with Local 1 between Duff Junction and Bridgeville"]};
/* The form's boxes, the dispatcher's words, the blank form and the copy check: www/js/track-warrant.js. */
const {BOXES,SAY,formHtml,compare}=window.TrackWarrant;
/* The form as the player filled it in. The play-through test replaces this, since its fake page has no checkboxes. */
const api={BOXES,SAY,TW_SEL,compare,
  read(w,el){
    const got={};
    BOXES.forEach(([n])=>{const c=el.querySelector("#c"+n),row=el.querySelector("#row"+n);
      got[n]={on:!!(c&&c.checked),v:row?[...row.querySelectorAll("select")].map(s=>s.value):[]}});
    return got;
  },
  /* The words of one warrant, a box to a line, as the sheet prints them. */
  words(w){return Object.keys(w.boxes).map(Number).sort((a,b)=>a-b).map(b=>`Box ${b}. ${SAY[b](w.boxes[b])}.`)},
  /* The dispatcher's call: a time the warrant takes effect shows in the blank list. */
  /* A new run starts with the printed list of times. */
  resetTimes(){TW_SEL.time.length=0;TW_SEL.time.push(...BASE_TIMES)},
  addTime(t){if(!TW_SEL.time.includes(t)){TW_SEL.time.push(t);TW_SEL.time.sort((a,b)=>mins(a)-mins(b))}},
  /* A warrant is in effect once its OK time is on it, unless Box 5 or Box 7 holds it back. */
  effect(G,no){const w=G.warrants.find(x=>x.no===no);if(w)w.eff=true},
  release(G,no){const w=G.warrants.find(x=>x.no===no);if(w){w.released=true;w.eff=false}},
  /* The warrants held, for the sheet. */
  held(G){
    if(!G.warrants.length)return "";
    return `<div class="xw-orders"><b>Warrants held</b>${G.warrants.map(w=>`<div class="ord">No ${esc(w.no)}: ${w.words.map(esc).join(" ")}<span class="ok">${w.released?"released":"OK "+esc(w.ok)+" RK"}</span></div>`).join("")}</div>`;
  },
  /* The copy scene. w: no, at (the named point where it is read), to (the train it is addressed to), boxes. G.warrants
     records it once the OK time is on it. */
  copy(H,G,w){
    return ()=>{
      let tries=0;
      const to=w.to||"PIR Local 1";
      const lines=[`Track warrant number ${w.no.split("").join(" ")}, to ${to} at ${w.at}.`,...api.words(w),"Dispatcher RK. Read it back."];
      const form=formHtml(TW_SEL,esc);
      const el=H.scene(w.at,"Copy track warrant "+w.no,`<p>The dispatcher reads the warrant at copying speed, slowly enough for you to write it down. Check each box he gives and fill in its blanks, then repeat it back.</p><div class="xw-dict" id="dict"></div>
      <div class="xw-tw"><div class="hd">TRACK WARRANT No ${esc(w.no)} · Oct 15 1997<br><span style="font-weight:400">To ${esc(to)} at ${esc(w.at)}</span></div>${form}<div class="okline">OK ____  Dispatcher ____</div></div>
      <div class="choices"><button class="xw-btn primary" id="rb">Repeat it to the dispatcher</button></div><div class="result" hidden></div>`);
      // read it out a line at a time
      const d=H.$("dict");let i=0;
      const tick=()=>{if(d.isConnected===false)return;if(i<lines.length){d.textContent+=(i?"\n":"")+lines[i++];if(!reduced&&typeof setTimeout==="function")setTimeout(tick,650);else tick()}};
      tick();
      H.$("rb").onclick=()=>{
        const bad=compare(w,api.read(w,el,tries));
        BOXES.forEach(([n])=>{const row=el.querySelector("#row"+n);if(row)row.classList[bad.includes(n)?"add":"remove"]("bad")});
        const r=el.querySelector(".result");r.hidden=false;
        if(bad.length){
          tries++;H.addTime(2);H.renderStatus();
          r.innerHTML=`<div class="verdict no">“That's not what I gave you.” <small style="font-size:14px;font-family:var(--mono)">+2 min</small></div><p>The dispatcher corrects box${bad.length>1?"es":""} ${bad.join(", ")}. Fix the shaded rows and repeat it again.</p>`+(tries>=2?`<p class="src">The dispatcher's words are in the blue panel above. Each box he names is checked, with its blanks in the order he reads them.</p>`:"");
          H.log("Warrant "+w.no+" read back with errors in "+bad.join(", "));
          if(tries===1)H.S.misses.push({title:"Copying track warrant "+w.no,why:"GCOR 14.9: the employee writes all the information and repeats it, preprinted and written words, to the dispatcher, who checks it before giving the OK.",src:"GC · 14.9",sec:"twc"});
        }else{
          const ok=fmt(H.S.clock+1);w.ok=ok;
          const line=el.querySelector(".okline");if(line)line.innerHTML=`OK <b>${ok}</b>  Dispatcher <b>RK</b>`;
          H.$("rb").disabled=true;
          r.innerHTML=`<div class="verdict ok">“That is correct. OK ${ok}, RK.”</div><div><button class="xw-btn primary" id="xwGo">Continue</button></div>`;
          H.log("Warrant "+w.no+" OK "+ok);
          H.addTime(1);
          G.warrants.push({no:w.no,ok,words:api.words(w),boxes:w.boxes,eff:!(w.boxes[5]||w.boxes[7]),released:false});
          H.renderStatus();
          const go=H.$("xwGo");go.onclick=()=>{go.disabled=true;H.next()};
        }
      };
    };
  }};
RE.twc=api;
})();
