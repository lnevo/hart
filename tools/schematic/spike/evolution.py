"""evolution.py [output folder]

Keep a folder of every committed version of the schematic sample drawings and an animated GIF of them.

Reads the versions from git history (this checkout's branch), so it can be re-run after every commit:
frames that already exist are kept, new ones are added, and the GIF is rebuilt. macOS only (renders
the SVG with Chrome, or sips without it); needs Pillow, which the repo's root .venv has:

    .venv/bin/python tools/schematic/spike/evolution.py

Default folder: ~/Documents/Layout/schematic-evolution (outside the repo; frames are large).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=HERE, capture_output=True,
                           text=True, check=True).stdout.strip())
SPIKE = HERE.relative_to(REPO).as_posix()
# the drawing that best shows the state at a commit, most complete first
PRIORITY = ["system_sample.svg", "main_asbuilt_sample.svg", "staging_sample.svg", "built_sample.svg"]
WIDTH = 1400


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def versions():
    """(hash, time, subject, file) for each commit that changed a sample drawing, oldest first."""
    log = git("log", "--reverse", "--format=@%h|%ad|%s", "--date=format:%Y-%m-%d %H:%M", "--name-only",
              "--", f"{SPIKE}/*_sample.svg")
    out, head, files = [], None, []
    for line in log.splitlines() + ["@"]:
        if line.startswith("@"):
            if head:
                pick = next((p for p in PRIORITY if f"{SPIKE}/{p}" in files), None)
                if pick:
                    out.append((*head, pick))
            head, files = (line[1:].split("|", 2) if "|" in line else None), []
        elif line.strip():
            files.append(line.strip())
    return out


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def render(svg, png):
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
    img = Image.open(png).convert("RGB")
    img = img.resize((WIDTH, round(img.height * WIDTH / img.width)))
    strip = 44
    canvas = Image.new("RGB", (WIDTH, img.height + strip), "white")
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, img.height, WIDTH, img.height + strip], fill="#222222")
    draw.text((14, img.height + 11), caption, fill="white", font=ImageFont.load_default(size=20))
    return canvas


def main(folder):
    folder.mkdir(parents=True, exist_ok=True)
    todo = versions()
    frames = []
    for i, (h, when, subject, name) in enumerate(todo, 1):
        svg, png = folder / f"{i:03d}_{h}.svg", folder / f"{i:03d}_{h}.png"
        if not svg.exists():
            svg.write_text(git("show", f"{h}:{SPIKE}/{name}"))
        if not png.exists():
            render(svg, png)
        short = subject if len(subject) < 105 else subject[:102] + "..."
        frames.append(frame(png, f"{i}/{len(todo)}   {when}   {short}"))
    height = max(f.height for f in frames)
    frames = [f if f.height == height else ImageOpsPad(f, height) for f in frames]
    gif = folder / "evolution.gif"
    durations = [1600] * (len(frames) - 1) + [5000]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True)
    print(f"{len(frames)} versions in {folder}; animation: {gif}")


def ImageOpsPad(img, height):
    canvas = Image.new("RGB", (img.width, height), "white")
    canvas.paste(img, (0, 0))
    return canvas


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "Documents/Layout/schematic-evolution")
