/* Extra East: the title screen's pixel art, a train crossing the start screen's canvas (#xwTitleCv). It stands
   alone: it reads nothing from run.js and shares nothing. Still under reduced motion; it animates only while on screen. */
(function(){
"use strict";
const $=id=>document.getElementById(id);
const reduced=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches;
(function title(){
  const cv=$("xwTitleCv");if(!cv)return;
  let g=cv.getContext("2d");const W=cv.width,H=cv.height;
  const SKY1="#e9dcb4",SKY2="#efe6c8",SKY3="#f5f0e1",SUN="#ead39a",GOLD="#ead39a",CREAM="#f5f0e1",RED="#a3302b",
    HILL1="#d6c79f",HILL2="#c3b287",GROUND="#a99a72",RAIL="#1d2733",INK="#1d2733",POLE="#5d5a4e",MUTED="#5d5a4e";
  const FONT={A:"01110100011000111111100011000110001",D:"11110100011000110001100011000111110",
    E:"11111100001000011110100001000011111",H:"10001100011000111111100011000110001",
    I:"11111001000010000100001000010011111",K:"10001100101010011000101001001010001",
      L:"10000100001000010000100001000011111",N:"10001110011010110011100011000110001",
    O:"01110100011000110001100011000101110",P:"11110100011000111110100001000010000",
      R:"11110100011000111110101001001010001",S:"01111100001000001110000010000111110",
    T:"11111001000010000100001000010000100",V:"10001100011000110001100010101000100",
      W:"10001100011000110101101011010101010",X:"10001100010101000100010101000110001",
    Y:"10001100010101000100001000010000100",C:"01111100001000010000100001000001111",
      U:"10001100011000110001100011000101110",
    B:"11110100011000111110100011000111110",M:"10001110111010110101100011000110001",
      "4":"00010001100101010010111110001000010","6":"01110100001000011110100011000101110",
    "·":"00000000000000000100000000000000000"," ":"00000000000000000000000000000000000"};
  function text(str,x,y,sc,col,shadow){
    const w=str.length*6*sc-sc;if(x==="c")x=Math.round((W-w)/2);
    for(const pass of shadow?[[shadow,1],[col,0]]:[[col,0]]){
      g.fillStyle=pass[0];
        [...str].forEach((ch,i)=>{const f=FONT[ch]||FONT[" "];
        for(let r=0;r<7;r++)for(let c=0;c<5;c++)if(f[r*5+c]==="1")g.fillRect(x+pass[1]+(i*6+c)*sc,y+pass[1]+r*sc,sc,
        sc)});
    }
  }
  // the still part of the picture, drawn once
  const bg=document.createElement("canvas");bg.width=W;bg.height=H;const b=bg.getContext("2d");
  [[0,SKY1],[30,SKY2],[52,SKY3]].forEach(([y,c],i,arr)=>{b.fillStyle=c;b.fillRect(0,y,W,(arr[i+1]?arr[i+1][0]:H)-y)});
  b.fillStyle=SKY2;for(let x=0;x<W;x+=2)b.fillRect(x+(x/2%2),29,1,1); // dithered band edges
  b.fillStyle=SKY3;for(let x=0;x<W;x+=2)b.fillRect(x+(x/2%2),51,1,1);
  b.fillStyle=SUN;
    for(let dy=-8;dy<=8;dy++){const w=Math.round(Math.sqrt(64-dy*dy));
    b.fillRect(212-w,68+dy,w*2+1,1)} // rising sun (east is on the right)
  function ridge(base,amp,step,col,seed){b.fillStyle=col;let h=0;
    for(let x=0;x<W;x++){if(x%step===0)h=Math.round(amp*(.5+.5*Math.sin(x*.045+seed)+.35*Math.sin(x*.13+seed*2)));
    b.fillRect(x,base-h,1,H)}}
  ridge(84,22,4,HILL1,1.3);ridge(92,14,3,HILL2,4.1);
  b.fillStyle=GROUND;b.fillRect(0,104,W,H-104);
  b.fillStyle=RAIL;b.fillRect(0,103,W,1);b.fillStyle="#8c7e58";for(let x=0;x<W;x+=4)b.fillRect(x,105,2,1);
  b.fillStyle=POLE;for(let x=10;x<W;x+=48){b.fillRect(x,82,1,21);b.fillRect(x-3,83,7,1)} // telegraph poles
  for(let x=10;x<W-48;x+=48)for(let i=0;i<48;i++)b.fillRect(x+i,84+Math.round(2*Math.sin(Math.PI*i/48)),1,1);
  { const keep=g;g=b; // the lettering never changes, so it goes on the still picture once
    text("KESTREL VALLEY RAILROAD","c",7,1,INK);text("EXTRA EAST","c",19,3,INK,RED);
      text("ASHBY TO IRONTON · 46 MILES","c",45,1,MUTED);g=keep }
  // the train, 92 px long, facing east (right)
  function train(x,f){
    const px=(c,a,y,w,h)=>{g.fillStyle=c;g.fillRect(Math.round(x+a),y,w,h)};
    // caboose
    px(RED,0,92,14,9);px(RED,4,88,6,4);px(INK,3,87,8,1);px(CREAM,2,94,3,2);px(CREAM,9,94,3,2);
    // boxcar
    px("#6b4a33",16,90,20,11);px("#5a3d29",23,91,6,9);
    // gondola with coal
    px("#3d4652",38,95,18,6);px(INK,39,93,16,2);
    // tender
    px(INK,58,92,14,9);px("#2a2f36",59,90,12,2);
    // engine 812: cab, boiler, stack, dome, headlight, pilot
    px(INK,73,86,9,15);px(SUN,75,88,4,4);px(INK,82,92,18,7);px(INK,95,85,3,7);px(INK,94,84,5,1);px(INK,88,90,3,2);
      px(SUN,100,92,2,2);px(INK,99,99,4,2);
    // wheels and rods, turning
    for(const a of [3,10,18,26,32,44,52,60,69])px(INK,a,101,3,2);
    for(const a of [84,89,94])px(INK,a,99,4,4);
    px(RED,84,100+(f%2),14,1);
    // smoke
    for(let i=0;i<4;i++){const p=(f+i*3)%12;g.fillStyle=`rgba(150,140,115,${(1-p/12)*.75})`;
      g.fillRect(Math.round(x+96-p*2.2),82-p*2,2+(p>>2),2+(p>>2))}
  }
  function draw(t){
    g.drawImage(bg,0,0);
    const span=W+110,x=still?120:((t/40)%span)-100;
    train(x,Math.floor(t/120));
  }
  const still=reduced;
  if(still){draw(0);return}
  let raf=0;const loop=t=>{draw(t);raf=requestAnimationFrame(loop)};
  // run only while the title is on screen
  const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting&&!raf)raf=requestAnimationFrame(loop);
    else if(!e.isIntersecting&&raf){cancelAnimationFrame(raf);raf=0}})});
  io.observe(cv);draw(0);
})();
})();
