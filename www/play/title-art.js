(function(){
"use strict";
/* The Extra East: HART Railroad title screen: the coke works at dusk, in pixel art. Drawn into
   #xwTitleCv on the game page (play/index.html) and in the game band on the home page (index.html).
   It stands still when the reader asks for reduced motion or the canvas has data-still (the home page),
   and pauses while scrolled out of view. */
const $=id=>document.getElementById(id);
const reduced=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches;

function title(){
  const cv=$("xwTitleCv");if(!cv)return;
  let g=cv.getContext("2d");const W=cv.width,H=cv.height;
  const C={sky:["#1b1830","#2c2142","#4a2a48","#7a3a3f","#b5573a","#e08a3c"],river:"#22263a",riverHi:"#e08a3c",riverHi2:"#8a4a3a",
    plant:"#141319",plant2:"#1f1d26",glow:"#ffb347",glow2:"#ff7a2a",ink:"#0e0d12",rail:"#3a3640",ground:"#262229",
    green:"#2f6b3f",green2:"#3f8a52",cream:"#efe6cf",smoke:"150,130,130",hopper:"#4a3b33",ore:"#7a3b2a"};
  const FONT={A:"01110100011000111111100011000110001",B:"11110100011000111110100011000111110",C:"01111100001000010000100001000001111",
    D:"11110100011000110001100011000111110",E:"11111100001000011110100001000011111",F:"11111100001000011110100001000010000",
    G:"01111100001000010111100011000101111",H:"10001100011000111111100011000110001",I:"11111001000010000100001000010011111",
    K:"10001100101010011000101001001010001",L:"10000100001000010000100001000011111",N:"10001110011010110011100011000110001",
    O:"01110100011000110001100011000101110",P:"11110100011000111110100001000010000",R:"11110100011000111110101001001010001",
    S:"01111100001000001110000010000111110",T:"11111001000010000100001000010000100",U:"10001100011000110001100011000101110",
    V:"10001100011000110001100010101000100",W:"10001100011000110101101011010101010",X:"10001100010101000100010101000110001",
    Y:"10001100010101000100001000010000100","&":"01100100101010001000101011001001100",
    "0":"01110100011001110101110011000101110","1":"00100011000010000100001000010001110","2":"01110100010000100010001000100011111",
    "4":"00010001100101010010111110001000010","5":"11111100001111000001000011000101110","7":"11111000010001000100010000100001000",
    "8":"01110100011000101110100011000101110","9":"01110100011000101111000010001001100","-":"00000000000000011111000000000000000",
    "·":"00000000000000000100000000000000000"," ":"00000000000000000000000000000000000"};
  function text(str,x,y,sc,col,shadow){
    const w=str.length*6*sc-sc;if(x==="c")x=Math.round((W-w)/2);
    for(const pass of shadow?[[shadow,1],[col,0]]:[[col,0]]){
      g.fillStyle=pass[0];[...str].forEach((ch,i)=>{const f=FONT[ch]||FONT[" "];for(let r=0;r<7;r++)for(let c=0;c<5;c++)if(f[r*5+c]==="1")g.fillRect(x+pass[1]+(i*6+c)*sc,y+pass[1]+r*sc,sc,sc)});
    }
  }
  const bg=document.createElement("canvas");bg.width=W;bg.height=H;const b=bg.getContext("2d");
  // dusk sky in dithered bands, darkest at the top
  const bands=[0,20,34,46,56,64];
  C.sky.forEach((c,i)=>{b.fillStyle=c;b.fillRect(0,bands[i],W,(bands[i+1]||72)-bands[i])});
  bands.slice(1).forEach((y,i)=>{b.fillStyle=C.sky[i];for(let x=0;x<W;x+=2)b.fillRect(x+((x/2)%2),y,1,1)});
  b.fillStyle="#f4d9a0";for(let i=0;i<14;i++)b.fillRect((i*53+17)%W,(i*29+3)%18,1,1); // first stars
  // the far shore: Pittsburgh hills, upstream on the right
  b.fillStyle="#3a2738";for(let x=0;x<W;x++){const h=Math.round(6+4*Math.sin(x*.05)+3*Math.sin(x*.13+1));b.fillRect(x,66-h,1,h+6)}
  // the plant: coke battery with its ovens, the quench tower, B furnace and its stoves, stacks
  const P=(c,x,y,w,h)=>{b.fillStyle=c;b.fillRect(x,y,w,h)};
  P(C.plant,8,58,90,14);P(C.plant2,10,54,86,4); // coke battery
  for(let x=12;x<94;x+=4){P(C.glow2,x,61,2,3)} // oven doors glowing
  P(C.plant,22,30,3,24);P(C.plant,40,26,3,28);P(C.plant,58,32,3,22); // battery stacks
  P(C.plant,100,40,12,32);P(C.plant2,102,36,8,4); // quench tower
  P(C.plant,150,22,10,50);P(C.plant,147,34,16,4);P(C.plant,152,14,6,8); // B furnace
  for(const x of [166,176,186])P(C.plant,x,36,8,36); // hot-blast stoves
  P(C.plant,200,44,30,28);P(C.plant2,205,40,6,4); // cast house
  P(C.plant,236,28,4,44);P(C.plant,244,34,3,38); // far stacks
  P(C.glow,150,60,10,3); // the cast, lit from inside
  // the river and its reflections
  P(C.river,0,72,W,12);
  for(let x=0;x<W;x+=3){const y=74+(x*7%9);b.fillStyle=(x>140&&x<170)||(x>8&&x<98&&x%6===0)?C.riverHi:C.riverHi2;b.fillRect(x,y,2,1)}
  // ground and the track along the bank
  P(C.ground,0,84,W,H-84);P(C.rail,0,101,W,1);
  b.fillStyle="#3c3640";for(let x=0;x<W;x+=4)b.fillRect(x,103,2,1);
  // a pole line
  b.fillStyle="#3a3438";for(let x=14;x<W;x+=56){b.fillRect(x,84,1,17);b.fillRect(x-3,85,7,1)}
  // the lettering sits on its own layer, drawn over the smoke
  const fg=document.createElement("canvas");fg.width=W;fg.height=H;
  {const keep=g;g=fg.getContext("2d");
    text("NEVILLE ISLAND · UP THE CHARTIERS","c",4,1,"#f4d9a0","#1b1830");
    text("EXTRA EAST","c",14,3,C.cream,"#7a2a24");
    text("HART RAILROAD","c",39,1,C.glow,"#1b1830");
    g=keep}
  // smoke and steam, drawn each frame
  function smoke(t){
    const puffs=[[23,30],[41,26],[59,32],[106,36],[155,14],[237,28]];
    puffs.forEach(([x,y],k)=>{for(let i=0;i<5;i++){const p=((t/180)+i*2.2+k*1.3)%11;const a=(1-p/11)*.55;
      g.fillStyle=k===3?`rgba(230,225,230,${a})`:`rgba(${C.smoke},${a})`;g.fillRect(Math.round(x-p*2.6),Math.round(y-2-p*1.6),2+(p>>2),2+(p>>2))}});
  }
  // the ore drag: SW9 #4 shoving ten hoppers is too long for the frame, so four hoppers and the engine
  function train(x,f){
    const Rr=(c,a,y,w,h)=>{g.fillStyle=c;g.fillRect(Math.round(x+a),y,w,h)};
    // SW9 on the west end, long hood leading west, cab coupled to the drag: it shoves east (right)
    Rr(C.green,0,90,24,10);Rr(C.green2,0,90,24,1);Rr(C.green,24,86,8,14);Rr(C.cream,26,88,4,3);Rr(C.ink,24,85,8,1);
    Rr(C.glow,-2,92,2,2); // headlight on the long hood end
    Rr(C.ink,3,100,4,2);Rr(C.ink,21,100,4,2);
    Rr(C.cream,8,93,1,3);Rr(C.cream,10,93,3,1);Rr(C.cream,10,95,3,1); // a 4 on the hood
    for(let k=0;k<4;k++){const o=34+k*18;Rr(C.hopper,o,92,16,8);Rr(C.ore,o+1,90,14,2);Rr(C.ink,o+2,100,3,2);Rr(C.ink,o+11,100,3,2)}
    for(let i=0;i<3;i++){const p=(f+i*3)%9;g.fillStyle=`rgba(60,55,60,${(1-p/9)*.6})`;g.fillRect(Math.round(x+12-p*1.5),88-p*2,2,2)}
  }
  function draw(t){
    g.drawImage(bg,0,0);smoke(t);g.drawImage(fg,0,0);
    const span=W+120,x=still?96:((t/45)%span)-110;
    train(x,Math.floor(t/140));
    // the cast flickers
    g.fillStyle=`rgba(255,179,71,${.35+.25*Math.sin(t/220)})`;g.fillRect(146,58,18,6);
  }
  const still=reduced||cv.hasAttribute("data-still"); // the home page shows one frame
  if(still||typeof IntersectionObserver!=="function"){draw(0);return}
  let raf=0;const loop=t=>{draw(t);raf=requestAnimationFrame(loop)};
  const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting&&!raf)raf=requestAnimationFrame(loop);else if(!e.isIntersecting&&raf){cancelAnimationFrame(raf);raf=0}})});
  io.observe(cv);draw(0);
}

title();
})();
