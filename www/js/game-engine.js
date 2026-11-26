/* The scene engine of the two rules games, Extra East (exam/run.js) and Extra East: HART Railroad (play/play.js).
   A run is a queue of scenes: ask() is a decision with a source, info() a page with one button. Each game passes in
   what differs: its state, how it draws the status and sheet, how its clock runs, and the words on its end screens.
   Loaded before the game's own script; in node, require() gives the same object (scripts/tests/game_engine_test.js). */
(function(root){
"use strict";
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
/* A random stream from a string: the same string gives the same draws (play's daily run). */
function seeded(str){
  let h=1779033703^str.length;
  for(let i=0;i<str.length;i++){h=Math.imul(h^str.charCodeAt(i),3432918353);h=h<<13|h>>>19}
  let a=h>>>0;
  return ()=>{a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296};
}
const rnd=(a,b,rand)=>a+Math.floor(rand()*(b-a+1)); // a whole number from a to b, both included
const pick=(a,rand)=>a[Math.floor(rand()*a.length)];
const shuffle=(a,rand)=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(rand()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
/* Minutes after midnight as h:mm on a 24-hour face, in both games: a run past midnight reads 0:15, not 24:15. */
const fmt=m=>{
  m=Math.round(m);m=((m%1440)+1440)%1440;
  const h=Math.floor(m/60),mm=m%60;return h+":"+String(mm).padStart(2,"0");
};
/* localStorage as JSON; a private window or blocked storage reads the default and drops the write. */
const store={
  get(k,d){try{const v=localStorage.getItem(k);return v?JSON.parse(v):d}catch(e){return d}},
  set(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
};
const MAX_MARKS=5; // five marks end a run in both games

/* The rule sources and the C&E study deck's sections, for both games and both answer keys. A question's src starts
   with a source key ("GC · 6.3") and its sec names a section. DECK_SECTIONS are the deck's eight in its order;
   SECTIONS adds the P&OV blog, which only play asks from. */
const SOURCES={SC:"1949 Standard Code",GC:"GCOR",TT:"TT&TO primer",YL:"Yard Limits guide",TW:"Track Warrants guide",
  SG:"Signals guide",SM:"Semaphores guide",PV:"Mark Connolly's P&OV blog,"};
const DECK_SECTIONS={def:"Definitions",sup:"Superiority & movement",to:"Train orders",sig:"Signals & whistles",
  sem:"Semaphores",yl:"Yard limits",twc:"Track warrants",gcor:"GCOR crew & speed"};
const SECTIONS={...DECK_SECTIONS,pov:"The P&OV jobs"};
const PLAY_DOTLESS=["GC","YL","PV"]; // Extra East: HART Railroad drops the dot after these; the exam keeps every dot
const SOURCE_KEY=new RegExp("^("+Object.keys(SOURCES).join("|")+")\\b( ·)?");
/**
 * A src with its key written out: "GC · 6.3" reads "GCOR · 6.3". A key in dotless also drops the " ·" after it
 * (play writes "GCOR 6.3"). A src without a known key is returned as it is.
 * @param {string} s @param {string[]} [dotless] @returns {string}
 */
const srcLabel=(s,dotless=[])=>s.replace(SOURCE_KEY,(m,k,dot)=>SOURCES[k]+(dot&&!dotless.includes(k)?dot:""));

/**
 * The part of a game's run state the engine reads and writes.
 * @typedef {Object} RunState
 * @property {number} clock   minutes after midnight
 * @property {number} marks   marks on the record; MAX_MARKS ends the run
 * @property {{title:string,why:string,src:string,url:(string|undefined),sec:string,end:boolean}[]} misses
 * @property {string[]} log   the log lines, "h:mm  text"
 * @property {boolean} ended  set by the game's finish(); next() does nothing after it
 */
/**
 * What a game hands the engine.
 * @typedef {Object} EngineConfig
 * @property {function():RunState} state        the current run
 * @property {function():void} render           redraws the status bar and the sheet
 * @property {function():string} hereName       where the run is, for a scene without its own place
 * @property {function(number):void} addTime    adds minutes to the clock, by the game's own pace
 * @property {function(Object):number} costMinutes  the minutes a wrong answer's cost shows
 * @property {function(Object):function():number} choiceRandom  the stream that orders an ask's choices
 * @property {function(Object):string} srcHtml   the source line under a verdict
 * @property {function(string,boolean):void} finish  ends the run with its last words
 * @property {{endVerdict:string,endText:string,marksText:string,smallTag:string}} words
 * @property {boolean} lockGo                    disable Continue once it is pressed
 * @property {function(HTMLElement):void} [afterScene]   after a scene is drawn
 * @property {function(HTMLElement,HTMLElement):void} [afterResult]  after a verdict is drawn
 */
/** @param {EngineConfig} cfg */
function createEngine(cfg){
  const $=id=>document.getElementById(id);
  const clock=fmt;
  let queue=[];
  const push=(...fns)=>{queue.push(...fns)};
  const front=(...fns)=>{queue.unshift(...fns)};
  const reset=fns=>{queue=fns?fns.slice():[]};
  function next(){
    if(cfg.state().ended)return;
    const f=queue.shift();
    if(f)f();
  }
  function log(t){
    const S=cfg.state(),line=clock(S.clock)+"  "+t;
    S.log.push(line);const li=document.createElement("li");li.textContent=line;$("xwLog").appendChild(li);
  }
  function scene(where,title,html){
    const el=$("xwScene");el.classList.remove("in");void el.offsetWidth;el.classList.add("in");
    el.innerHTML=`<div class="where"><span>${esc(where)}</span><span>${clock(cfg.state().clock)}</span></div>`+
      `<h2>${esc(title)}</h2>${html}`;
    cfg.render();
    if(cfg.afterScene)cfg.afterScene(el);
    return el;
  }
  /* A decision. right = the answer; wrong = [[text, cost, why?]]; cost {min, marks, end, endText}.
     why = explanation shown after any answer, note = a situational sentence after it; src = the rule's source;
     sec = the study deck section; miss = record it although the answer is right. */
  function ask(o){
    return ()=>{
      const S=cfg.state();
      const opts=shuffle([{t:o.right,ok:true,c:o.ok||{}},
        ...o.wrong.map(w=>({t:w[0],ok:false,c:w[1]||{min:5,marks:1},why:w[2]}))],cfg.choiceRandom(o));
      const buttons=opts.map((x,i)=>`<button class="xw-btn opt" data-i="${i}">${esc(x.t)}</button>`).join("");
      const el=scene(o.where||cfg.hereName(),o.title,
        `<p>${o.body}</p>${o.extra||""}<div class="choices">${buttons}</div><div class="result" hidden></div>`);
      const box=el.querySelector(".choices");
      box.querySelectorAll(".opt").forEach(b=>b.onclick=()=>{
        const x=opts[+b.dataset.i];
        box.classList.add("done");box.querySelectorAll(".opt").forEach(z=>z.disabled=true);
        b.classList.add(x.ok?"right":"wrong");
        if(!x.ok)box.querySelectorAll(".opt").forEach((z,i)=>{if(opts[i].ok)z.classList.add("right")});
        const c=x.c||{};
        if(c.min)cfg.addTime(c.min);
        if(c.marks)S.marks+=c.marks;
        const res=el.querySelector(".result");res.hidden=false;
        const cost=[];
        if(c.min)cost.push("+"+cfg.costMinutes(c)+" min");
        if(c.marks)cost.push("+"+c.marks+" mark"+(c.marks>1?"s":""));
        const ruleWhy=o.why+(o.note?" "+o.note:"");
        const why=(!x.ok&&x.why?x.why+" ":"")+ruleWhy;
        const verdict=x.ok?(o.okText||"Right."):(c.end?cfg.words.endVerdict:"Not right.");
        const costHtml=cost.length?" "+cfg.words.smallTag+cost.join(" · ")+"</small>":"";
        const goText=c.end||S.marks>=MAX_MARKS?"See the record":"Continue";
        res.innerHTML=`<div class="verdict ${x.ok?"ok":"no"}">${verdict}${costHtml}</div><p>${why}</p>`+
          `<div class="src">${cfg.srcHtml(o)}</div><div><button class="xw-btn primary" id="xwGo">${goText}</button></div>`;
        // miss: the answer is right, but it records what the player had just done wrong
        if(!x.ok||o.miss)S.misses.push({title:o.title,why:ruleWhy,src:o.src,url:o.url,sec:o.sec,end:!!c.end});
        log((x.ok?"✓ ":"✗ ")+o.title);
        if(o.after)o.after(x.ok,x);
        cfg.render();
        const go=$("xwGo");go.focus({preventScroll:true});
        if(cfg.afterResult)cfg.afterResult(res,go);
        go.onclick=()=>{
          if(cfg.lockGo)go.disabled=true;
          if(c.end){cfg.finish(c.endText||o.endText||cfg.words.endText,true);return}
          if(S.marks>=MAX_MARKS){cfg.finish(cfg.words.marksText,true);return}
          next();
        };
      });
    };
  }
  /* A page with one button; after runs before the next scene. */
  function info(where,title,html,btn,after){
    return ()=>{
      scene(where||cfg.hereName(),title,`${html}<div><button class="xw-btn primary" id="xwGo">${esc(btn||"Continue")}</button></div>`);
      const go=$("xwGo");
      go.onclick=()=>{if(cfg.lockGo)go.disabled=true;if(after)after();next()};
      go.focus({preventScroll:true});
    };
  }
  return {push,front,reset,next,log,scene,ask,info};
}

const api={esc,seeded,rnd,pick,shuffle,fmt,store,MAX_MARKS,SOURCES,DECK_SECTIONS,SECTIONS,PLAY_DOTLESS,srcLabel,createEngine};
root.GameEngine=api;
if(typeof module!=="undefined"&&module.exports)module.exports=api;
})(typeof window!=="undefined"?window:globalThis);
