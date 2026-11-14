"""publish_draft.py [--check]

Draw the system schematic with the schematic-maps plugin and publish it as the marked draft in docs/ops:
schematic-system-draft.svg (with a red DRAFT mark in the title block) and a Letter landscape PDF printed by
Chrome. Inputs: the layer files in jmri/layouts/hart/data/schematic/ and the plan graphs beside the owner's
AnyRail plan in ~/Documents/Layout/schematic/ (outside the repo). The plugin is this checkout's submodule
external/model-railroad-skills at its pinned commit (`git submodule update --init external/model-railroad-skills`
in a new worktree), or SCHEMATIC_PLUGIN=<plugin folder> for a trial of other plugin code.

--check draws and compares with the published SVG without writing anything (exit 1 if they differ). It also
fails if staging's measured track lengths (layer 1 `track_lengths_in`, used for car counts) no longer match
jmri/layouts/hart/data/block_lengths.csv; publishing copies them over first.
When the drawing itself (everything but the title block) differs from main's, publishing sets `date` to today and
`revision` to main's revision plus one in the page's preferences file, then draws again. Counting from main, not
from the last publish, keeps a branch that publishes several times at one revision. A revision that is not a
whole number is left alone. If anything fails after that, the preferences file is put back.
After a commit that changes the drawing, run tools/schematic/evolution.py.
"""
import csv
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths  # noqa: E402

REPO = paths.REPO_ROOT
DATA = REPO / "jmri/layouts/hart/data/schematic"
GRAPHS = Path.home() / "Documents/Layout/schematic"
OUT = REPO / "docs/ops"
LENGTHS = REPO / "jmri/layouts/hart/data/block_lengths.csv"
STAGING = DATA / "staging.plan_overrides.json"
INPUTS = [("staging.json", "staging"), ("main.json", "main_upper")]     # graph, layer file stem; the last sets the page
sys.path.insert(0, str(REPO / "tools/ops"))  # screenshot.py is a script, not a package: import it by folder
from screenshot import find_chrome  # noqa: E402

# the plugin's title box (it grows for a long title line); the DRAFT mark sits in its bottom right corner
TITLE_BOX = re.compile(r'<rect x="24" y="728" width="([\d.]+)" height="64"')
DRAFT = ('<text x="{x:g}" y="784" font-size="16" text-anchor="end" font-weight="bold" '
         'letter-spacing="3" fill="#c00">DRAFT</text>\n')


def page_prefs():
    """The preferences file that sets the page: sheet.preferences.json if present, else the last input's."""
    sheet = DATA / "sheet.preferences.json"
    return sheet if sheet.exists() else DATA / f"{INPUTS[-1][1]}.preferences.json"


def on_main(path):
    """The file's text where this branch left main (None if it was not there)."""
    git = lambda *a: subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)
    base = git("merge-base", "HEAD", "origin/main").stdout.strip() or "HEAD"
    r = git("show", f"{base}:{path.relative_to(REPO).as_posix()}")
    return r.stdout if r.returncode == 0 else None


def plugin():
    """The plugin folder: SCHEMATIC_PLUGIN, else this checkout's submodule at its pinned commit."""
    env = os.environ.get("SCHEMATIC_PLUGIN")
    if env:
        print(f"plugin: {env} (SCHEMATIC_PLUGIN)")
        return Path(env)
    sub = REPO / "external/model-railroad-skills"
    p = sub / "plugins/schematic-maps"
    if not (p / "bin/schematic").exists():
        sys.exit("schematic-maps plugin not found: run git submodule update --init external/model-railroad-skills")
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    have = git("-C", str(sub), "rev-parse", "HEAD")
    pinned = git("-C", str(REPO), "ls-files", "-s", "external/model-railroad-skills").split()[1]
    if have != pinned:
        sys.exit(f"submodule is at {have[:8]}, pinned {pinned[:8]}: run git submodule update, "
                 "or set SCHEMATIC_PLUGIN to draw with other plugin code on purpose")
    print(f"plugin: submodule at {have[:8]}")
    return p


def mark(svg):
    """The drawing with the DRAFT mark added just before the end."""
    end = svg.rstrip().rfind("</svg>")
    box = TITLE_BOX.search(svg)
    if end < 0 or not box:
        sys.exit("the plugin's title block moved; place the DRAFT mark again in publish_draft.py")
    return svg[:end] + DRAFT.format(x=24 + float(box.group(1)) - 10) + svg[end:].rstrip() + "\n"


def draw():
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "sheet.svg"
        run = subprocess.run([str(plugin() / "bin/schematic"), "draw", str(svg), "--data", str(DATA),
                              *(f"{GRAPHS}/{g}:{n}" for g, n in INPUTS)],
                             capture_output=True, text=True)
        print(run.stdout + run.stderr, end="")
        if run.returncode:
            sys.exit(run.returncode)
        return mark(svg.read_text())


def measured_lengths():
    """{track name: inches} for every Track row of block_lengths.csv."""
    with open(LENGTHS, newline="") as f:
        return {r["user_name"][len("Track "):]: float(r["inches"]) for r in csv.DictReader(f)
                if r["user_name"].startswith("Track ") and r["inches"]}


def lengths_current():
    return json.loads(STAGING.read_text()).get("track_lengths_in") == measured_lengths()


def copy_lengths():
    over = json.loads(STAGING.read_text())
    over["track_lengths_in"] = measured_lengths()
    STAGING.write_text(json.dumps(over, indent=1, ensure_ascii=False) + "\n")


def drawing_only(svg):
    """The sheet up to the title block (which the plugin draws last), to tell a real drawing change."""
    box = TITLE_BOX.search(svg)
    return svg[:box.start()] if box else svg


def next_fields(main_prefs, today):
    """(date, revision) for a changed drawing: today and main's revision plus one; None if that revision
    is not a whole number (a lettered revision is the owner's to set)."""
    rev = json.loads(main_prefs).get("revision", 0) if main_prefs else 0
    if isinstance(rev, bool) or not str(rev).strip().isdigit():
        return None
    return today.isoformat(), int(rev) + 1


def set_fields(path, date, rev):
    prefs = json.loads(path.read_text())
    prefs["date"], prefs["revision"] = date, rev
    path.write_text(json.dumps(prefs, indent=1, ensure_ascii=False) + "\n")


def pdf(svg_path, pdf_path):
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text("<!doctype html><style>@page{size:11in 8.5in;margin:0}html,body{margin:0}"
                        "img{width:11in;height:8.5in;display:block}</style>"
                        f'<img src="{svg_path.resolve().as_uri()}">')
        subprocess.run([find_chrome(), "--headless", "--disable-gpu", f"--user-data-dir={tmp}/profile",
                        "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", page.as_uri()],
                       capture_output=True, timeout=120, check=True)


def main(argv):
    target = OUT / "schematic-system-draft.svg"
    if "--check" in argv and not lengths_current():
        print(f"{STAGING.name}: track_lengths_in differs from {LENGTHS.name}; run publish_draft.py to copy them")
        return 1
    if "--check" not in argv and not lengths_current():
        copy_lengths()
        print(f"copied the measured track lengths into {STAGING.name}")
    sheet = draw()
    if "--check" in argv:
        same = target.exists() and target.read_text() == sheet
        print("published draft is current" if same else "published draft differs from the drawing")
        return 0 if same else 1
    prefs = page_prefs()
    original = prefs.read_text()
    try:
        publish(sheet, target, prefs, original)
    except BaseException:
        if prefs.read_text() != original:
            prefs.write_text(original)
            print(f"put back {prefs.name}")
        raise
    return 0


def publish(sheet, target, prefs, original):
    base = on_main(target) or (target.read_text() if target.exists() else None)
    if base and drawing_only(base) != drawing_only(sheet):
        fields = next_fields(on_main(prefs), datetime.date.today())
        now = json.loads(original)
        if fields is None:
            print(f"drawing changed; revision {now.get('revision')!r} is not a number, so date and revision are left as set")
        elif (now.get("date"), now.get("revision")) != fields:
            set_fields(prefs, *fields)
            print(f"drawing changed: title block set to {fields[0]}, revision {fields[1]}")
            sheet = draw()
    with tempfile.TemporaryDirectory() as tmp:
        svg, printed = Path(tmp) / target.name, Path(tmp) / "sheet.pdf"
        svg.write_text(sheet)
        try:
            pdf(svg, printed)
        except (subprocess.SubprocessError, OSError) as e:
            sys.exit(f"PDF not printed, nothing written: {e}")
        if not printed.exists():
            sys.exit("Chrome wrote no PDF, nothing written")
        shutil.copyfile(svg, target)
        shutil.copyfile(printed, OUT / "schematic-system-draft.pdf")
    print(f"wrote {target} and the PDF (--check compares the SVG only; the PDF follows it)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
