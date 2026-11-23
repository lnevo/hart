/* The shared engine of the road runs of Extra East: HART Railroad, "Up the Chartiers". It holds what every 1949 run on the
   Chartiers Branch shares: the line, the one fixed time-table, the meet check, the line map and the time-table sheet, the
   order paper and the questions that come with it. The runs themselves (road.js for the coal extra, passenger.js for
   No 307) load after it and register in window.NevilleRuns. The line comes from library/chartiers-valley-railroads.html
   and the sources it lists; the time-table, the other trains, the orders and the offices are the game's own. Every
   question is a rule from the C&E study deck (exam/deck-data.js), in the deck's words. Question wording that comes
   from the Standard Code speed signals uses exam/signals.js, which loads first. A second line (pcy.js, the PC&Y run) shares
   only the parts that are not the Chartiers Branch's own: the helpers, the draw and the signal toolkit at the end.
 */
(function(){
"use strict";
const LIB="../library/chartiers-valley-railroads.html";
const WIKI="https://en.wikipedia.org/wiki/Chartiers_Branch";
const lib=t=>`<a href="${LIB}">${t}</a>`;
const fmt=m=>{m=Math.round(m);m=((m%1440)+1440)%1440;return Math.floor(m/60)+":"+String(m%60).padStart(2,"0")};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* ---------- the line ---------- */
/* Carnegie (Mansfield) to Washington. mp: milepost from Carnegie. sd: siding. off: train order office. il: interlocking.
   Double track Carnegie to Houston (HOU), single track beyond. The stations and the mileposts of Bridgeville, Hills,
   Houston and Washington are the sources'; the other mileposts are placed between them. Tylerdale is 1.8 miles from
   Washington (the library page); the Tylerdale Connecting to the B&O joins the main there. */
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
  {n:"Tylerdale",mp:21.8,sd:0,il:1},
  {n:"Washington",mp:23.6,sd:1,off:1,yl:1}];
const LAST=ST.length-1,HOU=10,ARD=11,TYL=12,BV=5,HIL=8;

/* ---------- the time-table ---------- */
/* One table for every 1949 run, the same on every play, like an employee time-table: the draws change the orders, the late
   trains and the events, never these times. Minutes after midnight, one per station of ST, in station order. A time
   is the leaving time (Rule 5), except the arriving time at Washington southbound and at Carnegie northbound.
   Passenger trains run 2.2 minutes a mile, No 92 3.2, anchored at Houston. */
const TT=[
  {id:"305",name:"No 305",dir:1,cls:"First class",t:[444,446,449,451,452,453,457,460,463,470,478,488,492,496]},
  {id:"307",name:"No 307",dir:1,cls:"First class",t:[546,548,551,553,554,555,559,562,565,572,580,590,594,598]},
  {id:"309",name:"No 309",dir:1,cls:"First class",t:[586,588,591,593,594,595,599,602,605,612,620,630,634,638]},
  {id:"302",name:"No 302",dir:-1,cls:"First class",t:[560,558,555,553,552,551,547,544,541,534,526,516,512,508]},
  {id:"92",name:"No 92",dir:-1,cls:"Second class",t:[603,600,597,594,592,590,585,581,575,565,554,539,533,527]},
  {id:"304",name:"No 304",dir:-1,cls:"First class",t:[675,673,670,668,667,666,662,659,656,649,641,631,627,623]}];
/* An extra's own running time between each pair of stations, minutes: 3.5 a mile. */
const LEG=[3,4,3,2,2,6,5,6,11,12,16,6,7];
/* A fresh copy for one play: act is where each train actually is (a late order moves it), t stays as printed. */
function newTT(){return {trains:TT.map(x=>({id:x.id,name:x.name,dir:x.dir,cls:x.cls,t:x.t.slice(),act:x.t.slice(),marked:false})),leg:LEG.slice()}}
const train=(G,id)=>G.tt.trains.find(t=>t.id===id);
const run=(G,a,b)=>{let m=0;for(let i=Math.min(a,b);i<Math.max(a,b);i++)m+=G.tt.leg[i];return m}; // the extra's running time

/* ---------- the meet check ---------- */
/* An extra moves from k to j, leaving at c and arriving at a. Returns the problems with the regular trains, worst first. */
function checkMove(G,k,j,c,a){
  const d=j>k?1:-1,probs=[];
  for(const tr of G.tt.trains){
    if(tr.dir===-d){ // opposing
      if(Math.max(k,j)<=HOU)continue; // all on double track: opposing trains use the other main (Rule D-71)
      const ent=d===1?Math.max(k,HOU):k,ext=d===1?j:Math.max(j,HOU); // the single-track part: where we enter and leave it
      const tEnt=c+run(G,k,ent),tExt=c+run(G,k,ext);
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

/* ---------- drawings ---------- */
/* Semaphore, blade at a degrees (0 is horizontal, upper quadrant). */
function semSvg(a){
  return `<svg viewBox="0 0 120 120" width="110" height="110" aria-label="Semaphore, blade at ${a} degrees" role="img" style="align-self:flex-start"><rect x="57" y="20" width="6" height="96" fill="#1d2733"/><circle cx="60" cy="16" r="5" fill="#1d2733"/><g transform="rotate(${-a} 60 40)"><rect x="60" y="34" width="52" height="11" fill="#a3302b" stroke="#1d2733" stroke-width="1.5"/><rect x="100" y="34" width="4" height="11" fill="#fff"/></g><circle cx="52" cy="40" r="6" fill="#f3ecbf" stroke="#1d2733" stroke-width="1.5"/></svg>`;
}

/* The line sketch: Carnegie to Washington, the branches and junctions at 45 degrees, the player's engine lit at its station.
   o.label is the number on the engine. The run's where(S) names the place in the picture's label. */
function map(S,o){
  const G=S.road,W=600,xs=ST.map((s,i)=>26+i*42),y=72,y2=79;
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
  s+=`<path d="M${xs[BV]+20} ${y2} L${xs[BV]+28} ${y2+8} H${xs[BV]+36}"/>`; // P&WV, about a mile west of Bridgeville, the Washington side, off the second main
  s+=`<path d="M${xs[ARD]} ${y} L${xs[ARD]+12} ${y-12} H${xs[ARD]+24}"/>`; // Manifold, leaving at Arden
  s+=`<path d="M${xs[HOU]+8} ${y} L${xs[HOU]+20} ${y+12} H${xs[HOU]+34}"/>`; // Westland
  s+=`<path d="M${xs[TYL]+4} ${y} L${xs[TYL]+14} ${y+10} H${xs[TYL]+24}"/>`; // Tylerdale Connecting to the B&O
  s+=`</g>`;
  // stations
  ST.forEach((st,i)=>{const x=xs[i];s+=`<line x1="${x}" y1="${y+9}" x2="${x}" y2="${y+13}" stroke="var(--ink)" stroke-width="1.2"/>`;
    s+=`<text x="${x}" y="${i%2?112:101}" font-size="6.3" text-anchor="middle" class="lbl" font-weight="${i===at&&!G.moving?700:400}">${esc(st.n.toUpperCase())}</text>`;
    if(st.il)s+=`<rect x="${x-3}" y="${y-5}" width="6" height="6" fill="var(--rust)" opacity=".85"/>`});
  lab.forEach(([x,yy,t])=>{s+=`<text x="${x}" y="${yy}" font-size="5.8" class="lbl">${t}</text>`});
  s+=`<text x="${xs[ARD]+16}" y="${y-16}" font-size="5.8" class="lbl">MANIFOLD</text><text x="${xs[BV]+38}" y="${y2+11}" font-size="5.8" class="lbl">P&amp;WV</text><text x="${xs[HOU]+24}" y="${y+25}" font-size="5.8" class="lbl">WESTLAND</text><text x="${xs[TYL]+26}" y="${y+13}" font-size="5.8" class="lbl">B&amp;O</text>`;
  // the engine, the job's own lit; between two stations it stands midway
  const ex=G.moving&&G.to!==undefined?(xs[at]+xs[G.to])/2:me;
  s+=`<g transform="translate(${ex} ${y-1})"><rect x="-13" y="-5" width="26" height="10" rx="2" fill="var(--green)" stroke="var(--glow)" stroke-width="1.4"/><text x="0" y="2.4" font-size="6.4" text-anchor="middle" fill="#fff" font-weight="700">${esc(o.label)}</text></g>`;
  return s+`</svg>`;
}

/* ---------- the time-table sheet ---------- */
/* The six regular trains, south then north, with the player's own column marked. o.mine: the id of the player's train, or
   none for an extra, whose own running minutes print in the last column (o.runLabel). A train a late order has moved
   shows its old time struck and the new one beside it. */
function sheet(S,o){
  const G=S.road;if(!G)return "";
  const tr=G.tt.trains,short={"First class":"1st","Second class":"2nd"};
  const ar=(t,i)=>(t.dir===1&&i===LAST)||(t.dir===-1&&i===0)?" ar":"";
  let h=`<h3>Chartiers Branch</h3><div class="sub">Time-table · double track Carnegie to Houston, single track beyond · D = open office</div><div class="xw-tt" tabindex="0"><table><thead><tr><th>Station</th>`;
  tr.forEach(t=>h+=`<th${t.id===o.mine?' class="mine"':""}>${esc(t.name)}<small>${t.dir===1?"South":"North"} · ${esc(short[t.cls]||t.cls)}</small></th>`);
  if(o.runLabel)h+=`<th>${esc(o.runLabel)}<small>run min</small></th>`;
  h+=`</tr></thead><tbody>`;
  ST.forEach((st,i)=>{
    h+=`<tr class="${i===G.pos&&!G.moving?"here":""}"><td class="stn">${esc(st.n)}<small>MP ${st.mp.toFixed(1)}${st.off?" · D":""}${st.sd?"":" · no siding"}${st.il?" · interlocking":""}</small></td>`;
    tr.forEach(t=>{
      const m=t.id===o.mine?' mine':"";
      h+=t.marked&&t.act[i]!==t.t[i]?`<td class="late${m}"><s>${fmt(t.t[i])}</s><b>${fmt(t.act[i])}${ar(t,i)}</b></td>`:`<td${m?` class="mine"`:""}>${fmt(t.t[i])}${ar(t,i)}</td>`});
    if(o.runLabel)h+=`<td class="pencil">${i<LAST?G.tt.leg[i]:""}</td>`;
    h+=`</tr>`;
  });
  h+=`</tbody></table></div><div class="xw-si"><b>Special instructions</b><ul><li>Northward trains are superior to southward trains of the same class.</li><li>One time shown is the leaving time (Rule 5).</li><li>Carnegie and Washington are inside yard limits.</li><li>Extras clear opposing regular trains by 5 minutes (Rule S-87).</li><li>Double track Carnegie to Houston: D- rules apply there.</li><li>Interlockings at Bridgeville, Hills and Tylerdale.</li></ul></div>`;
  if(G.orders.length)h+=`<div class="xw-orders"><b>Orders held</b>${G.orders.map(x=>`<div class="ord">No ${x.no}: ${esc(x.text)}<span class="ok">${x.wire?"wire failed":"OK"}</span></div>`).join("")}</div>`;
  h+=`<div class="xw-orders"><b>Work</b>${S.jobs.map(j=>`<div class="ord${j.done?" done":""}">${j.done?"✓ ":""}${esc(j.t)}</div>`).join("")}</div>`;
  return h;
}

/* ---------- train orders ---------- */
/* The order numbers the clearance shows: the right ones, or with the last one wrong. */
const clearNums=(nums,wrong)=>wrong?nums.map((x,i)=>i===nums.length-1?x+3:x):nums;
/* The orders and the Clearance Form A the operator hands up. o: place, train, orders [{no,text}], shown (the numbers on the
   clearance), at (clock when the dispatcher gave the OK, or a function that gives it), wire (the wire failed before the OK), note (a line added after the greeting). */
function paper(H,o){return ()=>{ // built when the scene runs, so the OK time is the clock then
  const at=typeof o.at==="function"?o.at():o.at;
  const clearTxt=`CLEARANCE FORM A\nTo ${o.train}  at ${o.place.toUpperCase()}\nI have ${o.shown.length} order${o.shown.length>1?"s":""} for your train.\nNos ${o.shown.join(", ")}\n${o.wire?"Wire has failed":`OK  ${fmt(at)}  RK, dispatcher`}`;
  const ordTxt=o.orders.map(x=>`<span class="no">Order No ${x.no}</span>\n${esc(x.text)}`).join("\n\n");
  return H.info(o.place,"Orders","<p>The operator hands up the orders and the clearance."+(o.note||"")+"</p><div class='xw-tele'>"+ordTxt+"</div><div class='xw-clear'>"+esc(clearTxt)+"</div>","Check them")();
}}
/* The crew takes the orders: they go on the sheet, and a clearance fixed with the dispatcher costs 6 minutes. */
function take(H,G,orders,fixed,wire){return ()=>{orders.forEach(x=>G.orders.push(wire?Object.assign({wire:true},x):x));if(fixed)H.addTime(6);H.log("Orders "+orders.map(x=>x.no).join(", ")+" received");H.next()}}

/* ---------- questions the engine's own checks and papers raise ---------- */
const Q={
  margin:(name,where,mins)=>({miss:true,sec:"sup",src:"SC · Rule S-87",title:"Too close to "+name,body:`You got into the siding at ${where} only ${mins} minutes ahead of ${name}'s time there. By how much must an extra clear the time of an opposing regular train?`,right:"Not less than 5 minutes",wrong:[["Any margin, as long as it is in the clear"],["Not less than 2 minutes"],["Only to the leaving time"]],ok:{marks:1},okText:"Right, and you did not.",why:"Rule S-87: extras must clear the time of opposing regular trains by not less than 5 minutes unless otherwise provided. The TT&TO primer quotes 10 minutes."}),
  r86:(name,where)=>({miss:true,sec:"sup",src:"SC · Rule 86",title:name+" was close behind",body:`${name} was due to leave the station behind you before you were in the clear at ${where}. When must an inferior train running ahead of a superior train be clear?`,right:"When the superior train is due to leave the next station in the rear where time is shown",wrong:[["5 minutes before the superior train is due at the station ahead"],["When the superior train comes in sight"],["At the superior train's arriving time at the station ahead"]],ok:{marks:1},okText:"Right, and you were not.",why:"Rule 86: unless otherwise provided, the inferior train must be clear at the time the superior train is due to leave the next station in the rear where time is shown."}),
  fix:(shown,nums)=>({sec:"to",src:"SC · Rule 211",title:"Check the clearance",body:`The clearance lists Nos ${shown}, but you hold Nos ${nums}. What do you do?`,right:"Do not leave; have the operator correct it with the dispatcher",wrong:[["Leave; the orders in hand are what count"],["Cross out the number and write the right one in"],["Leave and report it from the next office"]],why:"Rule 211: Clearance Form A is filled out without erasure or alteration, and conductors, enginemen and firemen must see that its information matches the orders received."}),
  who:(shown,nums)=>({sec:"to",src:"SC · Rule 211",title:"Check the clearance",body:`The clearance lists Nos ${shown} and you hold Nos ${nums}. Who on your crew must check that they match?`,right:"The conductor, the engineman and the fireman",wrong:[["Only the conductor"],["Only the engineman"],["The operator alone"]],why:"Rule 211: conductors, enginemen and firemen, and trainmen when practicable, must see that the information on Clearance Form A matches the train orders received."}),
  wire:()=>({sec:"to",src:"SC · Rule 211",title:"The wire has failed",body:"The operator has all your orders, but the wire fails before the OK. He marks the clearance “Wire has failed.” May you go?",right:"Yes: it is acted on as though OK had been given",wrong:[["No; wait until the wire is restored"],["No; the orders are void and must be sent again"],["Only on the operator's verbal OK"]],why:"Rule 211: if all orders for the train are complete, the operator may deliver them with Clearance Form A marked “Wire has failed”. It is acted on as though OK had been given. When the wire is restored he reports each train cleared, the time and the order numbers."})
};
/* A question about a Standard Code speed signal (Rules 281-292, exam/signals.js): the picture, the aspect's indication, and
   the indications of the Code's other aspects as the wrong choices. o: rule, where (the place), body, cost of a wrong answer. */
function aspectQ(o){
  const A=ASPECTS.find(a=>a.r===o.rule),by=r=>ASPECTS.find(a=>a.r===r);
  return {sec:"sig",src:"SC · Rule "+A.r,where:o.where,title:o.title,body:o.body+" What does it indicate? Arms top to bottom: "+armWords(A.arms)+".",extra:`<div class="xw-fig">${sigFig(A.arms)}</div>`,right:A.ind,
    wrong:A.w.map(r=>[by(r).ind]),why:`Rule ${A.r}, ${A.name}: ${A.ind}.`};
}

/* ---------- the signal toolkit: shared by any run that has signals instead of a time-table ---------- */
/* What to do at a signal showing Stop, by its plate (Signals guide, exam/signals.js PLATES). Passing an absolute signal
   without permission ends the run. Each plate has exactly three wrong choices, so the answer key lists them all. */
function plateQ(key,where,place){
  const P=PLATES[key];
  return {sec:"sig",src:"SG · Signal signage",where,title:P.name+" at "+place,body:`The signal shows Stop and carries ${P.with}. What do you do?`,
    extra:`<div class="xw-fig">${sigFig("RRR",key==="none"?"":key)}</div>`,right:P.act,
    wrong:plateWrongs(key).map(w=>w.ends?[w.t,{end:true,endText:"You passed a signal at Stop without permission."}]:[w.t]),why:P.note};
}
/* The Standard Code pairs a home signal that is cleared with the approach signal before it by the speed of the route:
   the aspect of the approach signal, then the home signal's own. A home signal at Stop is preceded by Approach (285). */
const PAIR={limited:{app:"281B",home:"281C"},medium:{app:"282",home:"283"},slow:{app:"284",home:"287"}};
const SPEEDS=Object.keys(PAIR);

/* A signal on the map: dots stacked up from the rail or down from it, the aspect's colours once the player has met it,
   a ring while it has not been read. "D" is a distant signal, shown as a ring with no colour. */
function sigDots(g,s){
  const arms=g.sig[s.k],n=arms&&arms!=="D"?arms.length:1,dy=s.up?-1:1,y0=s.y+dy*5;
  let o=`<line x1="${s.x}" y1="${s.y}" x2="${s.x}" y2="${s.y+dy*(5+n*5)}" stroke="var(--ink)" stroke-width="1"/>`;
  for(let i=0;i<n;i++){
    const cy=s.y+dy*(8+i*5),k=arms&&arms!=="D"?arms[i]:null;
    o+=`<circle cx="${s.x}" cy="${cy}" r="2.2" fill="${k?ARM[k].c:"var(--sheet-2)"}" stroke="var(--ink)" stroke-width=".8"/>`;
  }
  return o;
}

/* ---------- a draw from a pool, each question once per run ---------- */
function draw(G,R,H,key,pool,p){
  if(R()>p)return null;
  let b=G.bag[key];if(!b||!b.length)b=G.bag[key]=H.shuffle(pool.map((_,i)=>i),R);
  return H.ask(pool[b.pop()]);
}

window.RoadEngine={ST,LAST,HOU,ARD,TYL,BV,HIL,LIB,WIKI,lib,fmt,esc,TT,newTT,train,run,checkMove,semSvg,map,sheet,clearNums,paper,take,Q,aspectQ,plateQ,PAIR,SPEEDS,sigDots,draw};
})();
