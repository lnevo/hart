"""Crop picker for the intake review page: drag and zoom a photo to set its card image.

    cars.py crop BATCH                 Add the picker to an existing batch's review page
    cars.py crop BATCH PHOTO X,Y,W,H[,ANGLE]   Re-cut one photo's card image to that box

The page's *Adjust crop* button shows the photo in a frame the shape of the card image, so
what you see is what the card shows. Drag to move, scroll or use the slider to zoom, and
turn the angle slider to straighten. *Use this crop* keeps the box in the page's ``crop``
column (it travels with *Download review.csv* and ``sheet-import``); *Copy command* gives the
``cars.py crop`` line for one photo.

Box numbers are pixels on the picker's view of the photo: the leveled photo for a car (as the
automatic crop sees it), the photo as taken for a locomotive. ANGLE is degrees
counter-clockwise, added on top. A car is re-cut from that view and sharpened for print; a
locomotive goes through ``loco_backdrop.clean`` (wiki/pipelines/intake-stages.md), so its old
print copy is removed. The OCR fields are left alone: a new crop does not re-read the photo.
"""
from __future__ import annotations

import json
from pathlib import Path

VIEW_DIR = "picker"  # inside the batch folder; gitignored with it
DATA_FILE = "picker.json"
VIEW_WIDTH = 1600  # the page needs a preview, not the full photo; box numbers stay full size


def parse_box(text: str) -> tuple[int, int, int, int, float]:
    parts = [p for p in text.replace(" ", "").split(",") if p]
    if len(parts) not in (4, 5):
        raise SystemExit(f"Crop must be X,Y,W,H or X,Y,W,H,ANGLE, not {text!r}")
    try:
        x, y, w, h = (int(round(float(p))) for p in parts[:4])
        angle = float(parts[4]) if len(parts) == 5 else 0.0
    except ValueError:
        raise SystemExit(f"Crop must be numbers: {text!r}") from None
    if w < 50 or h < 50:
        raise SystemExit(f"Crop {text!r} is too small (at least 50 x 50 pixels).")
    return x, y, w, h, angle


def format_box(x: float, y: float, w: float, h: float, angle: float = 0.0) -> str:
    box = f"{round(x)},{round(y)},{round(w)},{round(h)}"
    return box + (f",{angle:g}" if abs(angle) >= 0.05 else "")


def read_data(batch: Path) -> dict:
    path = batch / DATA_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_data(batch: Path, data: dict) -> None:
    (batch / DATA_FILE).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def source_png(row: dict, ctx) -> Path:
    return ctx.IMAGES_DIR / f"{Path(row['photo']).stem}.png"


def view_image(row: dict, ctx):
    """The image the picker shows and the box is measured on, and the automatic box on it."""
    from PIL import Image

    stem = Path(row["photo"]).stem
    if row.get("kind") == "loco":
        img = Image.open(source_png(row, ctx))
        img.load()
        auto = None
    else:
        import finalize_car_images as final

        found = final.finalize_box(stem)
        if found is None:
            from finalize_car_images import _level_for_finalize

            img, _ = _level_for_finalize(source_png(row, ctx), stem)
            auto = None
        else:
            img = found["leveled"]
            (cx, cy), (w, h) = found["center"], found["size"]
            auto = [cx - w / 2, cy - h / 2, w, h]
    if auto is None:  # a loose box around the middle of the photo
        w, h = img.size[0] * 0.8, img.size[1] * 0.35
        auto = [img.size[0] * 0.1, img.size[1] * 0.5 - h / 2, w, h]
    return img, [round(v) for v in auto]


def prepare(batch: Path, rows: list[dict], ctx, force: bool = False) -> int:
    """Write the picker's view of each photo. Rows whose view exists for their kind are kept."""
    data = read_data(batch)
    made = 0
    for r in rows:
        if not r.get("image"):
            continue  # processing failed: nothing to crop from
        have = data.get(r["photo"])
        if have and have.get("kind") == r["kind"] and not force and (batch / have["src"]).is_file():
            continue
        if not source_png(r, ctx).is_file():
            print(f"  {r['photo']}: no source photo {source_png(r, ctx)}")
            continue
        img, auto = view_image(r, ctx)
        out = batch / VIEW_DIR / f"{Path(r['photo']).stem}.{r['kind']}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        small = img.convert("RGB")
        small.thumbnail((VIEW_WIDTH, VIEW_WIDTH * 4))
        small.save(out, quality=85)
        data[r["photo"]] = {"kind": r["kind"], "src": f"{VIEW_DIR}/{out.name}",
                            "w": img.size[0], "h": img.size[1], "auto": auto}
        made += 1
    write_data(batch, data)
    return made


def cut(row: dict, ctx):
    """The new card image for a row's ``crop`` box (not saved)."""
    from PIL import Image

    from crop_car_image import _backdrop_color, _crop_at_fixed_size

    x, y, w, h, angle = parse_box(row["crop"])
    stem = Path(row["photo"]).stem
    if row["kind"] == "loco":
        img = Image.open(source_png(row, ctx))
    else:
        from finalize_car_images import _level_for_finalize

        img, _ = _level_for_finalize(source_png(row, ctx), stem)
    img = img.convert("RGB")
    if angle:  # about the centre, same size: the picker turns the image the same way
        img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=_backdrop_color(img))
    out = _crop_at_fixed_size(img, x + w / 2, y + h / 2, w, h)
    if row["kind"] == "loco":
        from loco_backdrop import REF_WIDTH, clean

        out = clean(out, (0, 0, REF_WIDTH, round(h * REF_WIDTH / w)))
    return out


def apply(row: dict, ctx) -> Path:
    """Re-cut the card image for a row's ``crop``. Updates the row's image and blur."""
    from car_paths import CARD_FILL_PRINT_DIR
    from intake_stages import blur_score
    from sharpen_card_fill_images import sharpen_for_print

    stem = Path(row["photo"]).stem
    out = cut(row, ctx)
    final = ctx.FINAL_DIR / f"{stem}.png"
    final.parent.mkdir(parents=True, exist_ok=True)
    out.save(final)
    printed = CARD_FILL_PRINT_DIR / f"{stem}.png"
    if row["kind"] == "loco":
        printed.unlink(missing_ok=True)  # the card builder prefers this folder: a stale crop wins
    else:
        printed.parent.mkdir(parents=True, exist_ok=True)
        sharpen_for_print(out).save(printed)
    row["image"] = str(final)
    row["blur"] = f"{blur_score(final):.0f}"
    return final


PICKER_CSS = """
#pk{position:fixed;inset:0;background:rgba(0,0,0,.75);display:none;z-index:9;overflow:auto}
#pk.on{display:block}#pk .box{background:#fff;max-width:1100px;margin:24px auto;padding:12px 16px;border-radius:8px}
#pk .frame{position:relative;overflow:hidden;border:1px solid #999;background:#777;cursor:grab;touch-action:none;
 user-select:none;margin:8px auto}#pk .frame.drag{cursor:grabbing}
#pk .frame img,.pv img{position:absolute;left:0;top:0;max-width:none;pointer-events:none}
#pk .ctl{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:8px 0}
#pk .ctl label{display:flex;gap:6px;align-items:center;margin:0;font-size:13px}
#pk .ctl input[type=range]{width:180px}#pk .ctl input[type=number]{width:5em}
#pk pre{background:#f3f3f1;padding:6px 8px;white-space:pre-wrap;margin:6px 0}
.pv{position:relative;overflow:hidden;width:100%;background:#777}
.adj{margin:4px 0}.crop-set{display:block;color:#1d5fa8;font-size:12px}
"""

PICKER_SCRIPT = r"""
const PICK=%(pick)s, BATCH=%(batch)s;
const pk=document.getElementById('pk'), fr=document.getElementById('pkf'), im=document.getElementById('pki');
const zoom=document.getElementById('pkz'), ang=document.getElementById('pka'), shp=document.getElementById('pks');
const out=document.getElementById('pko');
let cur=null, cx=0, cy=0, cw=1, ar=1, an=0, drag=null;
function parse(t){const p=(t||'').split(',').map(Number);return p.length>=4&&p.every(v=>!isNaN(v))?p:null}
function fmt(){return [cx,cy,cw,cw/ar].map(Math.round).join(',')+(Math.abs(an)>=0.05?','+(+an.toFixed(1)):'')}
function place(img,box,W,H,P){  // draw the box of photo P into a W x H frame
 const s=W/box[2], a=box[4]||0;
 img.style.width=P.w*s+'px';img.style.height=P.h*s+'px';
 img.style.left=-box[0]*s+'px';img.style.top=-box[1]*s+'px';
 img.style.transformOrigin=(P.w*s/2)+'px '+(P.h*s/2)+'px';
 img.style.transform='rotate('+(-a)+'deg)'}
function maxW(){return Math.min(cur.P.w*1.2, cur.P.h*1.2*ar)}
function size(){const avail=Math.min(pk.clientWidth-64,1060), H=Math.min(avail/ar, window.innerHeight*0.6);
 fr.style.width=H*ar+'px';fr.style.height=H+'px';return [H*ar,H]}
function render(){
 cw=Math.max(150,Math.min(cw,maxW()));
 cx=Math.max(-cw/2,Math.min(cx,cur.P.w-cw/2));const ch=cw/ar;cy=Math.max(-ch/2,Math.min(cy,cur.P.h-ch/2));
 const [W,H]=size();place(im,[cx,cy,cw,ch,an],W,H,cur.P);
 zoom.value=Math.round((1-(cw-150)/(maxW()-150))*1000);
 out.textContent='crop '+fmt()+'   ('+Math.round(cw)+' x '+Math.round(ch)+' px, shape '+ar.toFixed(2)+':1)\n'+
  'bin/cars crop '+BATCH+' '+cur.photo+' '+fmt()}
function openPicker(i){const P=PICK[ROWS[i].photo]; if(!P) return;
 const set=parse(document.querySelector('[data-i="'+i+'"][data-f="crop"]').value)||P.auto;
 cur={i,P,photo:ROWS[i].photo};[cx,cy,cw]=set;ar=set[2]/set[3];an=set[4]||0;
 im.src=P.src;shp.value=ar.toFixed(2);ang.value=an;document.getElementById('pkt').textContent=ROWS[i].photo+' ('+P.kind+')';
 pk.classList.add('on');render()}
function preview(i){const P=PICK[ROWS[i].photo], c=document.getElementById('c'+i); if(!P||!c) return;
 const v=document.querySelector('[data-i="'+i+'"][data-f="crop"]'), box=parse(v.value);
 let pv=c.querySelector('.pv'), orig=c.querySelector('img.orig'), note=c.querySelector('.crop-set');
 const done=box&&v.value===(ROWS[i].crop||'');  // already cut: the card image is the real thing
 if(!box||done){if(pv)pv.remove();if(orig)orig.style.display='';note.textContent=done?'crop '+v.value:'';return}
 if(!pv){pv=document.createElement('div');pv.className='pv';pv.innerHTML='<img>';c.insertBefore(pv,c.firstChild)}
 if(orig)orig.style.display='none';
 const W=pv.clientWidth||300,H=W*box[3]/box[2];pv.style.height=H+'px';const img=pv.querySelector('img');img.src=P.src;
 place(img,box,W,H,P);note.textContent='new crop '+v.value+' (applied by sheet-import)'}
fr.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,cx,cy};fr.setPointerCapture(e.pointerId);fr.classList.add('drag')});
fr.addEventListener('pointermove',e=>{if(!drag)return;const s=fr.clientWidth/cw;
 // the box is measured on the turned photo, so a move on screen is a move of the box
 const dx=(e.clientX-drag.x)/s, dy=(e.clientY-drag.y)/s;
 cx=drag.cx-dx;cy=drag.cy-dy;render()});
const end=()=>{drag=null;fr.classList.remove('drag')};fr.addEventListener('pointerup',end);fr.addEventListener('pointercancel',end);
function zoomAt(f,px,py){const s=fr.clientWidth/cw, ox=cx+px/s, oy=cy+py/s;
 cw=Math.max(150,Math.min(maxW(),cw*f));const ns=fr.clientWidth/cw;cx=ox-px/ns;cy=oy-py/ns;render()}
fr.addEventListener('wheel',e=>{e.preventDefault();const r=fr.getBoundingClientRect();
 zoomAt(e.deltaY>0?1.06:1/1.06,e.clientX-r.left,e.clientY-r.top)},{passive:false});
zoom.addEventListener('input',()=>{const W=fr.clientWidth,H=fr.clientHeight,t=zoom.value/1000;
 zoomAt((maxW()-t*(maxW()-150))/cw,W/2,H/2)});
ang.addEventListener('input',()=>{an=+ang.value;render()});
shp.addEventListener('change',()=>{const v=+shp.value;if(v>0.3&&v<10){const ch=cw/ar,my=cy+ch/2;ar=v;cy=my-cw/ar/2;render()}});
document.getElementById('pkr').onclick=()=>{const a=cur.P.auto;[cx,cy,cw]=a;ar=a[2]/a[3];an=0;ang.value=0;shp.value=ar.toFixed(2);render()};
document.getElementById('pkc').onclick=()=>{if(navigator.clipboard)navigator.clipboard.writeText('bin/cars crop '+BATCH+' '+cur.photo+' '+fmt()).catch(()=>{})};
document.getElementById('pku').onclick=()=>{const v=document.querySelector('[data-i="'+cur.i+'"][data-f="crop"]');
 v.value=fmt();v.dispatchEvent(new Event('input'));preview(cur.i);pk.classList.remove('on')};
document.getElementById('pkx').onclick=()=>pk.classList.remove('on');
document.getElementById('pkn').onclick=()=>{const v=document.querySelector('[data-i="'+cur.i+'"][data-f="crop"]');
 v.value='';v.dispatchEvent(new Event('input'));preview(cur.i);pk.classList.remove('on')};
document.addEventListener('keydown',e=>{if(e.key==='Escape')pk.classList.remove('on')});
window.addEventListener('resize',()=>{if(pk.classList.contains('on'))render()});
document.querySelectorAll('.adj').forEach(b=>b.onclick=()=>openPicker(+b.dataset.i));
ROWS.forEach((_,i)=>preview(i));
"""

PICKER_HTML = """
<div id=pk><div class=box><b id=pkt></b>
<p style="margin:4px 0">Drag the photo to move it, scroll or use the zoom slider to zoom, and turn the angle
slider to straighten. The frame is the shape of the card image, so what you see is what the card
shows. Change the shape (width&nbsp;:&nbsp;height) for a taller or wider image.</p>
<div class=frame id=pkf><img id=pki alt=""></div>
<div class=ctl><label>Zoom <input type=range id=pkz min=0 max=1000></label>
<label>Angle <input type=range id=pka min=-8 max=8 step=0.1 value=0></label>
<label>Shape <input type=number id=pks step=0.05 min=0.5 max=8></label>
<button id=pkr>Automatic crop</button><button id=pkc>Copy command</button>
<button id=pkn>Clear new crop</button><button id=pku><b>Use this crop</b></button><button id=pkx>Close</button></div>
<pre id=pko></pre></div></div>
"""


def page_parts(batch: Path, rows: list[dict]) -> tuple[str, str, str, dict]:
    """CSS, HTML and script for the page, and the photos that have a picker view."""
    data = read_data(batch)
    pick = {}
    for r in rows:
        d = data.get(r["photo"])
        if d and d.get("kind") == r["kind"] and (batch / d["src"]).is_file():
            pick[r["photo"]] = {**d, "src": f"{VIEW_DIR}/{Path(d['src']).name}"}
    if not pick:
        return "", "", "", {}
    script = PICKER_SCRIPT % {"pick": json.dumps(pick).replace("</", "<\\/"),
                              "batch": json.dumps(batch.name)}
    return PICKER_CSS, PICKER_HTML, script, pick


def cmd_crop(args, ctx) -> int:
    import intake_stages as st

    batch = st.batch_dir(args.batch)
    path = batch / "review.csv"
    if not path.is_file():
        raise SystemExit(f"No batch {args.batch} ({path})")
    rows = st.read_csv(path)
    for r in rows:
        r.setdefault("crop", "")
    if args.photo is None:
        made = prepare(batch, rows, ctx, force=args.refresh)
        st.contact_sheet(batch / "review.html", rows)
        print(f"Picker ready for {made} photos. Open {batch / 'review.html'}")
        return 0
    if args.box is None:
        raise SystemExit("Give the box too: cars.py crop BATCH PHOTO X,Y,W,H[,ANGLE]")
    row = next((r for r in rows if r["photo"] == args.photo), None)
    if row is None:
        raise SystemExit(f"Not in the batch: {args.photo}")
    parse_box(args.box)
    row["crop"] = args.box
    final = apply(row, ctx)
    st.write_csv(path, st.REVIEW_COLUMNS, rows)
    st.contact_sheet(batch / "review.html", rows)
    print(f"{row['photo']}: new card image {final} (blur {row['blur']}). Check it by eye.")
    return 0
