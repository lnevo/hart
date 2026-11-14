"""publish_draft.py [--check]

Draw the system schematic with the schematic-maps plugin and publish it as the marked draft in docs/ops:
schematic-system-draft.svg (with a red DRAFT mark in the title block) and a Letter landscape PDF printed by
Chrome. Inputs: the layer files in jmri/layouts/hart/data/schematic/ and the plan graphs beside the owner's
AnyRail plan in ~/Documents/Layout/schematic/ (outside the repo). The plugin is this checkout's submodule
external/model-railroad-skills at its pinned commit (`git submodule update --init external/model-railroad-skills`
in a new worktree), or SCHEMATIC_PLUGIN=<plugin folder> for a trial of other plugin code.

--check draws and compares with the published SVG without writing anything (exit 1 if they differ).
After a commit that changes the drawing, run tools/schematic/evolution.py.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "jmri/layouts/hart/data/schematic"
GRAPHS = Path.home() / "Documents/Layout/schematic"
OUT = REPO / "docs/ops"
sys.path.insert(0, str(REPO / "tools/ops"))
from screenshot import find_chrome  # noqa: E402

# the plugin's title block; the DRAFT mark sits in its bottom right corner
TITLE_BOX = '<rect x="24" y="728" width="330" height="64"'
DRAFT = ('<text x="344" y="784" font-size="16" text-anchor="end" font-weight="bold" '
         'letter-spacing="3" fill="#c00">DRAFT</text>\n')


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
    if end < 0 or TITLE_BOX not in svg:
        sys.exit("the plugin's title block moved; place the DRAFT mark again in publish_draft.py")
    return svg[:end] + DRAFT + svg[end:].rstrip() + "\n"


def draw():
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "sheet.svg"
        run = subprocess.run([str(plugin() / "bin/schematic"), "draw", str(svg), "--data", str(DATA),
                              f"{GRAPHS}/staging.json:staging", f"{GRAPHS}/main.json:main_upper"],
                             capture_output=True, text=True)
        print(run.stdout + run.stderr, end="")
        if run.returncode:
            sys.exit(run.returncode)
        return mark(svg.read_text())


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
    sheet = draw()
    target = OUT / "schematic-system-draft.svg"
    if "--check" in argv:
        same = target.exists() and target.read_text() == sheet
        print("published draft is current" if same else "published draft differs from the drawing")
        return 0 if same else 1
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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
