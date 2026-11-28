"""Publish the Neville Island helix package into the ops portal (helix/).

Reads STLs and documents from docs/benchwork/helix and writes helix/index.html (the STL index) and
helix/build-status.html (the build status, rendered from Markdown). Needs markdown and trimesh:

    .venv/bin/python www/scripts/build_helix_page.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import NamedTuple

import markdown
import trimesh

PORTAL = Path(__file__).resolve().parents[1]
OUT = PORTAL / "helix"
HELIX = PORTAL.parent / "docs" / "benchwork" / "helix"
SRC = HELIX / "stl"
DOCS = HELIX
PLAN = 'helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf'
STATUS = 'HART_Neville_Helix_BUILD_STATUS.md'
HANDOFF = 'HART_Neville_Helix_Agent_Handoff_FINAL_31p75_18p75_2026-09-23.md'
HEAD = Path(__file__).resolve().parent / "helix_page_head.html"


class Fixture(NamedTuple):
    """One part in the STL index: its files, the script that made them (archived; None when none was kept), a note."""
    files: list[str]
    script: str | None
    note: str


# (group, [(files, script, note)]): a plain literal, which tools/audit/tests/test_helix_stl_index.py reads (so the type
# is declared on its own line, and the literal stays an ast.Assign)
GROUPS: list[tuple[str, list[tuple[list[str], str | None, str]]]]
GROUPS = [
    ('Router templates', [
        (['roadbed_halflap_template_A.3mf', 'roadbed_halflap_template_A.stl', 'roadbed_halflap_template_A_CORE100.stl',
          'roadbed_halflap_template_B.3mf', 'roadbed_halflap_template_B.stl', 'roadbed_halflap_template_B_CORE100.stl'],
         'make_lap_template.py', 'Half-lap router template, hands A and B. Hooks the end cut and the 26 in edge; window to a radial shoulder at 3.75°. Open the 3MF (body + 100% core modifier).'),
        (['bracket_pocket_template_A.3mf', 'bracket_pocket_template_A.stl', 'bracket_pocket_template_A_CORE100.stl',
          'bracket_pocket_template_B.3mf', 'bracket_pocket_template_B.stl', 'bracket_pocket_template_B_CORE100.stl'],
         'make_bracket_pocket_template.py', 'Bracket pocket at a lap joint: slot 0.6625 wide on the joint line, 3/32 deep, 1/2 in bit. Pair with the same lap letter.'),
        (['bracket_pocket_template_MID.3mf', 'bracket_pocket_template_MID.stl', 'bracket_pocket_template_MID_CORE100.stl'],
         'make_mid_pocket_template.py', 'Mid-piece bracket pocket (odd n). Rides the 26 in edge; center the V-notch on the pencil line (chord 20.683, P1 19.900).'),
        (['router_depth_block.stl'], 'make_router_depth_block.py', 'Two-sided depth block, wells 3/32 · 1/4 · 3/8 / 1/2 · 5/8 · 3/4. Print on its end with a brim.'),
        (['router_depth_gauge.stl'], 'make_router_depth_gauge.py', 'Checks POCKET 3/32, LOWER 1/4, UPPER 1/2 (3/4-stock values).'),
    ]),
    ('Heights', [
        (['p1_height_template.stl'], 'make_height_spacers.py', 'P1 roadbed top at bracket 0: 1-1/32 in above the deck.'),
        (['height_base_1_4in.stl', 'height_spacer_1_4in.stl', 'height_spacer_1_2in.stl', 'height_spacer_3_4in.stl',
          'height_spacer_1in.stl', 'height_spacer_1_1_2in.stl'],
         'make_height_spacers.py', 'Stacking height blocks (pegs + crush ribs). Template + 1/2 in per 45° marks the plywood top.'),
        (['first_loop_pier_post2.stl', 'first_loop_pier_post3.stl', 'first_loop_pier_post4.stl',
          'first_loop_pier_post5.stl', 'first_loop_pier_post6.stl', 'first_loop_pier_post7.stl'],
         'make_first_loop_piers.py', 'First-loop piers, posts 2–7. Top at grade, arrow uphill; two screw tabs.'),
        (['layer_spacer_4in_pitch.stl'], 'make_layer_spacer.py', 'Loop-to-loop check, 3.280 in (4.000 − 0.72). Normal mode, ~22 g.'),
        (['layer_spacer_4in_pitch_vase.stl', 'layer_spacer_4in_pitch_vase_1line.stl'], 'make_layer_spacer_vase.py',
         'Same spacer in spiral vase mode (~10 g, or ~4 g single line). Slice gap closing radius 0.01.'),
    ]),
    ('Entry', [
        (['entry_wedge_riser_inside.stl', 'entry_wedge_riser_outside.stl'], None, 'Tongue risers, 1 × 2.25 in, 1.261 tall, step 0.864. Engraved R / L.'),
        (['cork_to_plywood_transition_shim.stl'], None, 'The “offset bracket” under P1: low foot 0.375 (tongue), high foot 0.611 (P1). Sits in a ~0.300 deep deck pocket.'),
        (['corner_spacer_P1.stl'], 'make_corner_offset_spacer.py', 'Barrel under each P1 wing corner, 0.311 tall, 5/8 OD. Print 2 at 100% infill; measure the gap first.'),
    ]),
    ('Brackets', [
        (['bracket_edge_shim.stl'], 'make_bracket_edge_shim.py', 'Fills the 26 in edge to 2x4 face gap above the bend; also the radial go/no-go gauge. 29 needed.'),
        (['bracket_plumb_shim.stl'], 'make_bracket_plumb_shim.py', 'Tapered strip (0.20 → 0.56 mm) for the sideways lean from grade. Notched edge uphill. One per bracket.'),
    ]),
    ('Field fit', [
        (['bracket_wedge_gap_1_64.stl', 'bracket_wedge_gap_2_64.stl', 'bracket_wedge_gap_3_64.stl', 'bracket_wedge_gap_4_64.stl'],
         'make_bracket_wedges.py', 'Tapered wedges for a gap between a bracket leg and its post. Notches show the gap in 64ths.'),
        (['rail_spacer_4in_pitch_vase.stl'], 'make_rail_spacer_vase.py', 'Railhead-to-underside spacer for the outside track, 3.120 in with track height 0.160 in. Spiral vase.'),
    ]),
    ('Shop tool', [
        (['router_sigerio_test_plate.stl', 'router_sigerio_test_plate_body.stl', 'router_sigerio_test_plate_screw_rings.stl'],
         None, 'MW104 router to Sigerio circle-jig adapter, test plate. Hole sizes and center bore are estimates.'),
    ]),
]
OBSOLETE = ['bracket_pocket_template.stl', 'entry_transition_shim.stl', 'entry_transition_shim_inside.stl',
            'entry_transition_shim_outside.stl', 'entry_wedge_riser.stl']
EXTRA_SCRIPTS = ['router_template_lattice.py', 'stl_text.py', 'make_lap_screw_template.py']


# GROUPS with each part as a Fixture
PARTS: list[tuple[str, list[Fixture]]] = [(g, [Fixture(*row) for row in rows]) for g, rows in GROUPS]


def size(n: int) -> str:
    return f'{n/1024:.0f} KB' if n < 1024 * 1024 else f'{n/1048576:.1f} MB'


def dims(path: Path) -> tuple[str, str, int]:
    """(extents in mm, extents in inches, face count) of an STL."""
    m = trimesh.load(path, force='mesh')
    e = m.extents
    mm = ' × '.join(f'{v:.1f}' for v in e)
    inch = ' × '.join(f'{v/25.4:.2f}' for v in e)
    return mm, inch, len(m.faces)


class HelixPageError(Exception):
    """The STL folder and the parts list disagree; the message lists the files."""


def listed_files() -> set[str]:
    """Every STL and 3MF the index lists; exits when one on disk is not classified or a listed one is gone."""
    listed = {f for _, rows in PARTS for row in rows for f in row.files}
    on_disk = {p.name for p in SRC.iterdir() if p.name.endswith(('.stl', '.3mf'))}
    missing = on_disk - listed - set(OBSOLETE)
    gone = listed - on_disk
    if missing or gone:
        raise HelixPageError(f'unclassified: {sorted(missing)}  missing: {sorted(gone)}')
    return listed


def stl_rows() -> list[str]:
    """The STL index's table rows: a heading row per group, then a row per file with its part's script and note."""
    rows_html = []
    for group, rows in PARTS:
        rows_html.append(f'<tr class="grp"><th colspan="5">{group}</th></tr>')
        for row in rows:
            cells = []
            for f in row.files:
                p = SRC / f
                if f.endswith('.stl'):
                    mm, inch, _faces = dims(p)
                    ext = f'{mm} mm<br><span class="muted">{inch} in</span>'
                else:
                    ext = '<span class="muted">3MF project (body + modifier)</span>'
                cells.append(f'<tr><td><a href="stl/{f}" download><code>{f}</code></a></td>'
                             f'<td>{size(p.stat().st_size)}</td><td>{ext}</td>')
            sc = f'<code>{row.script}</code>' if row.script else '<span class="muted">none kept</span>'
            span = len(cells)
            cells[0] += f'<td rowspan="{span}">{sc}</td><td rowspan="{span}">{html.escape(row.note)}</td></tr>'
            for i in range(1, span):
                cells[i] += '</tr>'
            rows_html += cells
    return rows_html


def status_page(head: str, published: dict[str, str]) -> str:
    """The build status page, with backticked file names linked to their published copies."""
    body = markdown.markdown((DOCS / STATUS).read_text(encoding="utf-8"), extensions=['tables', 'sane_lists'])
    body = re.sub(r'<(/?)h1>', r'<\1h2>', body)  # the page head carries the one h1

    def link(m: re.Match) -> str:
        name = m.group(1)
        return f'<a href="{published[name]}"><code>{name}</code></a>' if name in published else m.group(0)
    body = re.sub(r'<code>([^<]+)</code>', link, body)
    return head.replace('{{DESC}}', 'Build status of the Neville Island helix: as-built facts, decisions that override the plan, fixtures and scripts, and open items, updated 15 October 2026.').replace('{{TITLE}}', 'Helix build status').replace('{{PAGE}}', 'helix-status').replace('{{BODY}}', f'''
    <div class="page-head">
      <h1>Helix build status</h1>
      <p class="muted">Rendered from <a href="files/{STATUS}"><code>{STATUS}</code></a></p>
    </div>
    <div class="guide-body helix-wrap prose">
{body}
    </div>''')


def index_page(head: str, rows_html: list[str], n_files: int) -> str:
    """The helix index: the instruction documents and the STL index."""
    plan_kb = size((DOCS / PLAN).stat().st_size)
    tmpl_kb = size((DOCS / 'lap_screw_template.pdf').stat().st_size)
    obs = ', '.join(f'<code>{f}</code>' for f in OBSOLETE)
    return head.replace('{{DESC}}', 'Neville Island helix construction plan and printed fixtures: the 13-page plan PDF, the half-lap screw template and the design handoff.').replace('{{TITLE}}', 'Neville Island helix').replace('{{PAGE}}', 'helix').replace('{{BODY}}', f'''
    <div class="page-head">
      <h1>Neville Island helix</h1>
      <p class="muted">Construction plan and the printed fixtures for the 26 / 31.75 in helix · updated 15 October 2026</p>
    </div>
    <div class="guide-body helix-wrap prose">
      <h2>Instructions</h2>
      <div class="card-grid">
        <a class="card" href="files/{PLAN}"><h3>Construction plan (PDF)</h3>
          <p>13 pages, {plan_kb}. Frames, braces, bracket elevations, roadbed cut sheets, build sequence, diagonal bracing. <strong>Page 13: half-lap screw template.</strong></p></a>
        <a class="card" href="files/lap_screw_template.pdf"><h3>Half-lap screw template (PDF)</h3>
          <p>US Letter, {tmpl_kb}. Print at 100% / Actual size, then check the 2 in and 50 mm bars. Six #6 × 5/8 screws per lap.</p></a>
        <a class="card" href="files/{HANDOFF}"><h3>Design handoff (Markdown)</h3>
          <p>Design rationale, alternatives considered, and formulas behind the locked plan.</p></a>
      </div>

      <h2>Printed fixtures (STL index)</h2>
      <p>{n_files} files, all modelled in millimetres and checked as watertight single bodies. Extents are the bounding box as exported (X × Y × Z). Unless a part is marked <em>tested</em>, it has only been verified in software.</p>
      <p>Printing: Creality Print 7.3, 260 mm bed. Templates print router face down, 2–3 walls, 10–15% infill, no supports. For the 3MF files, if the modifier doesn't come in, import the body and its <code>_CORE100</code> STL together as one object, set the core to Modifier, and give it 100% infill.</p>
      <div class="table-wrap">
        <table class="roster stl-index">
          <thead><tr><th>File</th><th>Size</th><th>Extents</th><th>Script</th><th>Notes</th></tr></thead>
          <tbody>
{chr(10).join(rows_html)}
          </tbody>
        </table>
      </div>
      <p class="muted">Obsolete, not published: {obs}.</p>
      <p class="muted">The scripts that made these files are kept in the repository's archive, not published.</p>
    </div>''')

def main() -> None:
    try:
        listed = listed_files()
    except HelixPageError as exc:
        raise SystemExit(str(exc)) from exc
    published = {f: 'stl/' + f for f in sorted(listed)}
    for f in [PLAN, 'lap_screw_template.pdf', STATUS, HANDOFF]:
        published[f] = 'files/' + f
    # The generators are archived (archive/code/benchwork-tools/helix/); their names stay as plain text.
    head = HEAD.read_text(encoding="utf-8")
    (OUT / 'build-status.html').write_text(status_page(head, published), encoding="utf-8")
    n_files = sum(len(row.files) for _, rows in PARTS for row in rows)
    (OUT / 'index.html').write_text(index_page(head, stl_rows(), n_files), encoding="utf-8")
    scripts = {row.script for _, rows in PARTS for row in rows if row.script} | set(EXTRA_SCRIPTS)
    print('files', n_files, 'scripts', len(scripts))


if __name__ == '__main__':
    main()
