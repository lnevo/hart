"""publish_draft.py [--check | --preview DIR]

Draw the system schematic with the schematic-maps plugin and publish it in docs/ops:
schematic-system-draft.svg (the file keeps its name; the DRAFT mark came off when the owner approved the helix-join
release, 2026-11-17) and a Letter landscape PDF printed by
Chrome, and one SVG per station detail sheet (the `detail_sheets` preference) in docs/ops/stations/. Inputs: the layer files in jmri/layouts/hart/data/schematic/ and the plan graphs in its inputs/ folder
(track only, regenerated from the owner's AnyRail export as its README says). The plugin is this checkout's submodule
external/model-railroad-skills at its pinned commit (`git submodule update --init external/model-railroad-skills`
in a new worktree), or SCHEMATIC_PLUGIN=<plugin folder> for a trial of other plugin code.

--check draws and compares with the published SVG and the station sheets without writing anything (exit 1 if
any differ). It also
fails if staging's measured track lengths (layer 1 `track_lengths_in`, used for car counts) no longer match
jmri/layouts/hart/data/block_lengths.csv; publishing copies them over first.
--preview DIR draws the SVG and its PDF into DIR for the owner to look at; docs/ops, the layer files and the
title block's date and revision are left alone.
When the drawing itself (everything but the title block), or a station sheet's, differs from main's, publishing sets `date` to today and
`revision` to main's revision plus one in the page's preferences file, then draws again. Counting from main, not
from the last publish, keeps a branch that publishes several times at one revision. A revision that is not a
whole number is left alone. If anything fails after that, the preferences file is put back.
The station map pages are drawn from this sheet, so publishing then copies the title block's revision and date to
them with www/scripts/map_revision.py, and --check fails while any of them differs.
After a commit that changes the drawing, run tools/schematic/evolution.py.

The plugin's solved-sheet cache (SCHEMATIC_CACHE, default ~/.cache/hart/schematic, a folder only this user can open)
is on for the plugin commands this runs and for solved_sheet(), the one way build_layout_le.py, build_cats_panel.py
and build_device_map.py get the solved bands, so they and publishing solve the same inputs once between them. The
key covers the source of the plugin code the solve runs, the graphs and the layer files, so a SCHEMATIC_PLUGIN trial
or an edited layer file solves again; a change to the title block's date, revision or sheet alone does not (the
plugin draws the cached page again with them). build_layout_le.py also keeps its Layout Editor panels and their fit
grids there (cache_on). SCHEMATIC_CACHE= (empty) turns it off, as must any test that patches plugin code. tools/check.sh sets it
to the same folder for every job, the unit tests included.
"""
import contextlib
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
from hartlib import paths, railroad  # noqa: E402

REPO = paths.REPO_ROOT
CACHE = Path.home() / ".cache/hart/schematic"
DATA = REPO / "jmri/layouts/hart/data/schematic"
GRAPHS = DATA / "inputs"
OUT = REPO / "docs/ops"
STATIONS = OUT / "stations"                                              # one SVG per station detail sheet
LENGTHS = railroad.Sources.under().block_lengths
STAGING = DATA / "staging.plan_overrides.json"
INPUTS = [("staging.json", "staging"), ("main.json", "main_upper")]     # graph, layer file stem; the last sets the page
sys.path.insert(0, str(REPO / "tools/ops"))  # screenshot.py is a script, not a package: import it by folder
from screenshot import find_chrome  # noqa: E402
sys.path.insert(0, str(REPO / "www/scripts"))
import map_revision  # noqa: E402

# the plugin's title box (it grows for a long title line), drawn after the drawing itself
TITLE_BOX = re.compile(r'<rect x="24" y="728" width="([\d.]+)" height="64"')


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


def cache_env():
    """os.environ with SCHEMATIC_CACHE set to CACHE (made private to this user) unless the caller set it, even to
    empty (off)."""
    env = dict(os.environ)
    if "SCHEMATIC_CACHE" not in env:
        CACHE.mkdir(parents=True, exist_ok=True)
        CACHE.chmod(0o700)                       # the plugin unpickles what is in it: nobody else may write there
        env["SCHEMATIC_CACHE"] = str(CACHE)
    return env


@contextlib.contextmanager
def cache_on():
    """The plugin's cache on (cache_env) for the code inside, in this process; the variable as it was afterwards."""
    old = os.environ.get("SCHEMATIC_CACHE")
    os.environ["SCHEMATIC_CACHE"] = cache_env()["SCHEMATIC_CACHE"]
    try:
        yield
    finally:
        if old is None:
            del os.environ["SCHEMATIC_CACHE"]
        else:
            os.environ["SCHEMATIC_CACHE"] = old


def solved_sheet(sheet):
    """The solved Sheet of the schematic (INPUTS from GRAPHS, layer files in DATA), from the plugin's `sheet` module,
    through the cache. Every builder gets its bands here, so they share one cache key with publishing."""
    with cache_on():
        return sheet.build([(str(GRAPHS / g), n) for g, n in INPUTS], str(DATA))


def draw():
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "sheet.svg"
        run = subprocess.run([str(plugin() / "bin/schematic"), "draw", str(svg), "--data", str(DATA),
                              *(f"{GRAPHS}/{g}:{n}" for g, n in INPUTS)],
                             capture_output=True, text=True, env=cache_env())
        print(run.stdout + run.stderr, end="")
        if run.returncode:
            sys.exit(run.returncode)
        return svg.read_text()


def draw_stations():
    """{file name: SVG} of every station detail sheet (the detail_sheets preference), drawn from both
    inputs so the sheet-wide look (helix coils, mileposts) reaches them as it does the overall sheet."""
    with tempfile.TemporaryDirectory() as tmp:
        run = subprocess.run([str(plugin() / "bin/schematic"), "detail", f"{tmp}/", "--data", str(DATA),
                              *(f"{GRAPHS}/{g}:{n}" for g, n in INPUTS)],
                             capture_output=True, text=True, env=cache_env())
        print(run.stdout + run.stderr, end="")
        if run.returncode:
            sys.exit(run.returncode)
        return {f.name: f.read_text() for f in sorted(Path(tmp).glob("*.svg"))}


def stations_differ(sheets):
    """Names of station sheets that differ from (or are missing in, or no longer belong to) docs/ops/stations."""
    have = {f.name for f in STATIONS.glob("*.svg")} if STATIONS.exists() else set()
    return sorted(n for n in have | set(sheets)
                  if n not in sheets or n not in have or (STATIONS / n).read_text() != sheets[n])


def write_stations(sheets, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob("*.svg"):
        if f.name not in sheets:
            f.unlink()
    for name, svg in sheets.items():
        (folder / name).write_text(svg)


def measured_lengths():
    """{track name: inches} for every measured Track row of block_lengths.csv (measured, timed or estimated, as its
    flag column says). hartlib.railroad.read_block_lengths reads and checks every row, not only the Track rows: it
    stops on an empty or repeated name or a length that is not a number."""
    try:
        lengths = railroad.read_block_lengths(LENGTHS)
    except railroad.FactsError as exc:
        sys.exit(str(exc))
    return {name.removeprefix("Track "): b.inches for name, b in lengths.items()
            if name.startswith("Track ") and b.inches is not None}


def stale_lengths():
    """Track names whose copy in the staging layer file differs from block_lengths.csv ([] when current)."""
    have, want = json.loads(STAGING.read_text()).get("track_lengths_in") or {}, measured_lengths()
    return sorted(k for k in set(have) | set(want) if have.get(k) != want.get(k))


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
    i = argv.index("--preview") + 1 if "--preview" in argv else None
    unknown = [a for n, a in enumerate(argv) if a not in ("--check", "--preview") and n != i]
    if unknown or ("--check" in argv and i):     # anything else would publish: say how to call it instead
        print(__doc__.split("\n\n")[0])
        return 2
    if "--preview" in argv:
        i = argv.index("--preview")
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            sys.exit("--preview needs a folder")
        folder = Path(argv[i + 1]).expanduser().resolve()
        if folder.is_relative_to(REPO):
            sys.exit(f"--preview writes outside the repo; {folder} is inside it")
        stale = stale_lengths()
        if stale:
            print(f"note: {STAGING.name} track_lengths_in differs from {LENGTHS.name} for {', '.join(stale)}; "
                  "this preview counts cars from the old lengths, and publishing copies the new ones")
        write_stations(draw_stations(), folder / "stations")
        return preview(draw(), folder)
    check = "--check" in argv
    stale = stale_lengths()
    if stale and check:
        print(f"{STAGING.name}: track_lengths_in differs from {LENGTHS.name} for {', '.join(stale)}; "
              "run publish_draft.py to copy them")
        return 1
    if check:
        sheet = draw()
        same = target.exists() and target.read_text() == sheet
        print("published draft is current" if same else "published draft differs from the drawing")
        differ = stations_differ(draw_stations())
        print(f"station sheets differ: {', '.join(differ)}" if differ else "station sheets are current")
        try:
            pages = [p.relative_to(REPO).as_posix() for p in map_revision.drift(prefs=page_prefs())]
        except ValueError as e:
            pages = [str(e)]
        print(f"station map pages differ from the title block: {', '.join(pages)}" if pages
              else "station map pages carry the title block's revision and date")
        return 0 if same and not differ and not pages else 1
    prefs = page_prefs()
    try:
        map_revision.planned(REPO / "www", prefs)             # the station map data holds together before any write
    except ValueError as e:
        sys.exit(f"station map pages: {e}; nothing written")
    kept = {p: p.read_text() for p in (prefs, STAGING)}      # put back if anything below fails
    try:
        if stale:
            copy_lengths()
            print(f"copied the lengths of {', '.join(stale)} into {STAGING.name}")
        publish(draw(), target, prefs, kept[prefs], stations_changed(draw_stations()))
        write_stations(draw_stations(), STATIONS)
        print(f"wrote the station sheets in {STATIONS.relative_to(REPO)}")
        for page in map_revision.apply(prefs=prefs):
            print(f"set {page.relative_to(REPO)} to the title block's revision and date")
    except BaseException:
        for p, text in kept.items():
            if p.read_text() != text:
                p.write_text(text)
                print(f"put back {p.name}")
        raise
    return 0


def preview(sheet, folder):
    """The drawing as it stands, into folder; nothing in the repo changes."""
    folder.mkdir(parents=True, exist_ok=True)
    svg, printed = folder / "schematic-system-draft.svg", folder / "schematic-system-draft.pdf"
    svg.write_text(sheet)
    printed.unlink(missing_ok=True)                           # never report an old PDF as this one
    try:
        pdf(svg, printed)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"PDF not printed: {e}")
    print(f"preview: {svg}" + (f" and {printed.name}" if printed.exists() else ""))
    return 0


def stations_changed(sheets):
    """Names of the station sheets whose drawing (title block left out) differs from main's, a new sheet included:
    the station maps carry the schematic's revision, so such a change moves it too."""
    return sorted(n for n, svg in sheets.items()
                  if drawing_only(on_main(STATIONS / n) or "") != drawing_only(svg))


def publish(sheet, target, prefs, original, stations=()):
    """`stations`: the station sheets whose drawing changed (stations_changed); they move the revision as the overall
    sheet does."""
    base = on_main(target) or (target.read_text() if target.exists() else None)
    if base and (drawing_only(base) != drawing_only(sheet) or stations):
        fields = next_fields(on_main(prefs), datetime.date.today())
        now = json.loads(original)
        if fields is None:
            print(f"drawing changed; revision {now.get('revision')!r} is not a number, so date and revision are left as set")
        elif (now.get("date"), now.get("revision")) != fields:
            set_fields(prefs, *fields)
            print(f"drawing changed: title block set to {fields[0]}, revision {fields[1]}")
            sheet = draw()
    pdf_file = OUT / "schematic-system-draft.pdf"
    if target.exists() and target.read_text() == sheet and pdf_file.exists():
        print(f"{target.relative_to(REPO)} is current: SVG and PDF left as they are")
        return
    with tempfile.TemporaryDirectory() as tmp:
        svg, printed = Path(tmp) / target.name, Path(tmp) / "sheet.pdf"
        svg.write_text(sheet)
        try:
            pdf(svg, printed)
        except (subprocess.SubprocessError, OSError) as e:
            sys.exit(f"PDF not printed, nothing written: {e}")
        if not printed.exists():
            sys.exit("Chrome wrote no PDF, nothing written")
        shutil.copyfile(printed, pdf_file)          # the PDF first: a run stopped between the two leaves the SVG
        shutil.copyfile(svg, target)                # old, so the next publish sees it differ and prints again
    print(f"wrote {target} and the PDF (--check compares the SVG only; the PDF follows it)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
