#!/usr/bin/env python3
"""Render a promo video: vertical for TikTok, Reels and Shorts, or 16:9 for YouTube.

    .venv/bin/python tools/promo/tiktok_promo.py                          # TikTok / Shorts
    .venv/bin/python tools/promo/tiktok_promo.py --format landscape --music   # YouTube

Videos go to media/promo/ and page captures are read from media/promo/shots/
(both in the gitignored media mirror). The shot crops in site_cut are pixel
offsets into those captures, so after the site changes, delete the old capture,
let the script take a new one, and check the crops. See docs/website/promo-videos.md.

Builds the cut from material already in the repo: layout photos from
media/photos-layout (the gitignored mirror), the schematic and USS CTC
evolution videos in www/assets/behind/panel-evolution, and phone-width
captures of live site pages (taken with headless Chrome). Every frame is
drawn with Pillow and piped to ffmpeg, so this ffmpeg build needs no
drawtext. Two cuts: "build" (empty room to railroad) and "site" (a tour of
the website's Prototype, Operations, Behind the Scenes and AI sections).

The output has a silent audio track unless --music is given, which mixes in
an original synthesised soundtrack from soundtrack.py (no rights holder, so
nothing for Content ID to claim). On TikTok, add a sound from its library
instead; do not bake in commercial music.

Captions use Barlow Condensed, the site's display face, from tools/promo/fonts/
(SIL OFL, licence beside it). Without it the script falls back to Avenir Next
Condensed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
PHOTOS = ROOT / "media" / "photos-layout"
EVOLUTION = ROOT / "www" / "assets" / "behind" / "panel-evolution"
LOGO = ROOT / "www" / "assets" / "media" / "hart-logo.png"
FONTS = Path(__file__).resolve().parent / "fonts"
OUT = ROOT / "media" / "promo"
SITE_URL = "https://www.hartrailroad.com/"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

W, H, FPS = 1080, 1920, 30
LAND = False  # 16:9 for YouTube: captions in a left column, content on the right
STAGE = (0, 0, W, H)  # where content sits (x0, y0, x1, y1)


def set_format(fmt: str) -> None:
    """"vertical" (TikTok, Reels, Shorts) or "landscape" (YouTube, 1920x1080)."""
    global W, H, LAND, STAGE
    LAND = fmt == "landscape"
    W, H = (1920, 1080) if LAND else (1080, 1920)
    STAGE = (720, 60, 1860, 1020) if LAND else (0, 0, W, H)


def stage_centre() -> tuple[int, int]:
    return (STAGE[0] + STAGE[2]) // 2, (STAGE[1] + STAGE[3]) // 2
BRAND = (11, 52, 62)  # dark teal of the site footer band
GOLD = (240, 192, 85)  # --accent-on-dark
WHITE = (255, 255, 255)

# Site pages for the "site" cut, captured live at phone width (path -> file stem).
PAGES = {
    "": "home",
    "history/": "history",
    "plants/": "plants",
    "railroads/": "railroads",
    "photos/": "photos",
    "operators/cards/": "cards",
    "operators/room/": "room",
    "crew/": "crew",
    "build/": "build",
    "behind/": "behind",
    "behind/signals.html": "signals",
    "behind/wiring.html": "wiring",
    "behind/panel-evolution.html": "panels",
    "ai/": "ai",
    "ai/control.html": "ai-control",
    "ai/speed-runs.html": "speed-runs",
}


# ---------------------------------------------------------------- fonts / text

class Fonts:
    def __init__(self, font_dir: Path | None) -> None:
        heavy = font_dir / "BarlowCondensed-ExtraBold.ttf" if font_dir else None
        semi = font_dir / "BarlowCondensed-SemiBold.ttf" if font_dir else None
        if heavy and heavy.exists() and semi and semi.exists():
            self.heavy, self.semi, self.index = str(heavy), str(semi), (0, 0)
        else:
            avenir = "/System/Library/Fonts/Avenir Next Condensed.ttc"
            self.heavy = self.semi = avenir
            self.index = (8, 4)  # Heavy, Demi Bold

    def get(self, size: int, heavy: bool = True) -> ImageFont.FreeTypeFont:
        path = self.heavy if heavy else self.semi
        return ImageFont.truetype(path, size, index=self.index[0 if heavy else 1])


def wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if draw.textlength(trial, font=font) <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def caption_layer(fonts: Fonts, text: str, kicker: str = "", y: int = 330) -> Image.Image:
    """Caption on a dark band, kept out of TikTok's top bar and bottom/right UI.

    Landscape puts it in a column left of the stage, centred top to bottom.
    """
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if LAND:
        font, kfont = fonts.get(84), fonts.get(40, heavy=False)
        lines = wrap(d, text.upper(), font, 560)
        line_h, pad, x0, x1 = 88, 40, 60, 680
        block_h = len(lines) * line_h + (60 if kicker else 0)
        top = (H - block_h) // 2
        d.rounded_rectangle((x0, top - pad, x1, top + block_h + pad - 6), radius=26,
                            fill=(*BRAND, 228))
        cy = top
        if kicker:
            d.text((x0 + 40, cy), kicker.upper(), font=kfont, fill=GOLD)
            cy += 60
        for line in lines:
            d.text((x0 + 40, cy), line, font=font, fill=WHITE)
            cy += line_h
        return layer
    font = fonts.get(104)
    kfont = fonts.get(44, heavy=False)
    lines = wrap(d, text.upper(), font, 860)
    line_h = 108
    pad = 34
    block_h = len(lines) * line_h + (64 if kicker else 0)
    top = y
    box = (W // 2 - 470, top - pad, W // 2 + 470, top + block_h + pad - 6)
    d.rounded_rectangle(box, radius=26, fill=(*BRAND, 218))
    cy = top
    if kicker:
        d.text((W // 2, cy), kicker.upper(), font=kfont, fill=GOLD, anchor="mt")
        cy += 64
    for line in lines:
        d.text((W // 2, cy), line, font=font, fill=WHITE, anchor="mt")
        cy += line_h
    return layer


# ---------------------------------------------------------------- segments

@dataclass
class Segment:
    frames: Callable[[int], Iterator[Image.Image]]  # n -> RGB frames
    seconds: float
    caption: str = ""
    kicker: str = ""
    caption_y: int = 330
    extra: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return round(self.seconds * FPS)


def cover(im: Image.Image, w: int, h: int, focus=(0.5, 0.5)) -> Image.Image:
    return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=focus)


def photo(name: str, zoom=(1.0, 1.1), focus=(0.5, 0.5), drift=(0.0, 0.0)):
    """Slow push-in on one photo (Ken Burns), drawn from a 1.3x base."""
    def gen(n: int) -> Iterator[Image.Image]:
        src = ImageOps.exif_transpose(Image.open(PHOTOS / name)).convert("RGB")
        if LAND and src.height > src.width:
            yield from framed(src, n)
            return
        k = 1.3
        base = cover(src, int(W * k), int(H * k), focus)
        bw, bh = base.size
        for i in range(n):
            t = i / max(n - 1, 1)
            t = t * t * (3 - 2 * t)  # ease
            z = zoom[0] + (zoom[1] - zoom[0]) * t
            cw, ch = W * k / z, H * k / z
            cx = bw / 2 + drift[0] * W * t
            cy = bh / 2 + drift[1] * H * t
            box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
            yield base.resize((W, H), Image.BICUBIC, box=box)
    def framed(src: Image.Image, n: int) -> Iterator[Image.Image]:
        # Portrait photo in a 16:9 frame: sharp on the stage, blurred fill behind.
        blur = cover(src, W // 8, H // 8).filter(ImageFilter.GaussianBlur(4)).resize((W, H))
        blur = Image.blend(blur, Image.new("RGB", (W, H), BRAND), 0.45)
        ph = STAGE[3] - STAGE[1]
        pw = round(ph * src.width / src.height)
        sharp = src.resize((round(pw * 1.2), round(ph * 1.2)), Image.LANCZOS)
        cx, cy = stage_centre()
        for i in range(n):
            t = i / max(n - 1, 1)
            t = t * t * (3 - 2 * t)
            z = zoom[0] + (zoom[1] - zoom[0]) * t
            cw, ch = sharp.width / z, sharp.height / z
            bx = (sharp.width - cw) / 2
            by = (sharp.height - ch) / 2
            im = sharp.resize((pw, ph), Image.BICUBIC, box=(bx, by, bx + cw, by + ch))
            frame = blur.copy()
            frame.paste(im, (cx - pw // 2, cy - ph // 2))
            yield frame
    return gen


def video_frames(path: Path, vf: str, size: tuple[int, int], start: float = 0.0,
                 seconds: float | None = None) -> Iterator[Image.Image]:
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start)]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-i", str(path), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    frame_bytes = size[0] * size[1] * 3
    assert proc.stdout
    while True:
        buf = proc.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        yield Image.frombytes("RGB", size, buf)
    proc.wait()


def schematic(n: int) -> Iterator[Image.Image]:
    """The system schematic drawing itself, sped up to fit n frames."""
    src = EVOLUTION / "schematic-evolution.mp4"
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(src)]).strip())
    speed = dur / (n / FPS)
    # Crop the frame border and fit the whole sheet to the phone width.
    fw, fh = (1140, 880) if LAND else (1040, 800)
    vf = (f"setpts=PTS/{speed:.4f},fps={FPS},crop=1372:1058:14:11,"
          f"scale={fw}:{fh}:flags=lanczos")
    frames = list(video_frames(src, vf, (fw, fh)))
    last = frames[-1] if frames else Image.new("RGB", (fw, fh), WHITE)
    for i in range(n):
        im = frames[i] if i < len(frames) else last
        canvas = Image.new("RGB", (W, H), WHITE)
        if LAND:
            cx, cy = stage_centre()
            canvas.paste(im, (cx - fw // 2, cy - fh // 2))
        else:
            canvas.paste(im, ((W - fw) // 2, 700))
        yield canvas


def ctc_pan(n: int) -> Iterator[Image.Image]:
    """Pan across the USS CTC machine while its last changes come in."""
    src = EVOLUTION / "uss-panel-evolution.mp4"
    ph = 800 if LAND else 1120
    pw = round(1200 * ph / 652)
    view = STAGE[2] - STAGE[0]
    vf = f"fps={FPS},crop=1200:652:0:62,scale={pw}:{ph}:flags=lanczos"
    frames = list(video_frames(src, vf, (pw, ph), start=19.0))
    bg = (34, 34, 42)
    for i in range(n):
        t = i / max(n - 1, 1)
        t = t * t * (3 - 2 * t)
        im = frames[min(len(frames) - 1, int(i * len(frames) / n))]
        x = int((pw - view) * t)
        canvas = Image.new("RGB", (W, H), bg)
        top = (H - ph) // 2 if LAND else 620
        canvas.paste(im.crop((x, 0, x + view, ph)), (STAGE[0], top))
        yield canvas


def backdrop(name: str | None) -> Image.Image:
    """Brand colour, or a layout photo blurred and tinted towards it."""
    if not name:
        return Image.new("RGB", (W, H), BRAND)
    src = ImageOps.exif_transpose(Image.open(PHOTOS / name)).convert("RGB")
    im = cover(src, W // 4, H // 4).filter(ImageFilter.GaussianBlur(6)).resize((W, H))
    return Image.blend(im, Image.new("RGB", (W, H), BRAND), 0.62)


def phone_scroll(shot: Path, travel: int = 3300, start: int = 0, top: int = 410,
                 sh: int = 1500, bg: str | None = None, hold: float = 0.12):
    """A page capture scrolling inside a rounded phone-sized card."""
    def gen(n: int) -> Iterator[Image.Image]:
        page = Image.open(shot).convert("RGB")
        sw, sh_, top_ = (560, 940, 70) if LAND else (900, sh, top)
        cx = stage_centre()[0]
        page = page.resize((sw, round(page.height * sw / page.width)), Image.LANCZOS)
        dist = max(0, min(page.height - sh_ - start, travel))
        mask = Image.new("L", (sw, sh_), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw, sh_), radius=48, fill=255)
        base = backdrop(bg)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (cx - sw // 2 - 6, top_ + 10, cx + sw // 2 + 6, top_ + sh_ + 18), radius=54,
            fill=(0, 0, 0, 150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        base.paste(shadow, (0, 0), shadow)
        wait = int(n * hold)
        for i in range(n):
            t = max(0.0, (i - wait) / max(n - 1 - wait, 1))
            t = t * t * (3 - 2 * t)
            y = start + int(dist * t)
            frame = base.copy()
            frame.paste(page.crop((0, y, sw, y + sh_)), (cx - sw // 2, top_), mask)
            yield frame
    return gen


def end_card(fonts: Fonts, lines=("Neville Island, Pittsburgh · HO scale",
                                   "Follow along as it gets built")):
    def gen(n: int) -> Iterator[Image.Image]:
        card = Image.new("RGB", (W, H), BRAND)
        logo = Image.open(LOGO).convert("RGBA")
        size, top, url_y, line_y = (420, 90, 560, 700) if LAND else (560, 420, 1060, 1200)
        logo = logo.resize((size, size), Image.LANCZOS)
        card.paste(logo, ((W - size) // 2, top), logo)
        d = ImageDraw.Draw(card)
        d.text((W // 2, url_y), "HARTRAILROAD.COM", font=fonts.get(118), fill=GOLD, anchor="mt")
        for k, line in enumerate(lines):
            d.text((W // 2, line_y + 75 * k), line,
                   font=fonts.get(54, heavy=False), fill=WHITE, anchor="mt")
        for _ in range(n):
            yield card
    return gen


def build_cut(fonts: Fonts, shots: dict[str, Path]) -> list[Segment]:
    """Empty room to railroad, then the panels and the site."""
    hook = "This room was empty."
    built = "…so I built a railroad in it"
    cuts = [  # photo, focus
        ("IMG_5280.jpg", (0.5, 0.5)),
        ("IMG_6653.jpg", (0.45, 0.5)),
        ("IMG_6844.jpg", (0.5, 0.5)),
        ("IMG_0691.jpg", (0.5, 0.5)),
        ("IMG_7813.jpg", (0.5, 0.5)),
        ("IMG_7915.jpg", (0.5, 0.5)),
        ("IMG_8070.jpg", (0.5, 0.5)),
    ]
    segs = [Segment(photo("IMG_4038.jpg", zoom=(1.0, 1.06)), 1.8, hook)]
    segs += [Segment(photo(p, zoom=(1.04, 1.12), focus=f), 0.6, built) for p, f in cuts]
    segs += [
        Segment(photo("IMG_8904.jpg", zoom=(1.0, 1.12)), 2.6,
                "Neville Island in HO", kicker="Pittsburgh · Ohio River"),
        Segment(photo("IMG_9288.jpg", zoom=(1.12, 1.0)), 2.2,
                "Real industries. Real car forwarding."),
        Segment(schematic, 4.0, "Every track drawn and numbered", caption_y=300),
        Segment(ctc_pan, 5.0, "Signals run from a CTC panel", caption_y=300),
        Segment(phone_scroll(shots["home"]), 5.0, "The whole story is online",
                caption_y=150),
        Segment(end_card(fonts), 3.0),
    ]
    return segs


def page_shot(shot: Path, y0: int, y1: int, x0: int = 0, x1: int = 1080,
              tilt: float = 0.0, bg: str | None = None, area=(540, 1820)):
    """One region of a page capture as a card: pops in, then creeps closer.

    y0..x1 are pixels in the 1080 px wide capture. Full-width regions show at
    960 px; narrower crops show at 1000 px, so they read as a zoom.
    """
    def gen(n: int) -> Iterator[Image.Image]:
        region = Image.open(shot).convert("RGB").crop((x0, y0, x1, y1))
        dw = 960 if x1 - x0 >= 1080 else 1000
        dh = round(region.height * dw / region.width)
        room = area[1] - area[0]
        if LAND:
            dw = min(dw, STAGE[2] - STAGE[0] - 80)
            dh = round(region.height * dw / region.width)
            room = STAGE[3] - STAGE[1] - 40
        if dh > room:
            dw, dh = round(dw * room / dh), room
        region = region.resize((dw, dh), Image.LANCZOS)
        pad = 60
        card = Image.new("RGBA", (dw + 2 * pad, dh + 2 * pad), (0, 0, 0, 0))
        sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((pad - 4, pad + 8, pad + dw + 4, pad + dh + 16),
                                             radius=34, fill=(0, 0, 0, 160))
        card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
        mask = Image.new("L", (dw, dh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, dw, dh), radius=30, fill=255)
        card.paste(region, (pad, pad), mask)
        base = backdrop(bg)
        cx, cy = stage_centre() if LAND else (W // 2, (area[0] + area[1]) // 2)
        for i in range(n):
            pop = 4
            if i < pop:
                k = (i + 1) / pop
                scale = 1.10 - 0.10 * (k * (2 - k))
            else:
                scale = 1.0 + 0.035 * (i - pop) / max(n - pop, 1)
            im = card.resize((round(card.width * scale), round(card.height * scale)),
                             Image.BICUBIC)
            if tilt:
                im = im.rotate(tilt, resample=Image.BICUBIC, expand=True)
            frame = base.copy().convert("RGBA")
            frame.alpha_composite(im, (cx - im.width // 2, cy - im.height // 2))
            yield frame.convert("RGB")
    return gen


def slam(fonts: Fonts, word: str, count: str, bg: str | None):
    """Section title card: the name punches in over a gold rule."""
    def gen(n: int) -> Iterator[Image.Image]:
        base = backdrop(bg)
        for i in range(n):
            k = min(1.0, (i + 1) / 4)
            size = round(190 * (1.35 - 0.35 * (k * (2 - k))))
            frame = base.copy()
            d = ImageDraw.Draw(frame)
            font = fonts.get(size)
            lines = wrap(d, word.upper(), font, 980)
            y = H // 2 - len(lines) * size * 0.95 / 2
            d.text((W // 2, y - 90), count, font=fonts.get(64, heavy=False), fill=GOLD, anchor="mt")
            for line in lines:
                d.text((W // 2, y), line, font=font, fill=WHITE, anchor="mt")
                y += size * 0.95
            d.rectangle((W // 2 - 150, y + 30, W // 2 + 150, y + 42), fill=GOLD)
            yield frame
    return gen


def site_cut(fonts: Fonts, shots: dict[str, Path]) -> list[Segment]:
    """Rapid-fire tour of the site: four sections, a title slam then quick shots."""
    sections = [  # name, caption, backdrop, shots (page, y0, y1, x0, x1, tilt)
        ("Prototype", "Real Neville Island history", "IMG_9231.jpg", [
            ("history", 120, 1400, 0, 1080, 0),
            ("photos", 1900, 3000, 0, 1080, -3),
            ("plants", 4300, 5700, 0, 1080, 0),
            ("photos", 2900, 4000, 0, 1080, 3),
            ("railroads", 2700, 3700, 0, 1080, 0),
            ("photos", 5800, 6950, 0, 1080, -2.5),
        ]),
        ("Operations", "Car cards, waybills and crew sheets", "IMG_8904.jpg", [
            ("cards", 330, 1650, 60, 1020, 0),
            ("cards", 3360, 4440, 150, 930, -3),
            ("cards", 4500, 5560, 150, 930, 3),
            ("crew", 560, 2300, 0, 1080, 0),
            ("room", 1150, 2500, 0, 1080, -2),
            ("cards", 6560, 7160, 20, 780, 0),
        ]),
        ("Behind the Scenes", "How it's built, wired and signalled", "IMG_7813.jpg", [
            ("behind", 280, 660, 20, 560, 0),
            ("behind", 2230, 2960, 0, 1080, 3),
            ("signals", 1600, 2550, 0, 1080, 0),
            ("wiring", 1350, 2750, 0, 1080, -3),
            ("build", 5550, 6800, 0, 1080, 0),
            ("panels", 5400, 6000, 380, 700, 2.5),
            ("build", 4250, 5500, 0, 1080, 0),
        ]),
        ("The Diverging Route", "How AI helps build and run it", "IMG_9288.jpg", [
            ("ai", 600, 2150, 0, 1080, 0),
            ("speed-runs", 2600, 3450, 0, 1080, -3),
            ("speed-runs", 6100, 6950, 0, 1080, 0),
            ("ai-control", 0, 1650, 0, 1080, 3),
            ("ai", 4300, 5450, 0, 1080, 0),
            ("ai", 7150, 7700, 0, 1080, -2),
        ]),
    ]
    segs = [Segment(page_shot(shots["home"], 0, 1950, bg="IMG_8904.jpg"), 2.1,
                    "My model railroad has its own website", caption_y=150)]
    for k, (name, caption, bg, picks) in enumerate(sections, 1):
        segs.append(Segment(slam(fonts, name, f"{k} / {len(sections)}", bg), 0.7))
        for page, y0, y1, x0, x1, tilt in picks:
            segs.append(Segment(page_shot(shots[page], y0, y1, x0, x1, tilt, bg), 0.7,
                                caption, kicker=name, caption_y=150))
    segs.append(Segment(end_card(fonts, ("Prototype · Operations · Behind the Scenes",
                                         "The Diverging Route: AI in model railroading")),
                        3.5))
    return segs


CUTS = {"build": build_cut, "site": site_cut}


# ---------------------------------------------------------------- render

def capture_pages(out: Path) -> dict[str, Path]:
    """Phone-width captures of the live pages in PAGES, reusing files in out.

    Headless Chrome on macOS lays out no narrower than about 500 CSS px, so a
    390 px window clips the page; 500 px at 2.16x gives a clean 1080 px image.
    """
    out.mkdir(parents=True, exist_ok=True)
    shots = {}
    for path, stem in PAGES.items():
        shot = out / f"{stem}.png"
        if not shot.exists():
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--virtual-time-budget=6000", "--force-device-scale-factor=2.16",
                            "--window-size=500,3600", f"--screenshot={shot}", SITE_URL + path],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shots[stem] = shot
    return shots


def render(segs: list[Segment], fonts: Fonts, out: Path) -> None:
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
         "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k",
         str(out)], stdin=subprocess.PIPE)
    assert enc.stdin
    prev = None
    cache: dict[tuple, Image.Image] = {}
    for seg in segs:
        key = (seg.caption, seg.kicker, seg.caption_y)
        layer = None
        if seg.caption:
            layer = cache.get(key) or caption_layer(fonts, seg.caption, seg.kicker, seg.caption_y)
            cache[key] = layer
        fade = 5 if key != prev else 0  # fade only when the caption changes
        for i, frame in enumerate(seg.frames(seg.n)):
            if layer is not None:
                a = layer
                if i < fade:
                    alpha = layer.getchannel("A").point(lambda v, k=(i + 1) / (fade + 1): int(v * k))
                    a = layer.copy()
                    a.putalpha(alpha)
                frame = frame.convert("RGBA")
                frame.alpha_composite(a)
                frame = frame.convert("RGB")
            enc.stdin.write(frame.tobytes())
        prev = key
    enc.stdin.close()
    if enc.wait():
        raise SystemExit("ffmpeg failed")


def add_music(cut: str, video: Path, seconds: float, tmp: Path) -> None:
    """Replace the silent track with the cut's soundtrack, faded at the end."""
    import soundtrack  # same folder; numpy and scipy are only needed here

    wav = tmp / f"{cut}.wav"
    soundtrack.write(cut, str(wav))
    mixed = video.with_suffix(".music.mp4")
    af = (f"atrim=0:{seconds:.3f},afade=t=out:st={seconds - 0.6:.3f}:d=0.6,"
          "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(wav),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", af,
                    "-c:a", "aac", "-b:a", "192k", "-t", f"{seconds:.3f}",
                    "-movflags", "+faststart", str(mixed)], check=True)
    mixed.replace(video)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT, help="output directory (media/promo)")
    ap.add_argument("--font-dir", type=Path, default=FONTS,
                    help="folder with Barlow Condensed .ttf files (tools/promo/fonts)")
    ap.add_argument("--format", choices=("vertical", "landscape"), default="vertical",
                    help="vertical 1080x1920 (TikTok/Shorts) or landscape 1920x1080 (YouTube)")
    ap.add_argument("--cuts", default="build,site", help="comma list of: " + ", ".join(CUTS))
    ap.add_argument("--music", action="store_true",
                    help="mix in the cut's original soundtrack (soundtrack.py), -14 LUFS")
    ap.add_argument("--shots", type=Path, default=OUT / "shots",
                    help="folder for page captures; existing files are reused")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found")
    args.out.mkdir(parents=True, exist_ok=True)
    fonts = Fonts(args.font_dir)
    set_format(args.format)
    suffix = "-youtube" if LAND else ""
    with tempfile.TemporaryDirectory() as tmp:
        shots = capture_pages(args.shots or Path(tmp))
        for cut in args.cuts.split(","):
            out = args.out / f"hart-promo-{cut}{suffix}.mp4"
            segs = CUTS[cut](fonts, shots)
            render(segs, fonts, out)
            if args.music:
                add_music(cut, out, sum(seg.n for seg in segs) / FPS, Path(tmp))
            print(out)


if __name__ == "__main__":
    main()
