"""evolution.py [--site | --check] [output folder]

Keep a folder of every committed version of the schematic sample drawings and an animated GIF of them.

Reads the versions from git history, so it can be re-run after every commit: the stage 0 samples from the
closed spike branch (origin/agent/claude/schematic-spike), then every committed change of the published
draft, docs/ops/schematic-system-draft.svg, after the spike copies (commit 60ce2ef3). The current branch's
history is read, so run it from the branch that has the drawing commit:
frames that already exist are kept, new ones are added, and the GIF is rebuilt. macOS only (renders
the SVG with Chrome, or sips without it); needs Pillow, which the repo's root .venv has:

    .venv/bin/python tools/schematic/evolution.py

Default folder: ~/Documents/Layout/schematic-evolution (outside the repo; frames are large).

--site also makes the copy the website shows, after the frames are up to date: schematic-evolution.mp4 (H.264,
yuv420p, faststart, 30 seconds long however many versions there are, the last frame held 2 s) and schematic-poster.jpg (the last frame) in
www/assets/behind/panel-evolution/, and it sets the version count and dates in the caption and aria-label of
www/behind/panel-evolution.html (the spans marked data-film, and the count in words). It needs ffmpeg and stops
with a message without it.

--check renders nothing: it counts the versions in git history (the same list the frames come from) and exits 1
when the page's count or dates differ, that is when the site film is behind the drawing. It needs the spike ref
(origin/agent/claude/schematic-spike), so it is a manual check, not part of tools/check.sh (CI clones lack the ref).
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=HERE, capture_output=True,
                           text=True, check=True).stdout.strip())
SPIKE = "tools/schematic/spike"
SPIKE_REF = "origin/agent/claude/schematic-spike"
DRAFT = "docs/ops/schematic-system-draft.svg"
DRAFT_FROM = "60ce2ef3"  # the draft's first two commits are copies of spike samples already shown
# the drawing that best shows the state at a commit, most complete first
PRIORITY = ["signals_sample.svg", "system_sample.svg", "main_asbuilt_sample.svg", "staging_sample.svg", "built_sample.svg"]
WIDTH = 1400
STEP_MS, HOLD_MS = 1600, 5000  # the GIF: each version's time on screen, and the last version's
FILM_S, FILM_HOLD_S = 30.0, 2.0  # the site film always runs FILM_S seconds, however many versions there are
SITE = REPO / "www/assets/behind/panel-evolution"
PAGE = REPO / "www/behind/panel-evolution.html"
MP4, POSTER = "schematic-evolution.mp4", "schematic-poster.jpg"


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def versions():
    """(hash, time, subject, file) for each commit that changed a sample drawing, oldest first."""
    try:
        log = git("log", "--reverse", "--format=@%h|%ad|%s", "--date=format:%Y-%m-%d %H:%M", "--name-only",
                  SPIKE_REF, "--", f"{SPIKE}/*_sample.svg")
    except subprocess.CalledProcessError:
        sys.exit(f"{SPIKE_REF} not found: run git fetch origin agent/claude/schematic-spike "
                 "(the spike's frames number the folder, so they must come first)")
    out, head, files = [], None, []
    for line in log.splitlines() + ["@"]:
        if line.startswith("@"):
            if head:
                pick = next((f"{SPIKE}/{p}" for p in PRIORITY if f"{SPIKE}/{p}" in files), None)
                if pick:
                    out.append((*head, pick))
            head, files = (line[1:].split("|", 2) if "|" in line else None), []
        elif line.strip():
            files.append(line.strip())
    log = git("log", "--reverse", "--format=%h|%ad|%s", "--date=format:%Y-%m-%d %H:%M",
              f"{DRAFT_FROM}..HEAD", "--", DRAFT)
    out += [(*line.split("|", 2), DRAFT) for line in log.splitlines() if line.strip()]
    return out


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def render(svg, png):
    from PIL import Image
    """The whole sheet as an image: Chrome when it is installed (sharp, twice the size), else sips."""
    if Path(CHROME).exists():
        with tempfile.TemporaryDirectory() as tmp:
            shot = Path(tmp) / "shot.png"
            subprocess.run([CHROME, "--headless", "--disable-gpu", f"--user-data-dir={tmp}/profile",
                            f"--screenshot={shot}", "--window-size=1056,816", "--force-device-scale-factor=2",
                            "--hide-scrollbars", svg.resolve().as_uri()], capture_output=True, timeout=120)
            if shot.exists():
                Image.open(shot).convert("RGB").save(png)
                return
    subprocess.run(["sips", "-s", "format", "png", str(svg), "--out", str(png)], capture_output=True, check=True)
    flat = Image.new("RGB", Image.open(png).size, "white")
    flat.paste(Image.open(png).convert("RGBA"), mask=Image.open(png).convert("RGBA").split()[3])
    flat.save(png)


def frame(png, caption):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(png).convert("RGB")
    img = img.resize((WIDTH, round(img.height * WIDTH / img.width)))
    strip = 44
    canvas = Image.new("RGB", (WIDTH, img.height + strip), "white")
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, img.height, WIDTH, img.height + strip], fill="#222222")
    draw.text((14, img.height + 11), caption, fill="white", font=ImageFont.load_default(size=20))
    return canvas


ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "\
       "seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
MONTHS = "January February March April May June July August September October November December".split()


def film_durations(n):
    """Seconds on screen for each of n versions: the last held FILM_HOLD_S, the rest sharing the remainder."""
    if n < 2:
        raise ValueError(f"{n} version: the film needs at least two")
    step = round((FILM_S - FILM_HOLD_S) / (n - 1), 4)
    return [step] * (n - 1) + [round(FILM_S - step * (n - 1), 4)]


def words(n):
    """1 to 99 in words: 38 is thirty-eight."""
    if not 1 <= n <= 99:
        raise ValueError(f"{n} versions: words() covers 1 to 99, extend it")
    return ONES[n] if n < 20 else TENS[n // 10] + (f"-{ONES[n % 10]}" if n % 10 else "")


def day(when, year):
    """'2026-11-14 09:30' as '14 November' (with the year when asked)."""
    y, m, d = when.split()[0].split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]}" + (f" {y}" if year else "")


def page_values(todo):
    """What the page must say for these versions: (count, first day, last day with year, count in words)."""
    return len(todo), day(todo[0][1], False), day(todo[-1][1], True), words(len(todo))


SPAN = '<span data-film="{}">{}</span>'
SPAN_RE = '<span data-film="{}">([^<]*)</span>'
ARIA_RE = r'(aria-label=")([A-Za-z-]+)( versions of the system schematic)'


def page_text(html, values):
    """The page with the count, dates and count in words set. Raises when a marker is missing."""
    count, first, last, spelled = values
    for name, val in (("count", count), ("first", first), ("last", last)):
        html, n = re.subn(SPAN_RE.format(name), SPAN.format(name, val), html)
        if n != 1:
            raise ValueError(f'{PAGE.name}: expected one <span data-film="{name}">, found {n}')
    html, n = re.subn(ARIA_RE, lambda m: m[1] + spelled.capitalize() + m[3], html)
    if n != 1:
        raise ValueError(f"{PAGE.name}: expected one aria-label '... versions of the system schematic', found {n}")
    return html


def page_drift(html, values):
    """The statements on the page that differ from these versions, as text; empty when it is current."""
    count, first, last, spelled = values
    out = []
    for name, val in (("count", count), ("first", first), ("last", last)):
        found = re.findall(SPAN_RE.format(name), html)
        if len(found) != 1:
            out.append(f'expected one <span data-film="{name}">, found {len(found)}')
        elif found[0] != str(val):
            out.append(f"{name} says {found[0]}, git history has {val}")
    aria = re.findall(ARIA_RE, html)
    if len(aria) != 1:
        out.append(f"expected one aria-label count, found {len(aria)}")
    elif aria[0][1].lower() != spelled:
        out.append(f"aria-label says {aria[0][1].lower()}, git history has {spelled}")
    return out


def check():
    drift = page_drift(PAGE.read_text(), page_values(versions()))
    if drift:
        print(f"{PAGE.relative_to(REPO)} is behind the drawing: " + "; ".join(drift) + "; run evolution.py --site")
        return 1
    print(f"{PAGE.name} matches git history")
    return 0


def site(frames, todo, out=SITE):
    """The site's film and poster from the finished frames, and the page text. Stops without ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg not found: install it (brew install ffmpeg), --site makes the mp4 with it")
    if frames[0].height % 2 or frames[0].width % 2:
        sys.exit(f"frame size {frames[0].width}x{frames[0].height} is odd, yuv420p needs even sides")
    if not out.is_dir():
        sys.exit(f"{out} not found")
    with tempfile.TemporaryDirectory() as tmp:
        lines = []
        secs = film_durations(len(frames))
        for i, f in enumerate(frames):
            f.save(Path(tmp) / f"{i:03d}.png")
            lines += [f"file '{i:03d}.png'", f"duration {secs[i] - (0.04 if i == len(frames) - 1 else 0)}"]
        # the concat demuxer ignores the last duration unless a file follows: repeat the last frame for one tick
        lines += [f"file '{len(frames) - 1:03d}.png'", "duration 0.04"]
        # fps=25 makes a steady-rate film: a variable-rate one reports a shorter length and browsers cut its hold
        (Path(tmp) / "list.txt").write_text("\n".join(lines) + "\n")
        film = Path(tmp) / MP4
        run = subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "concat", "-i", "list.txt", "-vf", "fps=25", "-t", str(FILM_S),
                              "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p",
                              "-movflags", "+faststart", MP4], cwd=tmp, capture_output=True, text=True)
        if run.returncode or not film.exists():
            sys.exit(f"ffmpeg failed: {run.stderr.strip()}")
        shutil.copyfile(film, out / MP4)
    frames[-1].save(out / POSTER, quality=85, optimize=True)
    PAGE.write_text(page_text(PAGE.read_text(), page_values(todo)))
    print(f"site copy: {out / MP4} ({(out / MP4).stat().st_size // 1024} KB), {out / POSTER}, {PAGE.relative_to(REPO)}")


def main(folder, with_site=False):
    from PIL import Image
    if with_site and not shutil.which("ffmpeg"):  # before the slow renders
        sys.exit("ffmpeg not found: install it (brew install ffmpeg), --site makes the mp4 with it")
    folder.mkdir(parents=True, exist_ok=True)
    todo = versions()
    if not todo:
        sys.exit("no committed drawings found")
    frames = []
    for i, (h, when, subject, name) in enumerate(todo, 1):
        svg, png = folder / f"{i:03d}_{h}.svg", folder / f"{i:03d}_{h}.png"
        if not svg.exists():
            svg.write_text(git("show", f"{h}:{name}"))
        if not png.exists():
            render(svg, png)
        short = subject if len(subject) < 105 else subject[:102] + "..."
        frames.append(frame(png, f"{i}/{len(todo)}   {when}   {short}"))
    height = max(f.height for f in frames)
    frames = [f if f.height == height else ImageOpsPad(f, height) for f in frames]
    gif = folder / "evolution.gif"
    durations = [STEP_MS] * (len(frames) - 1) + [HOLD_MS]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print(f"{len(frames)} versions in {folder}; animation: {gif}")
    if with_site:
        site(frames, todo)


def ImageOpsPad(img, height):
    from PIL import Image
    canvas = Image.new("RGB", (img.width, height), "white")
    canvas.paste(img, (0, 0))
    return canvas


if __name__ == "__main__":
    args = sys.argv[1:]
    flags = [a for a in args if a.startswith("--")]
    rest = [a for a in args if not a.startswith("--")]
    if set(flags) - {"--site", "--check"} or len(rest) > 1 or (flags == ["--check"] and rest) or len(flags) > 1:
        sys.exit(__doc__.split("\n\n")[0])
    if flags == ["--check"]:
        sys.exit(check())
    main(Path(rest[0]).expanduser() if rest else Path.home() / "Documents/Layout/schematic-evolution", flags == ["--site"])
