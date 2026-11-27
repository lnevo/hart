/* The GCOR track warrant form and its copy scene, shared by the two track warrant games: the exam's modern run
   (exam/run-modern.js) and play's PIR run (play/warrant.js). BOXES are the seventeen boxes with their blanks; SAY is
   what the dispatcher says for each box, from the values in its blanks. formHtml draws the blank form, readForm reads
   it back and compare checks a copy of it. copyScene is the scene where the dispatcher reads a warrant out and the
   player copies it and repeats it back. One copy, so the two games cannot drift apart. Loaded before either game; it
   sets window.TrackWarrant. */
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
/* The blank form: each box with a checkbox and, for each blank, a list of the game's choices. sel holds the choices by
   blank kind (s, t, w, train, time, mph, txt); esc is the game's HTML escape. */
function formHtml(sel,esc){
  return BOXES.map(([n,txt])=>{
    let k=0;
    const blank=(_,t)=>{
      if(!sel[t])throw new Error(`track warrant form: no choices for the {${t}} blank of box ${n}`);
      const id=`b${n}_${k++}`;
      return `<select id="${id}" aria-label="Box ${n} blank ${k}"><option value="">—</option>`+
        `${sel[t].map(v=>`<option>${esc(v)}</option>`).join("")}</select>`;
    };
    const body=esc(txt).replace(/\{(\w+)\}/g,blank);
    return `<label class="box" id="row${n}"><input type="checkbox" id="c${n}"><span class="n">${n}</span><span>${body}</span></label>`;
  }).join("");
}
/* The check: w.boxes is {box: [values]} for the boxes the dispatcher gave; got is {box: {on, v}} as the player filled the
   form, where a box left out of got counts as unchecked and blank. Returns the numbers of the boxes that are wrong:
   checked when not given, not checked when given, or with a blank that differs. */
function compare(w,got){
  const bad=[];
  BOXES.forEach(([n])=>{
    const want=w.boxes[n],g=got[n]||{on:false,v:[]};
    if(!!want!==!!g.on){bad.push(n);return}
    if(want&&want.some((x,i)=>(g.v||[])[i]!==x))bad.push(n);
  });
  return bad;
}
/* The form as the player filled it, from the scene element root: {box: {on, v}}, on for the checkbox and v the blanks'
   values in order. */
function readForm(root){
  return Object.fromEntries(BOXES.map(([n])=>{
    const check=root.querySelector("#c"+n),row=root.querySelector("#row"+n);
    if(!check||!row)throw new Error(`track warrant form: box ${n} is not on the page`);
    return [n,{on:check.checked,v:[...row.querySelectorAll("select")].map(s=>s.value)}];
  }));
}
/* The dispatcher's line for each box of warrant w, in box order, as the sheet prints them. Every box must have its
   values by now. */
function boxLines(w){
  const nums=Object.keys(w.boxes).map(Number).sort((a,b)=>a-b);
  const unset=nums.filter(b=>!Array.isArray(w.boxes[b]));
  if(unset.length)throw new Error(`warrant ${w.no}: box ${unset.join(", ")} read out before it was filled`);
  return nums.map(b=>`Box ${b}. ${SAY[b](w.boxes[b])}.`);
}
/* Everything the dispatcher says for warrant w addressed to train `to`, a line at a time. */
function dispatcherLines(w,to){
  return [`Track warrant number ${w.no.split("").join(" ")}, to ${to} at ${w.at}.`,...boxLines(w),"Dispatcher RK. Read it back."];
}

/* The time between two lines of the dispatcher's reading, in milliseconds. */
const LINE_MS=650;
/* What a wrong read-back costs and what the OK takes, in minutes of the game clock. */
const WRONG_COPY_MIN=2,OK_MIN=1;
/* What the copy scene takes from its game, and the texts each game gives it. */
const GAME_NEEDS=["scene","$","esc","fmt","addTime","renderStatus","log","next"];
const OPTION_TEXTS=["to","date","intro"];
function checkCopyInputs(game,w,opt){
  const missing=GAME_NEEDS.filter(k=>typeof game[k]!=="function");
  if(missing.length)throw new TypeError(`track warrant copy scene: the game gives no ${missing.join(", ")}`);
  if(!w||typeof w.no!=="string"||typeof w.at!=="string"||!w.boxes)
    throw new TypeError("track warrant copy scene: a warrant needs no, at and boxes");
  const noText=OPTION_TEXTS.filter(k=>typeof opt[k]!=="string"||!opt[k]);
  if(noText.length)throw new TypeError(`track warrant ${w.no}: the copy scene has no ${noText.join(", ")}`);
  if(!opt.sel)throw new TypeError(`track warrant ${w.no}: the copy scene has no blank choices (sel)`);
  if(typeof opt.reduced!=="boolean")throw new TypeError(`track warrant ${w.no}: reduced must be true or false`);
}
/* The copy scene for warrant w, as a function the game queues. game: scene, $, esc, fmt, addTime, renderStatus, log,
   next, and S, the state with its clock and misses when the scene runs. opt: sel, the choices in the blanks (see
   formHtml); to, the train the warrant is addressed to; date, the date on the form; intro, the sentence above the
   form; reduced, true for no reading animation; read(el, tries), the form as filled, readForm by default; onRight(ok),
   called with the OK time once the copy is right. A wrong copy costs WRONG_COPY_MIN minutes and, the first time, a
   miss (GCOR 14.9); a right one puts the OK time on the warrant. */
function copyScene(game,w,opt){
  checkCopyInputs(game,w,opt);
  const read=opt.read||(el=>readForm(el));
  return ()=>{
    let tries=0;
    const {esc,$}=game;
    const lines=dispatcherLines(w,opt.to);
    const el=game.scene(w.at,"Copy track warrant "+w.no,`<p>${opt.intro}</p><div class="xw-dict" id="dict"></div>
      <div class="xw-tw"><div class="hd">TRACK WARRANT No ${esc(w.no)} · ${esc(opt.date)}<br><span style="font-weight:400">To ${esc(opt.to)} at ${esc(w.at)}</span></div>${formHtml(opt.sel,esc)}<div class="okline">OK ____  Dispatcher ____</div></div>
      <div class="choices"><button class="xw-btn primary" id="rb">Repeat it to the dispatcher</button></div><div class="result" hidden></div>`);
    // read it out a line at a time
    const dict=$("dict");
    let shown=0;
    const tick=()=>{
      if(dict.isConnected===false)return;
      if(shown<lines.length){
        dict.textContent+=(shown?"\n":"")+lines[shown++];
        if(!opt.reduced&&typeof setTimeout==="function")setTimeout(tick,LINE_MS);
        else tick();
      }
    };
    tick();
    $("rb").onclick=()=>{
      const bad=compare(w,read(el,tries));
      BOXES.forEach(([n])=>el.querySelector("#row"+n).classList[bad.includes(n)?"add":"remove"]("bad"));
      const result=el.querySelector(".result");
      result.hidden=false;
      if(bad.length){
        tries++;
        copiedWrong(game,w,bad,tries,result);
      }else copiedRight(game,w,el,result,opt.onRight);
    };
  };
}
function copiedWrong(game,w,bad,tries,result){
  game.addTime(WRONG_COPY_MIN);
  game.renderStatus();
  result.innerHTML=`<div class="verdict no">“That's not what I gave you.” <small style="font-size:14px;font-family:var(--mono)">+${WRONG_COPY_MIN} min</small></div>`+
    `<p>The dispatcher corrects box${bad.length>1?"es":""} ${bad.join(", ")}. Fix the shaded rows and repeat it again.</p>`+
    (tries>=2?`<p class="src">The dispatcher's words are in the blue panel above. Each box he names is checked, with its blanks in the order he reads them.</p>`:"");
  game.log("Warrant "+w.no+" read back with errors in "+bad.join(", "));
  if(tries===1)game.S.misses.push({title:"Copying track warrant "+w.no,
    why:"GCOR 14.9: the employee writes all the information and repeats it, preprinted and written words, "+
      "to the dispatcher, who checks it before giving the OK.",src:"GC · 14.9",sec:"twc"});
}
function copiedRight(game,w,el,result,onRight){
  const ok=game.fmt(game.S.clock+OK_MIN);
  w.ok=ok;
  el.querySelector(".okline").innerHTML=`OK <b>${ok}</b>  Dispatcher <b>RK</b>`;
  game.$("rb").disabled=true;
  result.innerHTML=`<div class="verdict ok">“That is correct. OK ${ok}, RK.”</div><div><button class="xw-btn primary" id="xwGo">Continue</button></div>`;
  game.log("Warrant "+w.no+" OK "+ok);
  game.addTime(OK_MIN);
  if(onRight)onRight(ok);
  game.renderStatus();
  const go=game.$("xwGo");
  go.onclick=()=>{go.disabled=true;game.next()};
}
window.TrackWarrant=Object.freeze({BOXES,SAY,formHtml,readForm,compare,boxLines,dispatcherLines,copyScene});
})();
