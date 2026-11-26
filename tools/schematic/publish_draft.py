"""publish_draft.py [--check | --preview DIR]

Draw the system schematic with the schematic-maps plugin and publish it in docs/ops:
schematic-system-draft.svg (the file keeps its name; the DRAFT mark came off when the owner approved the helix-join
release, 2026-11-17) and a Letter landscape PDF printed by
Chrome, and one SVG per station detail sheet (the `detail_sheets` preference) in docs/ops/stations/. Inputs: the layer files in jmri/layouts/hart/data/schematic/ and the plan graphs in its inputs/ folder
(track only, regenerated from the owner's AnyRail export as its README says). The plugin is this checkout's submodule
external/model-railroad-skills at its pinned commit (`git submodule update --init external/model-railroad-skills`
in a new worktree), or SCHEMATIC_PLUGIN=<plugin folder> for a trial of other plugin code.

--check draws and compares with the published SVG and the station sheets without writing anything (exit 1 if
any differ). Car counts and mileposts use the plan's lengths on every level (the layer files hold no measured
lengths since 2026-11-20: block_lengths.csv is the one record).
A pass records a digest of what the comparison read (check_digest: the plugin's code, every file in the layer
folder and its graphs, the published SVG and station sheets, this script, the Python) in publish_draft.check in the
plugin's cache folder, which keeps the last STAMP_KEEP so worktrees that take turns do not push each other out; a
later --check with a digest in it skips the drawing (24 s measured), and any change to one of them draws again. The station map pages are checked every time. SCHEMATIC_CACHE= (empty)
turns the stamp off with the cache.
--preview DIR draws the SVG and its PDF into DIR for the owner to look at; docs/ops, the layer files and the
title block's date and revision are left alone.
When the drawing itself (everything but the title block), or a station sheet's, differs from main's, publishing sets `date` to today and
`revision` to main's revision plus one in the page's preferences file, then draws again. Counting from main, not
from the last publish, keeps a branch that publishes several times at one revision. A revision that is not a
whole number is left alone. If anything fails after that, the preferences file is put back.
Main is where this branch left origin/main (`git merge-base HEAD origin/main`). If git cannot find that commit
(no origin/main, a shallow clone), publishing stops before it writes anything and names the git command that
brings it in; it also stops if git fails to read a file there. --check and --preview never need it.
The station map pages are drawn from this sheet, so publishing then copies the title block's revision and date to
them with hartlib.map_revision (which rebuilds www/data/crew.json from the crew master), and --check fails while any of them differs.
After a commit that changes the drawing, run tools/schematic/evolution.py.

The plugin's solved-sheet cache (SCHEMATIC_CACHE, default <main checkout>/.cache/hart/schematic, shared by every worktree; HART_CACHE_DIR moves the base; a folder only this user can open)
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
import functools
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import devices, layer_files, map_revision, paths  # noqa: E402

REPO = paths.REPO_ROOT
CACHE = paths.cache_dir("schematic")      # <main checkout>/.cache/hart/schematic, shared by every worktree
DATA = REPO / "jmri/layouts/hart/data/schematic"
GRAPHS = DATA / "inputs"
OUT = REPO / "docs/ops"
STATIONS = OUT / "stations"                                              # one SVG per station detail sheet
INPUTS = [("staging.json", "staging"), ("main.json", "main_upper")]     # graph, layer file stem; the last sets the page
sys.path.insert(0, str(REPO / "tools/ops"))  # screenshot.py is a script, not a package: import it by folder
from screenshot import ChromeMissing, find_chrome  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_screen  # noqa: E402

# the plugin's title box (it grows for a long title line), drawn after the drawing itself
TITLE_BOX = re.compile(r'<rect x="24" y="728" width="([\d.]+)" height="64"')


class PublishError(Exception):
    """Publishing or checking cannot go on; the message says why and what to run. main() prints it and exits 1."""


class PluginMissing(PublishError):
    """The schematic-maps plugin is not in this checkout or is off its pinned commit, and SCHEMATIC_PLUGIN is not
    set. The --check builders skip on it (build_signals, build_cats_panel); le_common turns it into a BuildError."""


class DrawFailed(PublishError):
    """bin/schematic exited non-zero; its output is printed already. main() exits with its status."""

    def __init__(self, returncode: int) -> None:
        super().__init__(f"bin/schematic exited {returncode}")
        self.returncode = returncode


if map_revision.PAGE_SHEET != INPUTS[-1][1]:
    raise PublishError(f"hartlib.map_revision.PAGE_SHEET is {map_revision.PAGE_SHEET!r} but the last input, which sets "
                       f"the page, is {INPUTS[-1][1]!r}: make them agree")


def page_prefs():
    """The preferences section that sets the page: the last input's in preferences.json (hartlib.map_revision)."""
    return map_revision.page_prefs(DATA)


def _git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


@functools.lru_cache(maxsize=None)
def main_base() -> str:
    """The commit where this branch left main, asked of git once per run. Publishing stops if git cannot tell (no
    origin/main, a shallow clone): compared with HEAD instead, a committed drawing change would equal itself and
    keep its old revision. --check and --preview never ask, so they run in a clone without origin/main (CI's is one)."""
    r = _git("merge-base", "HEAD", "origin/main")
    base = r.stdout.strip()
    if r.returncode != 0 or not base:
        why = r.stderr.strip() or f"exit {r.returncode}, no commit named"
        if _git("rev-parse", "--verify", "--quiet", "origin/main").returncode != 0:
            fix = "This checkout has no origin/main: run `git fetch origin main:refs/remotes/origin/main`"
        elif _git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            fix = "This clone is shallow, so the shared commit is not in it: run `git fetch --unshallow origin`"
        else:
            fix = ("HEAD and origin/main share no commit: check out a branch made from main "
                   "(`make wt TOPIC=<topic>`) and bring the drawing change there")
        raise PublishError(f"`git merge-base HEAD origin/main` failed ({why}), so the revision cannot be counted from "
                           f"main; nothing written. {fix}, then run `python3 tools/schematic/publish_draft.py` again")
    return base


def on_main(path: Path) -> str | None:
    """The file's text where this branch left main (None if it was not there). A git failure raises PublishError:
    read as "not there", it would count the revision from nothing."""
    base, rel = main_base(), path.relative_to(REPO).as_posix()
    r = _git("ls-tree", "--name-only", base, "--", rel)
    if r.returncode == 0 and not r.stdout.strip():
        return None                                            # git read the commit; the path is not in it
    if r.returncode == 0:
        r = _git("show", f"{base}:{rel}")
    if r.returncode != 0:
        raise PublishError(f"git could not read {rel} at {base} ({r.stderr.strip() or f'exit {r.returncode}'}), so "
                           "the drawing cannot be compared with main; the files this run changed are put back. Run "
                           "`git fsck` if git names a missing or corrupt object, then "
                           "`python3 tools/schematic/publish_draft.py` again")
    return r.stdout


def plugin() -> Path:
    """The plugin folder: SCHEMATIC_PLUGIN, else this checkout's submodule at its pinned commit. PluginMissing when
    the submodule is not checked out or is off its pin."""
    env = os.environ.get("SCHEMATIC_PLUGIN")
    if env:
        print(f"plugin: {env} (SCHEMATIC_PLUGIN)")
        return Path(env)
    sub = REPO / "external/model-railroad-skills"
    p = sub / "plugins/schematic-maps"
    if not (p / "bin/schematic").exists():
        raise PluginMissing("schematic-maps plugin not found: run git submodule update --init "
                            "external/model-railroad-skills")
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    have = git("-C", str(sub), "rev-parse", "HEAD")
    pinned = git("-C", str(REPO), "ls-files", "-s", "external/model-railroad-skills").split()[1]
    if have != pinned:
        raise PluginMissing(f"submodule is at {have[:8]}, pinned {pinned[:8]}: run git submodule update, "
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
    through the cache. Every builder gets its bands here, so they share one cache key with publishing. Its page
    options gain le_window and cats_window, both from the page's host_screen (apply_host_screen): the one place the
    Layout Editor panel's and the CATS desks' windows are derived. host_screen.HostScreenError when that stops; a
    caller turns it into its own error (le_common.schematic: BuildError)."""
    with cache_on():
        built = sheet.build([(str(GRAPHS / g), n) for g, n in INPUTS], str(layer_files.view(DATA)))
    apply_host_screen(built.opts)
    return built


def apply_host_screen(opts, data=DATA):
    """`opts` (the solved page options) with le_window and cats_window from preferences.json's host_screen
    (host_screen.apply, over every section of the file in `data`). Every stop is a host_screen.HostScreenError,
    a preferences file that cannot be read included."""
    try:
        map_revision.page_prefs(data)                   # stops on a sheet.preferences.json beside it
        sections = layer_files.read_file("preferences", data)
    except ValueError as exc:                           # LayerFileError is one
        raise host_screen.HostScreenError(f"the page's preferences: {exc}") from exc
    return host_screen.apply(opts, sections, map_revision.PAGE_SHEET)


STAMP_VERSION = b"publish_draft check 4"
HARTLIB = Path(devices.__file__).resolve().parents[1]   # the hartlib source tree this run imports (tools/hartlib/src)
STAMP_KEEP = 8                 # digests kept, newest first: one per worktree that runs --check in turn


def stamp_file():
    """Where --check keeps the digests of the inputs of its last passes (check_digest): publish_draft.check in the
    plugin's cache folder (cache_env), whose pruning removes only its own entries. None with the cache off."""
    where = cache_env()["SCHEMATIC_CACHE"].strip()
    return Path(where).expanduser() / "publish_draft.check" if where else None


def _tree(h, root, label):
    """Hash every file under root (Python's own caches aside), by its path below root and its bytes."""
    h.update(f"{label}\0".encode())
    files = sorted(f for f in root.rglob("*") if f.is_file() and "__pycache__" not in f.relative_to(root).parts)
    for f in files:
        h.update(f.relative_to(root).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")


def check_digest(plugin_dir):
    """A hex digest of everything the --check drawing comparison reads: the plugin's code (the folder bin/schematic
    runs from), every file in DATA (the layer files and the graphs in GRAPHS below it), devices_field.csv beside it
    (the owner's track names, which the plugin's view carries), the merged plan overrides and preferences the view
    writes (hartlib.layer_files.merged: preferences.json's block IDs take generated names from devices_generated.csv,
    which is not hashed whole), the hartlib code that builds that view (the whole HARTLIB tree: layer_files,
    track_names, devices and what they import, so a change there draws again before the data changes), the published
    SVG and the station sheets it is compared with, this script, and the Python the plugin runs under (bin/schematic runs the
    python3 on PATH, the real file it names, with the caller's PYTHONPATH). The station map pages and the staging
    lengths are not in it: --check reads those each time. Raises OSError when a file cannot be read."""
    h = hashlib.sha256(STAMP_VERSION + b"\0" + sys.version.encode() + b"\0")
    python = shutil.which("python3")
    h.update(f"{python and os.path.realpath(python)}\0{os.environ.get('PYTHONPATH')}\0".encode())
    h.update(Path(__file__).read_bytes() + b"\0")
    _tree(h, Path(plugin_dir), "plugin")
    _tree(h, DATA, "data")
    _tree(h, HARTLIB, "hartlib")
    field = devices.field_path(DATA.parent)       # the owner's track names the view draws (hartlib.track_names)
    h.update(b"field\0" + (field.read_bytes() if field.exists() else b"-") + b"\0")
    for kind in ("plan_overrides", "preferences"):      # what the plugin's view holds, its track names resolved
        try:
            merged = layer_files.dumps(layer_files.merged(DATA, kind)).encode()
        except layer_files.LayerFileError:
            merged = b"-"           # the drawing stops on it; the hand files above are hashed whole
        h.update(kind.encode() + b"\0" + merged + b"\0")
    target = OUT / "schematic-system-draft.svg"
    h.update(b"target\0" + (b"+" + target.read_bytes() if target.exists() else b"-") + b"\0")
    if STATIONS.exists():
        _tree(h, STATIONS, "stations")
    return h.hexdigest()


def read_stamp(stamp):
    """The digests in the stamp, newest first ([] when there is none). One that cannot be read counts as empty
    (said on stderr)."""
    if stamp is None:
        return []
    try:
        return stamp.read_text().split()
    except FileNotFoundError:
        return []
    except OSError as e:
        print(f"cannot read {stamp} ({e}); drawing to compare", file=sys.stderr)
        return []


def write_stamp(stamp, digest):
    """Record a passing check's digest ahead of the STAMP_KEEP - 1 newest others, through a temp file so a parallel
    reader never sees half of it. Two writers at once may lose one digest, which costs only a drawing. A write that
    fails is said on stderr: the stamp only saves time."""
    if stamp is None:
        return
    kept = [digest] + [d for d in read_stamp(stamp) if d != digest][:STAMP_KEEP - 1]
    tmp = None
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=stamp.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(kept) + "\n")
        os.replace(tmp, stamp)
        tmp = None
    except OSError as e:
        print(f"cannot write {stamp} ({e}); the next --check draws again", file=sys.stderr)
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)


def _digest_or_none(where):
    """check_digest, or None (said on stderr) when a file went away or could not be read while it was taken."""
    try:
        return check_digest(where)
    except OSError as e:
        print(f"cannot take the --check digest ({e}); drawing to compare", file=sys.stderr)
        return None


def compare_drawing():
    """(sheet current, [station sheets that differ]) for --check. When the stamp holds the digest of these inputs
    (check_digest), an earlier --check found them current and nothing is drawn; otherwise both are drawn and
    compared, and a pass records the digest, taken before and after the drawing so an edit made meanwhile records
    nothing."""
    target, stamp = OUT / "schematic-system-draft.svg", stamp_file()
    where = plugin() if stamp else None
    before = _digest_or_none(where) if stamp else None
    if before and before in read_stamp(stamp):
        print("drawing inputs unchanged since a passing --check: not drawn again")
        return True, []
    sheet = draw()
    same = target.exists() and target.read_text() == sheet
    differ = stations_differ(draw_stations())
    if before and same and not differ and _digest_or_none(where) == before:
        write_stamp(stamp, before)
    return same, differ


def draw() -> str:
    """The schematic SVG as the plugin draws it now. DrawFailed when bin/schematic fails."""
    with tempfile.TemporaryDirectory() as tmp:
        svg = Path(tmp) / "sheet.svg"
        run = subprocess.run([str(plugin() / "bin/schematic"), "draw", str(svg), "--data", str(layer_files.view(DATA)),
                              *(f"{GRAPHS}/{g}:{n}" for g, n in INPUTS)],
                             capture_output=True, text=True, env=cache_env())
        print(run.stdout + run.stderr, end="")
        if run.returncode:
            raise DrawFailed(run.returncode)
        return svg.read_text()


def draw_stations() -> dict[str, str]:
    """{file name: SVG} of every station detail sheet (the detail_sheets preference), drawn from both
    inputs so the sheet-wide look (helix coils, mileposts) reaches them as it does the overall sheet. DrawFailed
    when bin/schematic fails."""
    with tempfile.TemporaryDirectory() as tmp:
        run = subprocess.run([str(plugin() / "bin/schematic"), "detail", f"{tmp}/", "--data", str(layer_files.view(DATA)),
                              *(f"{GRAPHS}/{g}:{n}" for g, n in INPUTS)],
                             capture_output=True, text=True, env=cache_env())
        print(run.stdout + run.stderr, end="")
        if run.returncode:
            raise DrawFailed(run.returncode)
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


def drawing_only(svg):
    """The sheet up to the title block (which the plugin draws last), to tell a real drawing change."""
    box = TITLE_BOX.search(svg)
    return svg[:box.start()] if box else svg


def next_fields(main_prefs, today):
    """(date, revision) for a changed drawing: today and main's revision plus one; None if that revision
    is not a whole number (a lettered revision is the owner's to set). `main_prefs`: the page's preferences section
    on main, or None for none."""
    rev = main_prefs.get("revision", 0) if main_prefs else 0
    if isinstance(rev, bool) or not str(rev).strip().isdigit():
        return None
    return today.isoformat(), int(rev) + 1


def prefs_on_main(prefs: layer_files.Section) -> dict:
    """The page's preferences section where this branch left main. PublishError (one line) if main has no such
    file or section: counted from nothing, the revision would restart at 1."""
    text = on_main(prefs.path)
    if text is None:
        raise PublishError(f"{prefs.path.relative_to(REPO)} is not on main, so the revision cannot be counted from "
                           "main; nothing written. Publish from a branch made from a main that has it")
    try:
        return prefs.of(text, f"{prefs.path.name} on main")
    except layer_files.LayerFileError as exc:
        raise PublishError(f"{exc}; nothing written") from exc


def set_fields(prefs, date, rev):
    """Set the title block's date and revision in the page's preferences section (a hartlib.layer_files.Section)."""
    section = prefs.read()
    section["date"], section["revision"] = date, rev
    prefs.write(section)


def pdf(svg_path: Path, pdf_path: Path) -> None:
    """Print the SVG to a Letter landscape PDF with headless Chrome. PublishError when there is no Chrome; a failed
    print is the subprocess error."""
    try:
        chrome = find_chrome()
    except ChromeMissing as exc:
        raise PublishError(str(exc)) from exc
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text("<!doctype html><style>@page{size:11in 8.5in;margin:0}html,body{margin:0}"
                        "img{width:11in;height:8.5in;display:block}</style>"
                        f'<img src="{svg_path.resolve().as_uri()}">')
        subprocess.run([chrome, "--headless", "--disable-gpu", f"--user-data-dir={tmp}/profile",
                        "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", page.as_uri()],
                       capture_output=True, timeout=120, check=True)


def main(argv: list[str]) -> int:
    """Run publish_draft with `argv`; a PublishError ends the run with its message, a failed drawing with the
    plugin's exit status."""
    try:
        return run(argv)
    except DrawFailed as exc:
        return exc.returncode
    except PublishError as exc:
        sys.exit(str(exc))


def run(argv: list[str]) -> int:
    """--check, --preview DIR or a publish (the module docstring); PublishError when one cannot go on."""
    target = OUT / "schematic-system-draft.svg"
    i = argv.index("--preview") + 1 if "--preview" in argv else None
    unknown = [a for n, a in enumerate(argv) if a not in ("--check", "--preview") and n != i]
    if unknown or ("--check" in argv and i):     # anything else would publish: say how to call it instead
        print(__doc__.split("\n\n")[0])
        return 2
    if "--preview" in argv:
        i = argv.index("--preview")
        if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
            raise PublishError("--preview needs a folder")
        folder = Path(argv[i + 1]).expanduser().resolve()
        if folder.is_relative_to(REPO):
            raise PublishError(f"--preview writes outside the repo; {folder} is inside it")
        write_stations(draw_stations(), folder / "stations")
        return preview(draw(), folder)
    check = "--check" in argv
    if check:
        same, differ = compare_drawing()
        print("published draft is current" if same else "published draft differs from the drawing")
        print(f"station sheets differ: {', '.join(differ)}" if differ else "station sheets are current")
        try:
            pages = [p.relative_to(REPO).as_posix() for p in map_revision.drift(prefs=page_prefs())]
            pages = [f"{p} (differs from crew_master.build: the crew master or the title block)"
                     if p == "www/data/crew.json" else p for p in pages]
        except ValueError as e:
            pages = [str(e)]
        print(f"station map pages differ from the title block: {', '.join(pages)}" if pages
              else "station map pages carry the title block's revision and date")
        return 0 if same and not differ and not pages else 1
    try:
        prefs = page_prefs()
        map_revision.planned(REPO / "www", prefs)             # the station map data holds together before any write
    except ValueError as e:
        raise PublishError(f"station map pages: {e}; nothing written") from e
    main_base()                                               # stops here, before any write, if git cannot find it
    kept = {p: p.read_text() for p in (prefs.path,)}        # put back if anything below fails
    try:
        publish(draw(), target, prefs, kept[prefs.path], stations_changed(draw_stations()))
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


def publish(sheet: str, target: Path, prefs: layer_files.Section, original: str, stations: Sequence[str] = ()) -> None:
    """`stations`: the station sheets whose drawing changed (stations_changed); they move the revision as the overall
    sheet does. PublishError when the PDF is not printed."""
    base = on_main(target) or (target.read_text() if target.exists() else None)
    if base and (drawing_only(base) != drawing_only(sheet) or stations):
        fields = next_fields(prefs_on_main(prefs), datetime.date.today())
        now = prefs.of(original)
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
            raise PublishError(f"PDF not printed, nothing written: {e}") from e
        if not printed.exists():
            raise PublishError("Chrome wrote no PDF, nothing written")
        shutil.copyfile(printed, pdf_file)          # the PDF first: a run stopped between the two leaves the SVG
        shutil.copyfile(svg, target)                # old, so the next publish sees it differ and prints again
    print(f"wrote {target} and the PDF (--check compares the SVG only; the PDF follows it)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
