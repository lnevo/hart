"""publish_draft.py [--check]

Draw the system schematic with the schematic-maps plugin and publish it as the marked draft in docs/ops:
schematic-system-draft.svg (with a red DRAFT mark in the title block) and a Letter landscape PDF printed by
Chrome. Inputs: the layer files in jmri/layouts/hart/data/schematic/ and the plan graphs beside the owner's
AnyRail plan in ~/Documents/Layout/schematic/ (outside the repo). The plugin is the submodule
external/model-railroad-skills, or SCHEMATIC_PLUGIN=<plugin folder>.

--check draws and compares with the published SVG without writing anything (exit 1 if they differ).
After a commit that changes the drawing, run tools/schematic/evolution.py.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "jmri/layouts/hart/data/schematic"
GRAPHS = Path.home() / "Documents/Layout/schematic"
OUT = REPO / "docs/ops"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DRAFT = ('<text x="344" y="784" font-size="16" text-anchor="end" font-weight="bold" '
         'letter-spacing="3" fill="#c00">DRAFT</text>\n')


def plugin():
    env = os.environ.get("SCHEMATIC_PLUGIN")
    if env:
        return Path(env)
    for base in (REPO, REPO.parents[2] if ".claude" in REPO.parts else REPO):
        p = base / "external/model-railroad-skills/plugins/schematic-maps"
        if (p / "bin/schematic").exists():
            return p
    sys.exit("schematic-maps plugin not found; set SCHEMATIC_PLUGIN")


def mark(svg):
    """The drawing with the DRAFT mark added just before the end."""
    end = svg.rstrip().rfind("</svg>")
    if end < 0:
        raise ValueError("not an SVG")
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
        subprocess.run([CHROME, "--headless", "--disable-gpu", f"--user-data-dir={tmp}/profile",
                        "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", page.as_uri()],
                       capture_output=True, timeout=120, check=True)


def main(argv):
    sheet = draw()
    target = OUT / "schematic-system-draft.svg"
    if "--check" in argv:
        same = target.exists() and target.read_text() == sheet
        print("published draft is current" if same else "published draft differs from the drawing")
        return 0 if same else 1
    target.write_text(sheet)
    pdf(target, OUT / "schematic-system-draft.pdf")
    print(f"wrote {target} and the PDF")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
