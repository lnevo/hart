#!/usr/bin/env python3
"""Render a vertical (1080x1920) promo video for TikTok, Reels and Shorts.

    .venv/bin/python tools/promo/tiktok_promo.py --font-dir <dir> --out <dir>

Builds the cut from material already in the repo: layout photos from
media/photos-layout (the gitignored mirror), the schematic and USS CTC
evolution videos in www/assets/behind/panel-evolution, and a phone-width
capture of the live home page (taken with headless Chrome). Every frame is
drawn with Pillow and piped to ffmpeg, so this ffmpeg build needs no
drawtext. One video is written per opening caption in HOOKS, so the openings
can be tested against each other.

The output has a silent audio track. Add music from TikTok's own sound library
when posting; do not bake in commercial music.

--font-dir must hold BarlowCondensed-ExtraBold.ttf and -SemiBold.ttf (the
site's display face, OFL, from github.com/google/fonts ofl/barlowcondensed).
Without them the script falls back to Avenir Next Condensed.
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
SITE_URL = "https://www.hartrailroad.com/"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

W, H, FPS = 1080, 1920, 30
BRAND = (11, 52, 62)  # dark teal of the site footer band
GOLD = (240, 192, 85)  # --accent-on-dark
WHITE = (255, 255, 255)

# Opening caption over the empty room; one video per entry.
HOOKS = {
    "a": "This room was empty.",
    "b": "POV: a model railroader gets an empty room",
    "c": "Watch an empty room become a railroad",
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
    """Caption on a dark band, kept out of TikTok's top bar and bottom/right UI."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
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
    fw, fh = 1040, 800
    vf = (f"setpts=PTS/{speed:.4f},fps={FPS},crop=1372:1058:14:11,"
          f"scale={fw}:{fh}:flags=lanczos")
    frames = list(video_frames(src, vf, (fw, fh)))
    last = frames[-1] if frames else Image.new("RGB", (fw, fh), WHITE)
    for i in range(n):
        im = frames[i] if i < len(frames) else last
        canvas = Image.new("RGB", (W, H), WHITE)
        canvas.paste(im, ((W - fw) // 2, 700))
        yield canvas


def ctc_pan(n: int) -> Iterator[Image.Image]:
    """Pan across the USS CTC machine while its last changes come in."""
    src = EVOLUTION / "uss-panel-evolution.mp4"
    ph = 1120
    pw = round(1200 * ph / 652)
    vf = f"fps={FPS},crop=1200:652:0:62,scale={pw}:{ph}:flags=lanczos"
    frames = list(video_frames(src, vf, (pw, ph), start=19.0))
    bg = (34, 34, 42)
    for i in range(n):
        t = i / max(n - 1, 1)
        t = t * t * (3 - 2 * t)
        im = frames[min(len(frames) - 1, int(i * len(frames) / n))]
        x = int((pw - W) * t)
        canvas = Image.new("RGB", (W, H), bg)
        canvas.paste(im.crop((x, 0, x + W, ph)), (0, 620))
        yield canvas


def site_scroll(shot: Path):
    def gen(n: int) -> Iterator[Image.Image]:
        page = Image.open(shot).convert("RGB")
        # Phone frame: page in a rounded card on the brand colour.
        sw, sh = 900, 1500
        page = page.resize((sw, round(page.height * sw / page.width)), Image.LANCZOS)
        travel = min(page.height - sh, 3300)
        mask = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw, sh), radius=48, fill=255)
        bg = Image.new("RGB", (W, H), BRAND)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            ((W - sw) // 2 - 6, 420, (W + sw) // 2 + 6, 420 + sh + 18), radius=54,
            fill=(0, 0, 0, 140))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        bg.paste(shadow, (0, 0), shadow)
        hold = int(n * 0.12)
        for i in range(n):
            t = max(0.0, (i - hold) / max(n - 1 - hold, 1))
            t = t * t * (3 - 2 * t)
            y = int(travel * t)
            frame = bg.copy()
            frame.paste(page.crop((0, y, sw, y + sh)), ((W - sw) // 2, 410), mask)
            yield frame
    return gen


def end_card(fonts: Fonts):
    def gen(n: int) -> Iterator[Image.Image]:
        card = Image.new("RGB", (W, H), BRAND)
        logo = Image.open(LOGO).convert("RGBA")
        logo = logo.resize((560, 560), Image.LANCZOS)
        card.paste(logo, ((W - 560) // 2, 420), logo)
        d = ImageDraw.Draw(card)
        d.text((W // 2, 1060), "HARTRAILROAD.COM", font=fonts.get(118), fill=GOLD, anchor="mt")
        d.text((W // 2, 1200), "Neville Island, Pittsburgh · HO scale",
               font=fonts.get(54, heavy=False), fill=WHITE, anchor="mt")
        d.text((W // 2, 1275), "Follow along as it gets built",
               font=fonts.get(54, heavy=False), fill=WHITE, anchor="mt")
        for _ in range(n):
            yield card
    return gen


def build(fonts: Fonts, hook: str, shot: Path) -> list[Segment]:
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
        Segment(site_scroll(shot), 5.0, "The whole story is online", caption_y=150),
        Segment(end_card(fonts), 3.0),
    ]
    return segs


# ---------------------------------------------------------------- render

def capture_site(out: Path) -> Path:
    """Phone-width capture of the live home page.

    Headless Chrome on macOS lays out no narrower than about 500 CSS px, so a
    390 px window clips the page; 500 px at 2.16x gives a clean 1080 px image.
    """
    shot = out / "site-phone.png"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2.16", "--window-size=500,3000",
                    f"--screenshot={shot}", SITE_URL],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return shot


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="output directory")
    ap.add_argument("--font-dir", type=Path, help="folder with Barlow Condensed .ttf files")
    ap.add_argument("--hooks", default="".join(HOOKS), help="which openings to render, e.g. ab")
    ap.add_argument("--site-shot", type=Path, help="reuse a 1080 px wide home page capture")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found")
    args.out.mkdir(parents=True, exist_ok=True)
    fonts = Fonts(args.font_dir)
    with tempfile.TemporaryDirectory() as tmp:
        shot = args.site_shot or capture_site(Path(tmp))
        for h in args.hooks:
            out = args.out / f"hart-promo-{h}.mp4"
            render(build(fonts, HOOKS[h], shot), fonts, out)
            print(out)


if __name__ == "__main__":
    main()
