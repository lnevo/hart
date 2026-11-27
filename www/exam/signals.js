/* Signals shared by the study deck (index.html), the Extra East game (run.html) and the answer-key build.
   Data in the guides' own words: the Standard Code speed signals (Rules 281-292), the Signals guide's route
   signal chart and its plates. In a page it is a plain script whose names are globals to the scripts loaded after
   it; in node require() returns the same names (the answer key's build reads them so). */
/* A key that none of the tables below holds: an arm or lamp letter, or a plate. `table` names the table, `key` is the
   key asked for and `where` the call it came in, with its argument. */
class UnknownSignalKey extends Error{
  constructor(table,key,where){
    super(`${where}: ${JSON.stringify(key)} is not in ${table}`);
    this.name="UnknownSignalKey";
    this.table=table;
    this.key=key;
  }
}
/* The entry for key in table (named tableName), or UnknownSignalKey naming the call `where`. */
function signalEntry(table,tableName,key,where){
  if(!Object.prototype.hasOwnProperty.call(table,key))throw new UnknownSignalKey(tableName,key,where);
  return table[key];
}

/* A speed-signal drawing: semaphore arms top to bottom, as the Standard Code draws them (Rules 281-292).
   R red horizontal, Y yellow 45 degrees up, G green vertical. */
const ARM={R:{a:0,c:"#b8322b",t:"#fff",w:"red, horizontal"},Y:{a:-45,c:"#e0b52a",t:"#1d2733",w:"yellow, 45° up"},G:{a:-90,c:"#2d7a4a",t:"#fff",w:"green, vertical"}};
/* The arms of a semaphore as letters, each checked against ARM; `where` names the call for the error. */
function armsOf(arms,where){
  if(typeof arms!=="string"||!arms)throw new TypeError(`${where}: the arms must be a string of letters, not ${JSON.stringify(arms)}`);
  return [...arms].map(k=>signalEntry(ARM,"ARM",k,`${where}(${JSON.stringify(arms)})`));
}
const armWords=arms=>armsOf(arms,"armWords").map(A=>A.w).join("; ");
function sigFig(arms,plate){
  const n=arms.length,top=34,gap=46,h=top+(n-1)*gap+34;
  let g="";
  armsOf(arms,"sigFig").forEach((A,i)=>{const y=top+i*gap,k=arms[i];
    g+=`<g transform="rotate(${A.a} 30 ${y})"><rect x="30" y="${y-5}" width="34" height="10" fill="none" stroke="currentColor" stroke-width="2"/></g><circle cx="30" cy="${y}" r="9" fill="${A.c}" stroke="currentColor" stroke-width="1.5"/><text x="30" y="${y+4}" text-anchor="middle" font-size="11" font-weight="700" fill="${A.t}" font-family="system-ui,sans-serif">${k}</text>`});
  const pl=plate?`<rect x="24" y="${h-30}" width="${plate.length>1?28:20}" height="15" fill="#f5f0e1" stroke="currentColor" stroke-width="1.5"/><text x="${24+(plate.length>1?14:10)}" y="${h-19}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#1d2733" font-family="system-ui,sans-serif">${plate}</text>`:"";
  return `<svg class="ce-sig" viewBox="0 0 76 ${h}" width="76" height="${h}" role="img" aria-label="Semaphore signal, arms top to bottom: ${armWords(arms)}${plate?", "+plate+" plate":""}"><line x1="21" y1="${top-14}" x2="21" y2="${h-6}" stroke="currentColor" stroke-width="3"/><line x1="10" y1="${h-6}" x2="32" y2="${h-6}" stroke="currentColor" stroke-width="4"/>${g}${pl}</svg>`;
}

/* A color-light route signal: heads top to bottom, R red, Y yellow, G green (Signals guide chart). */
const LAMP={R:{c:"#c0392b",w:"red"},Y:{c:"#e0b52a",w:"yellow"},G:{c:"#2d8a4e",w:"green"}};
/* The heads of a color-light signal as letters, each checked against LAMP; `where` names the call for the error. */
function lampsOf(heads,where){
  if(typeof heads!=="string"||!heads)throw new TypeError(`${where}: the heads must be a string of letters, not ${JSON.stringify(heads)}`);
  return [...heads].map(k=>signalEntry(LAMP,"LAMP",k,`${where}(${JSON.stringify(heads)})`));
}
const lampWords=heads=>lampsOf(heads,"lampWords").map(L=>L.w).join(" over ");
function lightFig(heads,plate){
  const n=heads.length,top=26,gap=40,h=top+(n-1)*gap+44;
  let g="";
  lampsOf(heads,"lightFig").forEach((L,i)=>{const y=top+i*gap;
    g+=`<rect x="14" y="${y-15}" width="30" height="30" rx="15" fill="#1d2733"/><circle cx="29" cy="${y}" r="10" fill="${L.c}"/>`});
  const pl=plate?`<rect x="34" y="${h-34}" width="${plate.length>2?36:26}" height="16" fill="#f5f0e1" stroke="currentColor" stroke-width="1.5"/><text x="${34+(plate.length>2?18:13)}" y="${h-22}" text-anchor="middle" font-size="11" font-weight="700" fill="#1d2733" font-family="system-ui,sans-serif">${plate}</text>`:"";
  return `<svg class="ce-sig" viewBox="0 0 80 ${h}" width="80" height="${h}" role="img" aria-label="Color light signal, ${lampWords(heads)}${plate?", "+plate+" plate":""}"><line x1="29" y1="${top+15}" x2="29" y2="${h-6}" stroke="currentColor" stroke-width="3"/><line x1="18" y1="${h-6}" x2="40" y2="${h-6}" stroke="currentColor" stroke-width="4"/>${g}${pl}</svg>`;
}

/* Standard Code Fixed Signals, Rules 281-292 (§1.0, pages 90-107): the Code's first drawing of each aspect, arms top to
   bottom, with its name and indication in the Code's words. `w` lists the rules whose indications are the wrong choices. */
const ASPECTS=[
  {r:"281",arms:"GRR",name:"Clear",ind:"Proceed",more:1,w:["281A","283","285"]},
  {r:"281A",arms:"GYR",name:"Advance approach medium",ind:"Proceed approaching second signal at medium speed",more:1,w:["282","282A","281B"]},
  {r:"281B",arms:"YGG",name:"Approach limited",ind:"Proceed approaching next signal at limited speed",w:["281C","282","281A"]},
  {r:"281C",arms:"RGG",name:"Limited-clear",ind:"Proceed; limited speed within interlocking limits",w:["281B","283","287"]},
  {r:"282",arms:"YGR",name:"Approach medium",ind:"Proceed approaching next signal at medium speed",more:1,w:["281A","286","285"]},
  {r:"282A",arms:"YYR",name:"Advance approach",ind:"Prepare to stop at second signal",more:1,w:["281A","285","283A"]},
  {r:"283",arms:"RGR",name:"Medium clear",ind:"Proceed; medium speed within interlocking limits",more:1,w:["281C","287","286"]},
  {r:"283A",arms:"RYY",name:"Medium-advance approach",ind:"Proceed preparing to stop at second signal; medium speed within interlocking limits",w:["282A","286","283B"]},
  {r:"283B",arms:"RYG",name:"Medium-approach slow",ind:"Proceed at medium speed approaching next signal at slow speed",w:["284","286","288"]},
  {r:"284",arms:"YRG",name:"Approach slow",ind:"Proceed approaching next signal at slow speed. Train exceeding medium speed must at once reduce to that speed",w:["283B","285","288"]},
  {r:"285",arms:"YRR",name:"Approach",ind:"Proceed preparing to stop at next signal. Train exceeding medium speed must at once reduce to that speed",more:1,w:["286","282A","290"]},
  {r:"286",arms:"RYR",name:"Medium-approach",ind:"Proceed at medium speed preparing to stop at next signal",w:["285","283A","282"]},
  {r:"287",arms:"RRG",name:"Slow-clear",ind:"Proceed; slow speed within interlocking limits",more:1,w:["283","288","281C"]},
  {r:"288",arms:"YR",name:"Slow-approach",ind:"Proceed preparing to stop at next signal; slow speed within interlocking limits",w:["287","285","286"]},
  {r:"289",arms:"Y",name:"Permissive",ind:"Manual block occupied; proceed prepared to stop short of train or obstruction, but not exceeding 15 miles per hour",mark:1,w:["290","291","285"]},
  {r:"290",arms:"RRY",name:"Restricting",ind:"Proceed at restricted speed",more:1,w:["291","289","292"]},
  {r:"291",arms:"RR",name:"Stop and proceed",ind:"Stop; then proceed at restricted speed",more:1,mark:1,note:"Railroads desiring to avoid stopping trains may arrange accordingly.",w:["292","290","289"]},
  {r:"292",arms:"RRR",name:"Stop",ind:"Stop",more:1,w:["291","290","285"]}];

/* The Signals guide's route signal chart (§5, page 5), as the deck's chart card words it. */
const ROUTE=[
  {k:"clear",heads:"G",name:"Clear",ind:"Next two blocks are unoccupied"},
  {k:"approach",heads:"Y",name:"Approach",ind:"Next block is unoccupied"},
  {k:"dclear",heads:"RG",name:"Diverging Clear",ind:"Next two blocks are unoccupied on diverging route"},
  {k:"dapproach",heads:"RY",name:"Diverging Approach",ind:"Next block is unoccupied on diverging route"},
  {k:"stop",heads:"R",name:"Stop",ind:"Stop"},
  {k:"stop2",heads:"RR",name:"Stop",ind:"Stop"}];

/* What a plate on the mast means at a stop indication (Signals guide, §5 page 3), as the deck's plate cards word it. */
/* with: the plate as written in a sentence ("carries an SA plate"); near: plates whose action is too close to count as wrong. */
const PLATES={
  A:{name:"A plate",with:"an A plate",near:["SA"],abs:1,act:"Do not pass until permission is granted by whoever controls the signal",note:"An absolute signal: at stop, it may not be passed until permission is granted by the individual controlling the signal, usually a CTC dispatcher."},
  none:{name:"No plate",with:"no plate",near:["SA"],abs:1,act:"Do not pass until permission is granted by whoever controls the signal",note:"No plate: the same rule as an A plate governs."},
  num:{name:"Number plate",with:"a number plate",act:"Stop, then proceed at restricted speed",note:"Number plate, usually the nearest milepost: after stopping, you may proceed at restricted speed."},
  G:{name:"G plate",with:"a G plate",act:"Pass at restricted speed without stopping",note:"Grade signal, also with a number plate: it can be passed at restricted speed without stopping, which helps prevent a train from stalling on an upgrade."},
  SA:{name:"SA plate",with:"an SA plate",near:["A","none"],abs:1,act:"Get permission to proceed from the interlocking operator",note:"Semi-automatic, usually in interlockings: an absolute and an ABS part. At stop, permission to proceed must be obtained from the interlocking operator."},
  P:{name:"P plate",with:"a P plate",act:"Inspect the protective device in the block",note:"Protective signal: there is a protective device in the block, such as a high water or slide detector, that must be inspected by the train crew."}};

/* The wrong choices for a plate question: every other plate's action, leaving out its own and any `near` one too close
   to call wrong. At an absolute plate (abs), a choice that passes the signal without permission ends the run. */
function plateWrongs(key){
  const where=`plateWrongs(${JSON.stringify(key)})`;
  const P=signalEntry(PLATES,"PLATES",key,where);
  const close=new Set([P.act,...(P.near||[]).map(k=>signalEntry(PLATES,"PLATES",k,`${where}, its near list`).act)]);
  return [...new Set(Object.values(PLATES).map(x=>x.act))].filter(t=>!close.has(t))
    .map(t=>({t,ends:!!P.abs&&/without stopping|Stop, then proceed/.test(t)}));
}
/* The explanation after a route signal question, the same in the game and the answer key. */
const routeWhy=r=>`${r.name}: ${r.ind}.${r.heads.length>1&&r.k!=="stop2"?" It's not red unless it's all red.":""}`;

/* Choose a block-signal story for each leg of a signals run. fixed[i] is the story a set piece already puts on leg i,
   or null for an ordinary leg; allowed(i) lists the stories leg i may draw. An ordinary leg never repeats the story of
   the leg before it or of a fixed leg after it, a story in `once` is used on one leg at most, and the draw is uniform
   over what is left. rand() returns a number in [0,1). clash(a,b) says whether two stories count as the same; by
   default only equal keys do. */
function pickStories(fixed,allowed,once,rand,clash=(a,b)=>a===b){
  const out=fixed.slice(),used=new Set();
  for(let i=0;i<out.length;i++){
    if(out[i]!==null)continue;
    const all=allowed(i),ok=all.filter(k=>!(i>0&&clash(k,out[i-1]))&&!(fixed[i+1]!=null&&clash(k,fixed[i+1]))&&!(once.includes(k)&&used.has(k)));
    const pool=ok.length?ok:all.filter(k=>!(once.includes(k)&&used.has(k)));
    out[i]=pool[Math.floor(rand()*pool.length)];
    if(once.includes(out[i]))used.add(out[i]);
  }
  return out;
}

if(typeof module!=="undefined"&&module.exports)
  module.exports={ASPECTS,ROUTE,PLATES,sigFig,lightFig,armWords,lampWords,plateWrongs,routeWhy,pickStories,UnknownSignalKey};
