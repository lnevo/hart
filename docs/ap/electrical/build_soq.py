#!/usr/bin/env python3
"""Build the MRE Electrical SOQ package: docs/ap/electrical/MRE-Electrical-SOQ.pdf.

Steps:
  1. Draw the plan clips and drawings (make_drawings.py) and the scaled staging plan.
  2. Fill soq.html: numbers for chapters, sections, figures and tables; cross-references;
     contents lists; Appendix B from the block table; photo placeholders for photos not
     yet taken (PHOTO_PUNCH_LIST.md); the list of wiring records.
  3. Print it twice with headless Chrome: once to find the page of every heading and
     caption, then again with those page numbers in the contents.
  4. Put the ticked NMRA form in front, the railroad's wiring records (exported from the
     two wiring decks with Keynote) behind, page numbers in the footer, and bookmarks.

    python3 docs/ap/electrical/build_soq.py            # needs Chrome, Keynote and PyMuPDF
    python3 docs/ap/electrical/build_soq.py --html-only  # just write build/soq.html and build/plates.html

The form's personal fields stay blank: the member fills them on a private copy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BUILD = HERE / "build"
OUT_PDF = HERE / "MRE-Electrical-SOQ.pdf"
FORM = HERE / "MRE-Electrical-SOQ-form.pdf"
PUNCH = HERE / "PHOTO_PUNCH_LIST.md"
BLOCKS = ROOT / "jmri/layouts/hart/data/block_lengths.csv"
TRACK_PLAN = ROOT / "www/build/track-plan.html"
DECKS = {"layout": ROOT / "docs/wiring/Layout Documentation.pptx", "nodes": ROOT / "docs/wiring/Wiring_Schematic.pptx"}
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
FORM_PAGES = 2
FOOTER = "HART Railroad · Model Railroad Engineer - Electrical · SOQ supporting documentation"   # base-14 Helvetica has no en dash

# Wiring record pages, in order: (deck, 1-based page, expected title start, record name).
RECORDS = [
    ("layout", 1, "Track Busses", "Track buses: each bus, its colours, location and protection device"),
    ("layout", 2, "PSXX-AR", "Power districts: command station, boosters, booster matrix, breakers and auto-reversers"),
    ("layout", 4, "PSXX-2", "Bus wiring: power supply outputs, DCC buses, detector chain, 12 V control bus"),
    ("layout", 5, "Input", "Control node configuration: one node's inputs, outputs and block sensors"),
    ("layout", 6, "Input", "Turnout wiring: switch machine, contacts, Universal Translator, Touch Toggle, output"),
    ("nodes", 1, "Wiring Schematic - Node Summary", "Node summary: every LCOS node, its location and boards"),
    ("nodes", 2, "Turnout Summary", "Turnout summary: each switch's button, feedback and output pins"),
    ("nodes", 3, "Node C1", "Node C1 pin page (east end and return loop)"),
    ("nodes", 4, "Node C2", "Node C2 pin page (east end, west part)"),
    ("nodes", 5, "Node C3", "Node C3 pin page (yard west ladder)"),
    ("nodes", 6, "Node C4", "Node C4 pin page (west end and passing siding)"),
    ("nodes", 7, "Node C11", "Node C11 pin page (helix and return loop)"),
    ("nodes", 8, "Node C12", "Node C12 pin page (east end, yard east ladder)"),
    ("nodes", 9, "Node C13", "Node C13 pin page (yard lead and engine storage)"),
]

# Ids whose numbers soq.html, the drawings and PHOTO_PUNCH_LIST.md quote by hand ("Section 3.3" and so on).
EXPECTED = {"matrix": "2", "req1": "3", "req1-two": "3.1", "req1-gaps": "3.2", "req1-loop": "3.3", "req1-siding": "3.4",
            "req1-engine": "3.5", "req1-yard": "3.6", "req2": "4", "req2-turnout": "4.1", "req2-crossover": "4.2",
            "req3": "5", "req3-a": "5.1", "req3-b": "5.2", "req3-v": "5.3", "req45": "6", "demo": "7",
            "app-a": "A", "app-b": "B", "app-c": "C", "app-d": "D", "app-records": "E"}

YARD = {"S-R": "Y1", "S-1": "Y2", "S-2": "Y3", "S-3": "Y4", "S-4": "Y5"}


def die(msg: str) -> None:
    raise SystemExit(f"build_soq: {msg}")


# ---------------------------------------------------------------- content pieces
def generic(name: str) -> str:
    """Generic description of a detected section from its layout name."""
    if name in YARD:
        return f"Yard track {YARD[name]}"
    m = re.fullmatch(r"EH-(\d)", name)
    if m:
        return f"Engine storage E{m.group(1)}"
    fixed = {"Main West": "Main line (west), RS-1", "West Ext": "Double-track section", "East Lead": "Double-track section",
             "Brick-Plane": "Main line (east)", "East Ext": "Main line beside the passing siding", "Main East": "Main line (east)",
             "K-1": "Return loop RS-2", "K-2": "Return loop RS-2", "Scale": "Passing siding", "Barn": "Yard lead",
             "W-1": "Holding track", "W-2": "Holding track"}
    if name in fixed:
        return fixed[name]
    m = re.fullmatch(r"OS Switch (\d+)([ab]?)", name)
    if m:
        n, half = m.groups()
        return f"Turnout {n}{' (crossover half ' + half + ')' if half else ''}"
    die(f"no generic label for section {name!r}; add it to generic()")


def appendix_b() -> str:
    import make_drawings
    rows = make_drawings.detected_sections()
    if len(rows) != 43:
        die(f"{BLOCKS} has {len(rows)} detected sections, the text says 43; update soq.html")
    body = "".join(f"<tr><td>{i}</td><td>{html.escape(generic(s['name']))}</td><td>{html.escape(s['name'])}</td>"
                   f"<td>C{s['node']} · {s['ch']}</td><td>{'≈ ' if s['estimate'] else ''}{s['inches']:.0f}</td></tr>"
                   for i, s in enumerate(rows, 1))
    return ('<table id="tab-sections"><caption>Detected sections on the staging level and helix</caption>'
            '<thead><tr><th scope="col">No.</th><th scope="col">Section (this document)</th><th scope="col">Layout name</th>'
            f'<th scope="col">Node · ch</th><th scope="col">Length, in</th></tr></thead><tbody>{body}</tbody></table>')


def punch_items() -> dict[str, str]:
    """PL-nn → target file name, from PHOTO_PUNCH_LIST.md (rows like "| PL-01 | `photos/x.jpg` | ...")."""
    items = {}
    for line in PUNCH.read_text().splitlines():
        m = re.match(r"\|\s*(PL-\d\d)\s*\|\s*`photos/([^`]+)`", line)
        if m:
            items.setdefault(m.group(1), [])
            items[m.group(1)].append(m.group(2))
    return {k: v for k, v in items.items()}


def fill_photos(doc: str) -> str:
    """Swap photos not yet taken for placeholders that name their punch-list item."""
    punch = punch_items()

    def one(m: re.Match) -> str:
        fig = m.group(0)
        fid = re.search(r'id="([^"]+)"', fig).group(1)
        src = re.search(r'<img src="photos/([^"]+)"', fig)
        if not src:
            return fig
        name = src.group(1)
        pid = re.search(r'data-punch="([^"]+)"', fig)
        if (HERE / "photos" / name).exists():
            return fig
        if not pid:
            die(f"photos/{name} is missing and figure {fid} has no data-punch item")
        if name not in punch.get(pid.group(1), []):
            die(f"figure {fid}: {pid.group(1)} in {PUNCH.name} does not name photos/{name}")
        alt = re.search(r'alt="([^"]*)"', fig).group(1)
        box = (f'<div class="pending" role="img" aria-label="Photograph pending: {alt}"><strong>Photograph pending · '
               f'{pid.group(1)}</strong>{alt}<br>File: photos/{name}</div>')
        return re.sub(r"<img [^>]*>", box, fig)
    return re.sub(r'<figure class="photo"[^>]*>.*?</figure>', one, doc, flags=re.S)


# ---------------------------------------------------------------- numbering
def number(doc: str) -> tuple[str, dict[str, str], list[tuple[int, str, str, str]], list, list]:
    """Number headings, figures and tables. Returns doc, labels by id, toc, figures, tables."""
    labels: dict[str, str] = {}
    toc, figs, tabs = [], [], []
    ch, sec, sub, app = 0, 0, 0, 0
    fig_n, tab_n = {}, {}
    out = []
    parts = re.split(r'(<section class="[^"]+">)', doc)
    current = ""
    for part in parts:
        m = re.fullmatch(r'<section class="([^"]+)">', part)
        if m:
            current = m.group(1)
            out.append(part)
            continue
        if current not in ("chapter", "appendix", "plates"):
            out.append(part)
            if current == "front":
                for h in re.finditer(r'<h2 class="no-num" id="([^"]+)">([^<]+)</h2>', part):
                    if h.group(1) != "contents":
                        toc.append((2, h.group(1), "", h.group(2)))
            continue
        if current == "chapter":
            ch += 1
            sec = sub = 0
            key = str(ch)
        elif current == "appendix":
            app += 1
            sec = sub = 0
            key = chr(64 + app)
        else:
            sec = sub = 0
            key = "Plate"         # never shown: the plates hold only drawings labelled D1 to D6

        def head(hm: re.Match) -> str:
            nonlocal sec, sub
            lvl, hid, text = int(hm.group(1)), hm.group(2), hm.group(3)
            if lvl == 2:
                num = key
                labels[hid] = f"Chapter {key}" if current == "chapter" else f"Appendix {key}"
                shown = num if current == "chapter" else f"Appendix {key}"
            elif lvl == 3:
                sec += 1
                sub = 0
                num = f"{key}.{sec}"
                labels[hid] = f"Section {num}"
                shown = num
            else:
                sub += 1
                num = f"{key}.{sec}.{sub}"
                labels[hid] = f"Section {num}"
                shown = num
            toc.append((lvl, hid, shown, text))
            return f'<h{lvl} id="{hid}"><span class="num">{shown}</span>{text}</h{lvl}>'
        if current == "plates":
            for pm in re.finditer(r'<h2 class="[^"]*" id="([^"]+)">([^<]+)</h2>', part):
                toc.append((2, pm.group(1), "", pm.group(2)))
        part = re.sub(r'<h([234]) id="([^"]+)">([^<]+)</h\1>', head, part)

        def fig(fm: re.Match) -> str:
            block = fm.group(0)
            fid = re.search(r'id="([^"]+)"', block).group(1)
            cap = re.search(r"<figcaption>(.*?)</figcaption>", block, re.S).group(1)
            if current == "plates":
                lab = re.match(r"Drawing (D\d)", cap).group(1)
                labels[fid] = f"Drawing {lab}"
                short = cap.split(".")[0]
                figs.append((fid, f"Drawing {lab}", short.split(": ", 1)[1] if ": " in short else short, f"Drawing {lab}:"))
                return block
            fig_n[key] = fig_n.get(key, 0) + 1
            lab = f"Figure {key}.{fig_n[key]}"
            labels[fid] = lab
            short = re.sub(r"<[^>]+>", "", cap).split(". ")[0].rstrip(".")
            figs.append((fid, lab, short, f"{lab} {short[:28]}"))
            return block.replace("<figcaption>", f'<figcaption><span class="flabel">{lab}</span>', 1)
        part = re.sub(r'<figure class="[^"]*"[^>]*id="[^"]+"[^>]*>.*?</figure>', fig, part, flags=re.S)

        def tab(tm: re.Match) -> str:
            tid, cap = tm.group(1), tm.group(2)
            tab_n[key] = tab_n.get(key, 0) + 1
            lab = f"Table {key}.{tab_n[key]}"
            labels[tid] = lab
            plain = re.sub(r"<[^>]+>", "", cap)
            tabs.append((tid, lab, plain, f"{lab} {plain[:28]}"))
            return tm.group(0).replace("<caption>", f'<caption><span class="flabel">{lab}</span> ', 1)
        part = re.sub(r'<table id="([^"]+)"[^>]*>\s*<caption>(.*?)</caption>', tab, part, flags=re.S)
        out.append(part)
    doc = "".join(out)
    for k, v in EXPECTED.items():
        got = labels.get(k, "").split(" ")[-1]
        if got != v:
            die(f"{k} is numbered {got!r} but the text and drawings quote {v!r}; renumber them together")

    def xref(xm: re.Match) -> str:
        target = xm.group(1)
        if target not in labels:
            die(f"cross-reference to unknown id #{target}")
        return f'<a class="xref" href="#{target}">{labels[target]}</a>'
    doc = re.sub(r'<a class="xref" href="#([^"]+)"></a>', xref, doc)
    return doc, labels, toc, figs, tabs


def lists(doc: str, toc, figs, tabs, pages: dict[str, int]) -> str:
    def pg(i):
        return str(pages[i]) if i in pages else "00"
    lines = []
    for lvl, hid, num, text in toc:
        if hid in ("contents",):
            continue
        lines.append(f'<li class="l{lvl}"><a href="#{hid}"><span class="lbl">{num}</span>{text}</a>'
                     f'<span class="fill"></span><span class="pg">{pg(hid)}</span></li>')
    doc = doc.replace('<nav id="toc" aria-label="Table of contents"></nav>',
                      f'<nav id="toc" aria-label="Table of contents"><ol>{"".join(lines)}</ol></nav>')
    fl = "".join(f'<li><a href="#{i}"><span class="lbl">{lab}</span>{html.escape(html.unescape(t))}</a><span class="fill"></span>'
                 f'<span class="pg">{pg(i)}</span></li>' for i, lab, t, _ in figs)
    doc = doc.replace('<nav id="figlist" aria-label="List of figures"></nav>',
                      f'<nav id="figlist" aria-label="List of figures"><ol>{fl}</ol></nav>')
    tl = "".join(f'<li><a href="#{i}"><span class="lbl">{lab}</span>{html.escape(html.unescape(t))}</a><span class="fill"></span>'
                 f'<span class="pg">{pg(i)}</span></li>' for i, lab, t, _ in tabs)
    return doc.replace('<nav id="tablist" aria-label="List of tables"></nav>',
                       f'<nav id="tablist" aria-label="List of tables"><ol>{tl}</ol></nav>')


# ---------------------------------------------------------------- scaled plan
def scaled_plan() -> Path:
    """The staging level of plan 5.3b, to scale, with working notes removed (drawings/P0-staging-to-scale.svg)."""
    t = TRACK_PLAN.read_text()
    m = re.search(r'<svg viewBox="([^"]+)" role="img" aria-label="Staging level of plan 5.3b">(.*?)</svg>', t, re.S)
    if not m:
        die(f"{TRACK_PLAN}: no staging-level SVG; update scaled_plan()")
    vb, inner = m.groups()

    def text(tm: re.Match) -> str:
        body = tm.group(2)
        if re.fullmatch(r"Sw \d+", body) or body == "100 cm":
            return f'<text{tm.group(1)}>{body}</text>'
        eh = re.fullmatch(r"EH-(\d)", body)
        if eh:
            return f'<text{tm.group(1)}>E{eh.group(1)}</text>'
        return ""
    inner = re.sub(r"<text([^>]*)>([^<]*)</text>", text, inner)
    style = ("<style>.trk,.m7,.sw7,.to{stroke:#16202a;stroke-width:1.6;fill:none;stroke-dasharray:none}"
             ".loop{stroke:#16202a;stroke-width:2.4;fill:none}.m7old,.m7dot{display:none}.scale{stroke:#16202a;stroke-width:1.4}"
             "text{font:600 8px 'Helvetica Neue',Helvetica,Arial,sans-serif;fill:#16202a}"
             ".m7t{font:600 8px 'Helvetica Neue',Helvetica,Arial,sans-serif;fill:#16202a}</style>")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-labelledby="t">'
           f'<title id="t">Plan P0: the staging level to scale</title>{style}<rect x="-1000" y="-1000" width="4000" '
           f'height="4000" fill="#fff"/>{inner}</svg>')
    path = HERE / "drawings/P0-staging-to-scale.svg"
    path.write_text(svg)
    return path


# ---------------------------------------------------------------- printing
def chrome_pdf(src: Path, dst: Path) -> None:
    if not CHROME.exists():
        die(f"Chrome not found at {CHROME}")
    r = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--allow-file-access-from-files", "--generate-pdf-document-outline", "--export-tagged-pdf",
                        f"--print-to-pdf={dst}", src.as_uri()], capture_output=True, text=True, timeout=180)
    if not dst.exists() or dst.stat().st_size == 0:
        die(f"Chrome did not print {src}: {r.stderr[-400:]}")


def probes(toc, figs, tabs) -> dict[str, tuple[str, bool]]:
    """What to search for to find each item: a chapter-level heading opens its page; anything
    else is found at its last mention. The contents lists come first, so the last match is the item."""
    out = {hid: (f"{num} {text}".strip(), lvl == 2) for lvl, hid, num, text in toc}
    out.update({i: (probe, False) for i, _, _, probe in figs + tabs})
    return out


def locate(pdf: Path, wanted: dict[str, tuple[str, bool]]) -> dict[str, int]:
    """1-based page in pdf of each wanted item."""
    import fitz
    texts = [re.sub(r"\s+", " ", p.get_text()) for p in fitz.open(pdf)]
    pages = {}
    for key, (probe, opens) in wanted.items():
        probe = re.sub(r"\s+", " ", html.unescape(probe)).strip()
        if opens:
            hits = [n for n, t in enumerate(texts) if t.strip().startswith(probe)][-1:]   # contents may spill onto a page that starts with it
        else:
            hits = [n for n, t in enumerate(texts) if probe in t][-1:]
        if not hits:
            die(f"cannot find {probe!r} in {pdf.name}")
        pages[key] = hits[0] + 1
    return pages


def export_decks(tmp: Path) -> dict[str, Path]:
    out = {}
    for key, pptx in DECKS.items():
        dst = tmp / f"{key}.pdf"
        script = (f'tell application "Keynote"\nset d to open POSIX file "{pptx}"\n'
                  f'export d to POSIX file "{dst}" as PDF\nclose d saving no\nend tell')
        for attempt in range(3):          # Keynote refuses ("Connection is invalid") while it is still quitting
            subprocess.run(["osascript", "-e", 'tell application "Keynote" to launch'], capture_output=True, timeout=60)
            time.sleep(2 + 3 * attempt)
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=180)
            if dst.exists():
                break
        if not dst.exists():
            die(f"Keynote could not export {pptx.name}: {r.stderr.strip()}")
        out[key] = dst
    subprocess.run(["osascript", "-e", 'tell application "Keynote" to quit'], capture_output=True)
    return out


def ticked_form(tmp: Path) -> Path:
    """The NMRA form with the claimed items ticked and nothing personal filled in."""
    import fitz
    want_on = {"If DCCTMCCOther Power  gapsswitchesphase for troubleshooting", "One Reverse Loop or Wye or Turntable or Transfer Table",
               "One passing siding", "Facilities for storing of at least two unused motive power units",
               "One yard with a minimum of three tracks and a switching lead independent of the mainline",
               "One power supply with protective devices short indicator andor circuit breaker to ensure safe operation",
               "Turnout", "Crossover", "Check Box4", "Electrical turnout position", "Track occupancy", "Check Box11",
               "Attachment showing the track plan required in Requirement 1",
               "Description of the track work features method of construction and identification of commercial"}
    text = {"NMRA Region": "Northeastern (NER)", "Division": "Sunrise Trails", "Other_2": "Reversing sections (2), auto-reversers"}
    d = fitz.open(FORM)
    seen = set()
    for page in d:
        for w in page.widgets():
            name = w.field_name
            if w.field_type_string == "CheckBox":
                w.field_value = w.on_state() if name in want_on else "Off"
                if name in want_on:
                    seen.add(name)
                w.update()
            elif name in text:
                w.field_value = text[name]
                w.update()
                seen.add(name)
    missing = (want_on | set(text)) - seen
    if missing:
        die(f"form fields not found: {sorted(missing)}")
    if d.page_count != FORM_PAGES:
        die(f"{FORM.name} has {d.page_count} pages; FORM_PAGES (and 'Pages 1 and 2' in soq.html) assume {FORM_PAGES}")
    dst = tmp / "form.pdf"
    d.save(dst)
    return dst


def assemble(doc_pdf: Path, plates_pdf: Path, after: int, form_pdf: Path, decks: dict[str, Path], toc, pages,
             records_label: str) -> None:
    """after: the main-document page (1-based) the landscape plates follow."""
    import fitz
    doc = fitz.open(doc_pdf)
    doc.insert_pdf(fitz.open(plates_pdf), start_at=after)
    form = fitz.open(form_pdf)
    doc.insert_pdf(form, start_at=0)
    srcs = {k: fitz.open(v) for k, v in decks.items()}
    for key, n, start, name in RECORDS:
        src = srcs[key]
        if src.page_count < n or not src[n - 1].get_text().strip().startswith(start):
            die(f"{DECKS[key].name} page {n} does not start with {start!r}; update RECORDS")
        page = doc.new_page(width=792, height=612)
        page.insert_text((50, 40), f"{records_label} · {name}", fontsize=10, fontname="helv", color=(0.12, 0.31, 0.51))
        page.show_pdf_page(fitz.Rect(50, 52, 742, 560), src, n - 1, keep_proportion=True)
    total = doc.page_count
    for i, page in enumerate(doc):
        if i < FORM_PAGES + 1:            # form pages and the title page carry no footer
            continue
        w, h = page.rect.width, page.rect.height
        page.insert_text((54, h - 30), FOOTER, fontsize=7.5, fontname="helv", color=(0.35, 0.4, 0.45))
        label = f"Page {i + 1} of {total}"
        page.insert_text((w - 54 - fitz.get_text_length(label, "helv", 7.5), h - 30), label, fontsize=7.5,
                         fontname="helv", color=(0.35, 0.4, 0.45))
    outline = [[1, "SOQ form", 1]]
    for lvl, hid, num, text in toc:
        if hid in pages and lvl <= 3:
            outline.append([lvl - 1, f"{num} {html.unescape(text)}".strip(), pages[hid]])
    rec_start = total - len(RECORDS) + 1
    for k, (_, _, _, name) in enumerate(RECORDS):
        outline.append([2, name.split(":")[0], rec_start + k])
    doc.set_toc(outline)
    doc.set_metadata({"title": "Model Railroad Engineer – Electrical: Statement of Qualifications",
                      "author": "HART Railroad", "subject": "NMRA Achievement Program SOQ supporting documentation",
                      "keywords": "NMRA, Achievement Program, Model Railroad Engineer, Electrical, SOQ"})
    doc.set_language("en-US") if hasattr(doc, "set_language") else None
    doc.save(OUT_PDF, garbage=3, deflate=True)


# ---------------------------------------------------------------- main
def render(date: str) -> tuple[str, list, list, list, dict]:
    doc = (HERE / "soq.html").read_text()
    doc = doc.replace("{{DATE}}", date).replace("{{APPENDIX_B}}", appendix_b())
    doc = fill_photos(doc)
    doc, labels, toc, figs, tabs = number(doc)
    return doc, toc, figs, tabs, labels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--html-only", action="store_true", help="write build/soq.html and stop")
    ap.add_argument("--date", default=dt.date.today().strftime("%-d %B %Y"))
    a = ap.parse_args()
    sys.path.insert(0, str(HERE))
    import make_drawings
    make_drawings.main()
    scaled_plan()
    BUILD.mkdir(exist_ok=True)
    doc, toc, figs, tabs, labels = render(a.date)
    records = "".join(f"<li>{html.escape(name)} <span class=\"pg\">(page {{{{REC{k}}}}})</span></li>"
                      for k, (_, _, _, name) in enumerate(RECORDS))
    doc = doc.replace("{{APPENDIX_RECORDS}}", f'<ol class="record-list">{records}</ol>')
    page_html = BUILD / "soq.html"
    for name in ("soq.css",):
        shutil.copy(HERE / name, BUILD / name)
    for sub in ("drawings", "photos"):
        link = BUILD / sub
        if link.is_symlink() or link.exists():   # a link left by a swept worktree dangles
            link.unlink()
        link.symlink_to(HERE / sub)

    plates_html = BUILD / "plates.html"
    plate_keys = {"plates"} | {i for i, lab, _, _ in figs if lab.startswith("Drawing ")}

    def write(pages: dict[str, int], rec0: int) -> None:
        """Write the portrait document and, apart, the landscape plates: Chrome lays a named
        landscape page out at the first page's width, so the plates are printed on their own."""
        out = lists(doc, toc, figs, tabs, pages)
        for k in range(len(RECORDS)):
            out = out.replace(f"{{{{REC{k}}}}}", str(rec0 + k) if rec0 else "00")
        m = re.search(r'<section class="plates">.*?</section>', out, re.S)
        if not m:
            die("soq.html has no plates section")
        head = out[:out.index("<body>") + len("<body>")]
        landscape = "<style>@page { size: 11in 8.5in; margin: 0.6in 0.7in 0.75in 0.7in; }</style></head>"
        plates_html.write_text(head.replace("</head>", landscape) + m.group(0).replace(' class="plates"', "") + "</body></html>")
        page_html.write_text(out[:m.start()] + out[m.end():])
    write({}, 0)
    if a.html_only:
        print(page_html, plates_html)
        return
    import fitz
    want = probes(toc, figs, tabs)
    main_want = {k: v for k, v in want.items() if k not in plate_keys}
    plate_want = {k: v for k, v in want.items() if k in plate_keys}

    def paginate(main_pdf: Path, plates_pdf: Path) -> tuple[dict[str, int], int, int]:
        """Final page of every item, the main page the plates follow, and the first record page."""
        main, plates = locate(main_pdf, main_want), locate(plates_pdf, plate_want)
        n_main, n_plates = fitz.open(main_pdf).page_count, fitz.open(plates_pdf).page_count
        after = main["app-a"] - 1
        pages = {k: FORM_PAGES + v + (n_plates if v > after else 0) for k, v in main.items()}
        pages.update({k: FORM_PAGES + after + v for k, v in plates.items()})
        return pages, after, FORM_PAGES + n_main + n_plates + 1
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        chrome_pdf(page_html, tmp / "main1.pdf")
        chrome_pdf(plates_html, tmp / "plates1.pdf")
        pages, after, rec0 = paginate(tmp / "main1.pdf", tmp / "plates1.pdf")
        write(pages, rec0)
        chrome_pdf(page_html, tmp / "main2.pdf")
        chrome_pdf(plates_html, tmp / "plates2.pdf")
        if paginate(tmp / "main2.pdf", tmp / "plates2.pdf") != (pages, after, rec0):
            die("page numbers moved between the two passes; check the contents lists")
        assemble(tmp / "main2.pdf", tmp / "plates2.pdf", after, ticked_form(tmp), export_decks(tmp), toc, pages,
                 labels["app-records"])
    print(f"{OUT_PDF.relative_to(ROOT)}: {fitz.open(OUT_PDF).page_count} pages")


if __name__ == "__main__":
    main()
