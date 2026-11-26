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
import functools
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

if str(Path(__file__).resolve().parent) not in sys.path:     # promo_shots and soundtrack sit beside this file
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from promo_shots import BUILD_QUICK, CUT_PAGES, SITE_SECTIONS, PromoError, capture_pages  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PHOTOS = ROOT / "media" / "photos-layout"
EVOLUTION = ROOT / "www" / "assets" / "behind" / "panel-evolution"
LOGO = ROOT / "www" / "assets" / "media" / "hart-logo.png"
FONTS = Path(__file__).resolve().parent / "fonts"
OUT = ROOT / "media" / "promo"

FPS = 30


@dataclass(frozen=True)
class Format:
    """A video's frame: its size, and the stage box (x0, y0, x1, y1) that content sits in."""
    name: str
    w: int
    h: int
    stage: tuple[int, int, int, int]

    @property
    def land(self) -> bool:
        """16:9 for YouTube: captions in a left column, content on the right."""
        return self.name == "landscape"

    def centre(self) -> tuple[int, int]:
        return (self.stage[0] + self.stage[2]) // 2, (self.stage[1] + self.stage[3]) // 2


FORMATS: dict[str, Format] = {
    "vertical": Format("vertical", 1080, 1920, (0, 0, 1080, 1920)),       # TikTok, Reels, Shorts
    "landscape": Format("landscape", 1920, 1080, (720, 60, 1860, 1020)),  # YouTube
}
Frames = Callable[[int], Iterator[Image.Image]]     # n -> n RGB frames

BRAND = (11, 52, 62)  # dark teal of the site footer band
GOLD = (240, 192, 85)  # --accent-on-dark
WHITE = (255, 255, 255)

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


def wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
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


def caption_layer(fonts: Fonts, fmt: Format, text: str, kicker: str = "", y: int = 330) -> Image.Image:
    """Caption on a dark band, kept out of TikTok's top bar and bottom/right UI.

    Landscape puts it in a column left of the stage, centred top to bottom.
    """
    layer = Image.new("RGBA", (fmt.w, fmt.h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if fmt.land:
        font, kfont = fonts.get(84), fonts.get(40, heavy=False)
        lines = wrap(d, text.upper(), font, 560)
        line_h, pad, x0, x1 = 88, 40, 60, 680
        block_h = len(lines) * line_h + (60 if kicker else 0)
        top = (fmt.h - block_h) // 2
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
    box = (fmt.w // 2 - 470, top - pad, fmt.w // 2 + 470, top + block_h + pad - 6)
    d.rounded_rectangle(box, radius=26, fill=(*BRAND, 218))
    cy = top
    if kicker:
        d.text((fmt.w // 2, cy), kicker.upper(), font=kfont, fill=GOLD, anchor="mt")
        cy += 64
    for line in lines:
        d.text((fmt.w // 2, cy), line, font=font, fill=WHITE, anchor="mt")
        cy += line_h
    return layer


# ---------------------------------------------------------------- segments

@dataclass
class Segment:
    frames: Frames
    seconds: float
    caption: str = ""
    kicker: str = ""
    caption_y: int = 330

    @property
    def n(self) -> int:
        return round(self.seconds * FPS)


def cover(im: Image.Image, w: int, h: int, focus: tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    return ImageOps.fit(im, (w, h), Image.LANCZOS, centering=focus)


def photo(fmt: Format, name: str, zoom: tuple[float, float] = (1.0, 1.1), focus: tuple[float, float] = (0.5, 0.5),
          drift: tuple[float, float] = (0.0, 0.0)) -> Frames:
    """Slow push-in on one photo (Ken Burns), drawn from a 1.3x base."""
    def gen(n: int) -> Iterator[Image.Image]:
        src = ImageOps.exif_transpose(Image.open(PHOTOS / name)).convert("RGB")
        if fmt.land and src.height > src.width:
            yield from framed(src, n)
            return
        k = 1.3
        base = cover(src, int(fmt.w * k), int(fmt.h * k), focus)
        bw, bh = base.size
        for i in range(n):
            t = i / max(n - 1, 1)
            t = t * t * (3 - 2 * t)  # ease
            z = zoom[0] + (zoom[1] - zoom[0]) * t
            cw, ch = fmt.w * k / z, fmt.h * k / z
            cx = bw / 2 + drift[0] * fmt.w * t
            cy = bh / 2 + drift[1] * fmt.h * t
            box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
            yield base.resize((fmt.w, fmt.h), Image.BICUBIC, box=box)
    def framed(src: Image.Image, n: int) -> Iterator[Image.Image]:
        # Portrait photo in a 16:9 frame: sharp on the stage, blurred fill behind.
        blur = cover(src, fmt.w // 8, fmt.h // 8).filter(ImageFilter.GaussianBlur(4)).resize((fmt.w, fmt.h))
        blur = Image.blend(blur, Image.new("RGB", (fmt.w, fmt.h), BRAND), 0.45)
        ph = fmt.stage[3] - fmt.stage[1]
        pw = round(ph * src.width / src.height)
        sharp = src.resize((round(pw * 1.2), round(ph * 1.2)), Image.LANCZOS)
        cx, cy = fmt.centre()
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
    if proc.wait():
        raise PromoError(f"ffmpeg could not decode {path}")


def schematic(fmt: Format) -> Frames:
    """The system schematic drawing itself, sped up to fit n frames."""
    return functools.partial(_schematic, fmt)


def _schematic(fmt: Format, n: int) -> Iterator[Image.Image]:
    src = EVOLUTION / "schematic-evolution.mp4"
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(src)]).strip())
    speed = dur / (n / FPS)
    # Crop the frame border and fit the whole sheet to the phone width.
    fw, fh = (1140, 880) if fmt.land else (1040, 800)
    vf = (f"setpts=PTS/{speed:.4f},fps={FPS},crop=1372:1058:14:11,"
          f"scale={fw}:{fh}:flags=lanczos")
    frames = list(video_frames(src, vf, (fw, fh)))
    if not frames:
        raise PromoError(f"no frames from {src}")
    last = frames[-1]
    for i in range(n):
        im = frames[i] if i < len(frames) else last
        canvas = Image.new("RGB", (fmt.w, fmt.h), WHITE)
        if fmt.land:
            cx, cy = fmt.centre()
            canvas.paste(im, (cx - fw // 2, cy - fh // 2))
        else:
            canvas.paste(im, ((fmt.w - fw) // 2, 700))
        yield canvas


def ctc_pan(fmt: Format) -> Frames:
    """Pan across the USS CTC machine while its changes come in (the whole film, about 8 s)."""
    return functools.partial(_ctc_pan, fmt)


def _ctc_pan(fmt: Format, n: int) -> Iterator[Image.Image]:
    src = EVOLUTION / "uss-panel-evolution.mp4"
    ph = 800 if fmt.land else 1120
    pw = round(1200 * ph / 652)
    view = fmt.stage[2] - fmt.stage[0]
    vf = f"fps={FPS},crop=1200:652:0:62,scale={pw}:{ph}:flags=lanczos"
    frames = list(video_frames(src, vf, (pw, ph)))
    if not frames:
        raise PromoError(f"no frames from {src}")
    bg = (34, 34, 42)
    for i in range(n):
        t = i / max(n - 1, 1)
        t = t * t * (3 - 2 * t)
        im = frames[min(len(frames) - 1, int(i * len(frames) / n))]
        x = int((pw - view) * t)
        canvas = Image.new("RGB", (fmt.w, fmt.h), bg)
        top = (fmt.h - ph) // 2 if fmt.land else 620
        canvas.paste(im.crop((x, 0, x + view, ph)), (fmt.stage[0], top))
        yield canvas


def backdrop(fmt: Format, name: str | None) -> Image.Image:
    """Brand colour, or a layout photo blurred and tinted towards it (a copy)."""
    return _backdrop(name, fmt).copy()


@functools.lru_cache(maxsize=16)
def _backdrop(name: str | None, fmt: Format) -> Image.Image:
    if not name:
        return Image.new("RGB", (fmt.w, fmt.h), BRAND)
    src = ImageOps.exif_transpose(Image.open(PHOTOS / name)).convert("RGB")
    im = cover(src, fmt.w // 4, fmt.h // 4).filter(ImageFilter.GaussianBlur(6)).resize((fmt.w, fmt.h))
    return Image.blend(im, Image.new("RGB", (fmt.w, fmt.h), BRAND), 0.62)


def phone_scroll(fmt: Format, shot: Path, travel: int = 3300, start: int = 0, top: int = 410,
                 sh: int = 1500, bg: str | None = None, hold: float = 0.12) -> Frames:
    """A page capture scrolling inside a rounded phone-sized card."""
    def gen(n: int) -> Iterator[Image.Image]:
        page = Image.open(shot).convert("RGB")
        sw, sh_, top_ = (560, 940, 70) if fmt.land else (900, sh, top)
        cx = fmt.centre()[0]
        page = page.resize((sw, round(page.height * sw / page.width)), Image.LANCZOS)
        dist = max(0, min(page.height - sh_ - start, travel))
        mask = Image.new("L", (sw, sh_), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw, sh_), radius=48, fill=255)
        base = backdrop(fmt, bg)
        shadow = Image.new("RGBA", (fmt.w, fmt.h), (0, 0, 0, 0))
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


def end_card(fonts: Fonts, fmt: Format, lines: Sequence[str] = ("Neville Island, Pittsburgh · HO scale",
                                                               "Follow along as it gets built")) -> Frames:
    def gen(n: int) -> Iterator[Image.Image]:
        card = Image.new("RGB", (fmt.w, fmt.h), BRAND)
        logo = Image.open(LOGO).convert("RGBA")
        size, top, url_y, line_y = (420, 90, 560, 700) if fmt.land else (560, 420, 1060, 1200)
        logo = logo.resize((size, size), Image.LANCZOS)
        card.paste(logo, ((fmt.w - size) // 2, top), logo)
        d = ImageDraw.Draw(card)
        d.text((fmt.w // 2, url_y), "HARTRAILROAD.COM", font=fonts.get(118), fill=GOLD, anchor="mt")
        for k, line in enumerate(lines):
            d.text((fmt.w // 2, line_y + 75 * k), line,
                   font=fonts.get(54, heavy=False), fill=WHITE, anchor="mt")
        for _ in range(n):
            yield card
    return gen


def build_cut(fonts: Fonts, shots: Mapping[str, Path], fmt: Format) -> list[Segment]:
    """Empty room to railroad, then the panels and the site."""
    hook = "This room was empty."
    built = "…so I built a railroad in it"
    segs = [Segment(photo(fmt, "IMG_4038.jpg", zoom=(1.0, 1.06)), 1.8, hook)]
    segs += [Segment(photo(fmt, q.name, zoom=(1.04, 1.12), focus=q.focus), 0.6, built) for q in BUILD_QUICK]
    segs += [
        Segment(photo(fmt, "IMG_8904.jpg", zoom=(1.0, 1.12)), 2.6,
                "Neville Island in HO", kicker="Pittsburgh · Ohio River"),
        Segment(photo(fmt, "IMG_9288.jpg", zoom=(1.12, 1.0)), 2.2,
                "Real industries. Real car forwarding."),
        Segment(schematic(fmt), 4.0, "Every track drawn and numbered", caption_y=300),
        Segment(ctc_pan(fmt), 5.0, "Signals run from a CTC panel", caption_y=300),
        Segment(phone_scroll(fmt, shots["home"]), 5.0, "The whole story is online",
                caption_y=150),
        Segment(end_card(fonts, fmt), 3.0),
    ]
    return segs


def page_shot(fmt: Format, shot: Path, y0: int, y1: int, x0: int = 0, x1: int = 1080,
              tilt: float = 0.0, bg: str | None = None, area: tuple[int, int] = (540, 1820)) -> Frames:
    """One region of a page capture as a card: pops in, then creeps closer.

    y0..x1 are pixels in the 1080 px wide capture. Full-width regions show at
    960 px; narrower crops show at 1000 px, so they read as a zoom.
    """
    def gen(n: int) -> Iterator[Image.Image]:
        region = Image.open(shot).convert("RGB").crop((x0, y0, x1, y1))
        dw = 960 if x1 - x0 >= 1080 else 1000
        dh = round(region.height * dw / region.width)
        room = area[1] - area[0]
        if fmt.land:
            dw = min(dw, fmt.stage[2] - fmt.stage[0] - 80)
            dh = round(region.height * dw / region.width)
            room = fmt.stage[3] - fmt.stage[1] - 40
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
        base = backdrop(fmt, bg)
        cx, cy = fmt.centre() if fmt.land else (fmt.w // 2, (area[0] + area[1]) // 2)
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


def slam(fonts: Fonts, fmt: Format, word: str, count: str, bg: str | None) -> Frames:
    """Section title card: the name punches in over a gold rule."""
    def gen(n: int) -> Iterator[Image.Image]:
        base = backdrop(fmt, bg)
        for i in range(n):
            k = min(1.0, (i + 1) / 4)
            size = round(190 * (1.35 - 0.35 * (k * (2 - k))))
            frame = base.copy()
            d = ImageDraw.Draw(frame)
            font = fonts.get(size)
            lines = wrap(d, word.upper(), font, 980)
            y = fmt.h // 2 - len(lines) * size * 0.95 / 2
            d.text((fmt.w // 2, y - 90), count, font=fonts.get(64, heavy=False), fill=GOLD, anchor="mt")
            for line in lines:
                d.text((fmt.w // 2, y), line, font=font, fill=WHITE, anchor="mt")
                y += size * 0.95
            d.rectangle((fmt.w // 2 - 150, y + 30, fmt.w // 2 + 150, y + 42), fill=GOLD)
            yield frame
    return gen


def site_cut(fonts: Fonts, shots: Mapping[str, Path], fmt: Format) -> list[Segment]:
    """Rapid-fire tour of the site: the sections of SITE_SECTIONS, each a title slam then quick shots."""
    segs = [Segment(page_shot(fmt, shots["home"], 0, 1950, bg="IMG_8904.jpg"), 2.1,
                    "My model railroad has its own website", caption_y=150)]
    for k, sec in enumerate(SITE_SECTIONS, 1):
        segs.append(Segment(slam(fonts, fmt, sec.name, f"{k} / {len(SITE_SECTIONS)}", sec.backdrop), 0.7))
        for r in sec.regions:
            segs.append(Segment(page_shot(fmt, shots[r.page], r.y0, r.y1, r.x0, r.x1, r.tilt, sec.backdrop), 0.7,
                                sec.caption, kicker=sec.name, caption_y=150))
    segs.append(Segment(end_card(fonts, fmt, ("Prototype · Operations · Behind the Scenes",
                                         "The Diverging Route: AI in model railroading")),
                        3.5))
    return segs


# ---------------------------------------------------------------- Diverging Route cut

VO_DIR = OUT / "vo"  # voiceover.py writes media/promo/vo/<voice>/NN-key.wav + .json
VO_LINES = Path(__file__).resolve().parent / "diverging_vo.json"
VO_LEAD, VO_GAP, VO_TAIL = 0.35, 0.22, 2.2  # seconds before, between and after the lines


@dataclass
class VoLine:
    key: str
    wav: Path
    seconds: float
    words: list[dict]
    caption: str
    start: float = 0.0  # on the video timeline

    def at(self, word: str, after: float = 0.0) -> float:
        """Timeline second just before `word` is spoken (first match after `after`)."""
        want = word.lower()
        for w in self.words:
            if w["start"] + self.start >= after and \
                    w["w"].lower().strip(".,!?:;'\"") .startswith(want):
                return self.start + max(0.0, w["start"] - 0.08)
        raise PromoError(f"'{word}' not heard in {self.wav.name}; regenerate that line")


def vo_voices() -> list[str]:
    """The voices diverging_vo.json has an intro for (owner, generic)."""
    import json

    return list(json.loads(VO_LINES.read_text())["intro"])


def load_vo(voice: str) -> list[VoLine]:
    import json
    import wave

    data = json.loads(VO_LINES.read_text())
    spec = [("intro", data["intro"][voice]["caption"])]
    spec += [(ln["key"], ln["caption"]) for ln in data["lines"]]
    lines, t = [], VO_LEAD
    for k, (key, caption) in enumerate(spec):
        wav = VO_DIR / voice / f"{k:02d}-{key}.wav"
        if not wav.exists():
            raise PromoError(f"{wav} missing: run tools/promo/voiceover.py --voice {voice}")
        with wave.open(str(wav)) as w:
            secs = w.getnframes() / w.getframerate()
        words = json.loads(wav.with_suffix(".json").read_text())["words"]
        lines.append(VoLine(key, wav, secs, words, caption, start=t))
        t += secs + VO_GAP
    return lines


def timed(shots: Sequence[tuple[float, Frames, str, str]], end: float) -> list[Segment]:
    """(start second, frames, caption, kicker) shots, each running to the next start.

    Frame counts come from the cumulative timeline so the cuts never drift.
    """
    segs = []
    for i, (t0, gen, cap, kick) in enumerate(shots):
        t1 = shots[i + 1][0] if i + 1 < len(shots) else end
        f0, f1 = round(t0 * FPS), round(t1 * FPS)
        segs.append(Segment(gen, (f1 - f0) / FPS, cap, kicker=kick, caption_y=150))
    return segs


def route_card(fonts: Fonts, fmt: Format) -> Frames:
    """End card: the series name, where to find it, and the stay-tuned line."""
    def gen(n: int) -> Iterator[Image.Image]:
        card = Image.new("RGB", (fmt.w, fmt.h), BRAND)
        logo = Image.open(LOGO).convert("RGBA").resize((360, 360), Image.LANCZOS)
        card.paste(logo, ((fmt.w - 360) // 2, 300), logo)
        d = ImageDraw.Draw(card)
        d.text((fmt.w // 2, 760), "THE DIVERGING", font=fonts.get(150), fill=WHITE, anchor="mt")
        d.text((fmt.w // 2, 905), "ROUTE", font=fonts.get(150), fill=WHITE, anchor="mt")
        d.rectangle((fmt.w // 2 - 150, 1080, fmt.w // 2 + 150, 1092), fill=GOLD)
        d.text((fmt.w // 2, 1130), "AI in model railroading", font=fonts.get(60, heavy=False),
               fill=WHITE, anchor="mt")
        d.text((fmt.w // 2, 1250), "HARTRAILROAD.COM/AI", font=fonts.get(104), fill=GOLD, anchor="mt")
        d.text((fmt.w // 2, 1400), "Video series coming soon · stay tuned",
               font=fonts.get(54, heavy=False), fill=WHITE, anchor="mt")
        for i in range(n):
            k = min(1.0, (i + 1) / 5)
            if k < 1:  # quick settle from a slight zoom
                z = 1.06 - 0.06 * (k * (2 - k))
                im = card.resize((round(fmt.w * z), round(fmt.h * z)), Image.BICUBIC)
                x, y = (im.width - fmt.w) // 2, (im.height - fmt.h) // 2
                yield im.crop((x, y, x + fmt.w, y + fmt.h))
            else:
                yield card
    return gen


def diverging_cut(fonts: Fonts, shots: Mapping[str, Path], voice: str, fmt: Format) -> list[Segment]:
    """The Diverging Route series promo, cut to the voiceover's words."""
    L = {ln.key: ln for ln in load_vo(voice)}
    ai, ps = shots["ai"], functools.partial(page_shot, fmt)
    kick = "The Diverging Route"
    intro, title, switch = L["intro"], L["title"], L["switch"]
    hob, jobs, verdict, same, cta = L["hobbies"], L["jobs"], L["verdict"], L["same"], L["cta"]
    end = cta.start + cta.seconds + VO_TAIL
    sw, hb, sm = "Diverging route:", "Many hobbies in one", same.caption
    plan = [
        (0.0, photo(fmt, "IMG_8904.jpg", zoom=(1.0, 1.14)), intro.caption, ""),
        (intro.start + intro.seconds * 0.55, photo(fmt, "IMG_8947.jpg", zoom=(1.04, 1.16)), intro.caption, ""),
        (title.start, slam(fonts, fmt, "The Diverging Route", "A new series", "IMG_8904.jpg"), "", ""),
        (title.at("new"), ps(ai, 560, 1900, bg="IMG_9231.jpg"), title.caption, ""),
        (title.at("model"), photo(fmt, "IMG_8307.jpg", zoom=(1.05, 1.18)), title.caption, ""),
        (switch.start, photo(fmt, "IMG_9231.jpg", zoom=(1.0, 1.16), drift=(0.0, -0.04)),
         switch.caption, sw),
        (switch.at("other"), photo(fmt, "IMG_8070.jpg", zoom=(1.04, 1.16), focus=(0.4, 0.6)),
         switch.caption, sw),
        (switch.at("switch"), ps(ai, 700, 1800, 0, 700, tilt=-2, bg="IMG_9231.jpg"),
         switch.caption, sw),
        (switch.at("leaves"), photo(fmt, "IMG_7956.jpg", zoom=(1.04, 1.16)), switch.caption, sw),
        (switch.at("somewhere"), photo(fmt, "IMG_9231.jpg", zoom=(1.25, 1.4), focus=(0.4, 0.7)),
         switch.caption, sw),
        (hob.start, photo(fmt, "IMG_7915.jpg", zoom=(1.0, 1.1)), hb, ""),
        (hob.at("historian"), ps(shots["photos"], 1900, 3000, tilt=-2, bg="IMG_9231.jpg"),
         "Historian", hb),
        (hob.at("carpenter"), photo(fmt, "IMG_6653.jpg", zoom=(1.05, 1.15)), "Carpenter", hb),
        (hob.at("electrician"), photo(fmt, "IMG_7813.jpg", zoom=(1.05, 1.15)), "Electrician", hb),
        (hob.at("signal"), ctc_pan(fmt), "Signal engineer", hb),
        (hob.at("programmer"), photo(fmt, "IMG_7471.jpg", zoom=(1.05, 1.18)), "Programmer", hb),
        (jobs.start, ps(ai, 3880, 4460, bg="IMG_8904.jpg"), jobs.caption, kick),
        (jobs.at("every"), photo(fmt, "IMG_8120.jpg", zoom=(1.04, 1.14)), jobs.caption, kick),
        (jobs.at("research"), ps(shots["ai-research"], 250, 1350, bg="IMG_9231.jpg"),
         "The research", kick),
        (jobs.at("helix"), photo(fmt, "IMG_0883.jpg", zoom=(1.04, 1.16)), "The helix", kick),
        (jobs.at("wiring"), ps(shots["ai-electronics"], 250, 1350, tilt=-2, bg="IMG_7813.jpg"),
         "The wiring", kick),
        (jobs.at("signals"), ps(shots["signals"], 1600, 2550, bg="IMG_7813.jpg"),
         "The signals", kick),
        (jobs.at("paperwork"), ps(shots["cards"], 3360, 4440, 150, 930, tilt=3,
                                  bg="IMG_8904.jpg"), "The paperwork", kick),
        (jobs.at("speed"), ps(shots["speed-runs"], 2600, 3450, bg="IMG_9288.jpg"),
         "Even speed matching", kick),
        (verdict.start, ps(shots["ai-research"], 1840, 2420, bg="IMG_9288.jpg"),
         "What I asked", kick),
        (verdict.at("came"), ps(shots["ai-research"], 2600, 2940, tilt=-2, bg="IMG_9288.jpg"),
         "What came out", kick),
        (verdict.at("honest"), ps(shots["ai-research"], 2950, 3360, tilt=2, bg="IMG_9288.jpg"),
         "An honest verdict", kick),
        (same.start, photo(fmt, "IMG_9288.jpg", zoom=(1.0, 1.16)), sm, ""),
        (same.at("destination"), photo(fmt, "IMG_8904.jpg", zoom=(1.2, 1.35), focus=(0.5, 0.6)),
         sm, ""),
        (same.at("running"), photo(fmt, "IMG_8947.jpg", zoom=(1.1, 1.25)), "More time running trains",
         ""),
        (cta.start, phone_scroll(fmt, ai, travel=2600, start=0, bg="IMG_8904.jpg", hold=0.05),
         "Find it at hartrailroad.com", kick),
        (cta.at("stay"), route_card(fonts, fmt), "", ""),
    ]
    times = [p[0] for p in plan]
    if times != sorted(times):
        raise PromoError("voiceover word timings out of order; check the line JSON files")
    return timed(plan, end)


def write_voice_track(voice: str, seconds: float, path: Path) -> None:
    """All voiceover lines placed on the timeline, as one 48 kHz mono WAV."""
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import resample_poly

    sr = 48000
    buf = np.zeros(int(seconds * sr) + sr, dtype=np.float32)
    for ln in load_vo(voice):
        rate, x = wavfile.read(ln.wav)
        x = x.astype(np.float32) / (32768 if x.dtype == np.int16 else 1)
        x = resample_poly(x, sr, rate).astype(np.float32)
        i = int(ln.start * sr)
        buf[i:i + len(x)] += x[: len(buf) - i]
    wavfile.write(path, sr, buf[: int(seconds * sr)])


def add_voice(voice: str, video: Path, seconds: float, tmp: Path, music: bool) -> None:
    """Voiceover up front at -14 LUFS; with music, the bed ducks under the voice."""
    vo = tmp / "vo.wav"
    write_voice_track(voice, seconds, vo)
    inputs = ["-i", str(video), "-i", str(vo)]
    if music:
        import soundtrack

        beat = 0.6
        end_card = seconds - VO_TAIL - 1.0
        soundtrack.CUES["diverging"] = soundtrack.Cue(
            bpm=100, beats=int(seconds / beat) + 1,
            sections=[(0, 4, "intro"), (4, 8, "rise"), (8, int(end_card / beat), "full")],
            outro=end_card / beat)
        bed = tmp / "bed.wav"
        soundtrack.write("diverging", str(bed))
        inputs += ["-i", str(bed)]
        graph = ("[1:a]aresample=48000,pan=stereo|c0=c0|c1=c0,loudnorm=I=-16:TP=-2,"
                 "asplit=2[v][key];"
                 "[2:a]aresample=48000,volume=0.22[m];"
                 "[m][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=350[duck];"
                 f"[v][duck]amix=inputs=2:normalize=0:duration=first,"
                 f"afade=t=out:st={seconds - 0.6:.3f}:d=0.6,"
                 "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    else:
        graph = ("[1:a]aresample=48000,pan=stereo|c0=c0|c1=c0,"
                 "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    mixed = video.with_suffix(".vo.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph,
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(mixed)], check=True)
    mixed.replace(video)


# The cuts main() renders; diverging_cut also takes a voice, so main() calls it on its own.
CUTS: dict[str, Callable[[Fonts, Mapping[str, Path], Format], list[Segment]]] = {"build": build_cut, "site": site_cut}
CUT_NAMES = ("build", "site", "diverging")


def encoder_cmd(out: Path, fmt: Format) -> list[str]:
    """ffmpeg reading raw RGB frames on stdin and writing an H.264 MP4 with a silent audio track."""
    return ["ffmpeg", "-v", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{fmt.w}x{fmt.h}", "-r", str(FPS), "-i", "-",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k",
            str(out)]


def render(segs: Sequence[Segment], fonts: Fonts, out: Path, fmt: Format, cmd: Sequence[str] | None = None) -> None:
    """Draw every segment's frames, captions faded in, and pipe them to ffmpeg (`cmd`, encoder_cmd by default).
    PromoError, with ffmpeg's error output, when it fails. Its stderr is a file: a full pipe would stall it."""
    with tempfile.TemporaryFile() as errors:
        enc = subprocess.Popen(list(cmd or encoder_cmd(out, fmt)), stdin=subprocess.PIPE, stderr=errors)
        assert enc.stdin
        early = False
        try:
            _write_frames(segs, fonts, fmt, enc.stdin)
            enc.stdin.close()
        except BrokenPipeError:       # the encoder stopped reading before the last frame
            early = True
        code = enc.wait()
        errors.seek(0)
        said = errors.read().decode("utf-8", "replace").strip()
    if code or early:
        raise PromoError(f"ffmpeg failed ({f'exit {code}' if code else 'it stopped reading frames early'}) writing {out}"
                         + (f":\n{said}" if said else ""))
    if said:
        print(said, file=sys.stderr)


def _write_frames(segs: Sequence[Segment], fonts: Fonts, fmt: Format, sink: IO[bytes]) -> None:
    """Every frame of `segs`, its caption layer composited (faded in when the caption changes), to `sink`."""
    prev = None
    cache: dict[tuple, Image.Image] = {}
    for seg in segs:
        key = (seg.caption, seg.kicker, seg.caption_y)
        layer = None
        if seg.caption:
            layer = cache.get(key) or caption_layer(fonts, fmt, seg.caption, seg.kicker, seg.caption_y)
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
            sink.write(frame.tobytes())
        prev = key


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
    """Parse the arguments and render the cuts; a PromoError exits with its message."""
    try:
        _main()
    except PromoError as exc:
        raise SystemExit(f"tiktok_promo.py: {exc}") from exc


def _main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT, help="output directory (media/promo)")
    ap.add_argument("--font-dir", type=Path, default=FONTS,
                    help="folder with Barlow Condensed .ttf files (tools/promo/fonts)")
    ap.add_argument("--format", choices=("vertical", "landscape"), default="vertical",
                    help="vertical 1080x1920 (TikTok/Shorts) or landscape 1920x1080 (YouTube)")
    ap.add_argument("--cuts", default="build,site", help="comma list of: " + ", ".join(CUT_NAMES))
    ap.add_argument("--music", action="store_true",
                    help="mix in the cut's original soundtrack (soundtrack.py), -14 LUFS")
    ap.add_argument("--voice", default="owner,generic",
                    help="diverging cut: comma list of owner, generic (voiceover.py output)")
    ap.add_argument("--shots", type=Path, default=OUT / "shots",
                    help="folder for page captures; existing files are reused")
    args = ap.parse_args()
    cuts = args.cuts.split(",")
    unknown = [c for c in cuts if c not in CUT_NAMES]
    if unknown:
        ap.error(f"unknown cut(s): {', '.join(unknown)}; choose from {', '.join(CUT_NAMES)}")
    voices = [v.strip() for v in args.voice.split(",") if v.strip()]
    if "diverging" in cuts:
        bad = [v for v in voices if v not in vo_voices()]
        if bad or not voices:
            ap.error(f"unknown voice(s): {', '.join(bad) or '(none)'}; choose from {', '.join(vo_voices())}")
        if args.format == "landscape":
            # route_card and timed() place text for the 1080x1920 frame only.
            ap.error("the diverging cut is drawn for the vertical format only; drop --format landscape")
    if not shutil.which("ffmpeg"):
        raise PromoError("ffmpeg not found")
    args.out.mkdir(parents=True, exist_ok=True)
    fonts = Fonts(args.font_dir)
    fmt = FORMATS[args.format]
    suffix = "-youtube" if fmt.land else ""
    with tempfile.TemporaryDirectory() as tmp:
        shots = capture_pages(args.shots, set().union(*(CUT_PAGES[c] for c in cuts)))
        for cut in cuts:
            if cut == "diverging":
                for voice in voices:
                    out = args.out / f"hart-promo-diverging-{voice}{suffix}.mp4"
                    segs = diverging_cut(fonts, shots, voice, fmt)
                    render(segs, fonts, out, fmt)
                    add_voice(voice, out, sum(seg.n for seg in segs) / FPS, Path(tmp),
                              args.music)
                    print(out)
                continue
            out = args.out / f"hart-promo-{cut}{suffix}.mp4"
            segs = CUTS[cut](fonts, shots, fmt)
            render(segs, fonts, out, fmt)
            if args.music:
                add_music(cut, out, sum(seg.n for seg in segs) / FPS, Path(tmp))
            print(out)


if __name__ == "__main__":
    main()
