"""Publish the Neville Island helix package into the ops portal (helix/).

Reads ~/Downloads/stl. Needs markdown and trimesh. Run: python scripts/build_helix_page.py
"""
import html, os, re, shutil, sys
import markdown, trimesh

SRC = os.path.expanduser('~/Downloads/stl')
PORTAL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PORTAL, 'helix')
PLAN = 'helix_construction_plan_FINAL_31p75_18p75_2026-09-23.pdf'
STATUS = 'HART_Neville_Helix_BUILD_STATUS.md'
HANDOFF = 'HART_Neville_Helix_Agent_Handoff_FINAL_31p75_18p75_2026-09-23.md'

# (group, [(files, script, note)])
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
    ('Shop tool', [
        (['router_sigerio_test_plate.stl', 'router_sigerio_test_plate_body.stl', 'router_sigerio_test_plate_screw_rings.stl'],
         None, 'MW104 router to Sigerio circle-jig adapter, test plate. Hole sizes and center bore are estimates.'),
    ]),
]
OBSOLETE = ['bracket_pocket_template.stl', 'entry_transition_shim.stl', 'entry_transition_shim_inside.stl',
            'entry_transition_shim_outside.stl', 'entry_wedge_riser.stl']
EXTRA_SCRIPTS = ['router_template_lattice.py', 'stl_text.py', 'make_lap_screw_template.py']


def size(n):
    return f'{n/1024:.0f} KB' if n < 1024 * 1024 else f'{n/1048576:.1f} MB'


def dims(path):
    m = trimesh.load(path, force='mesh')
    e = m.extents
    mm = ' × '.join(f'{v:.1f}' for v in e)
    inch = ' × '.join(f'{v/25.4:.2f}' for v in e)
    return mm, inch, len(m.faces)


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    for d in ('stl', 'scripts', 'files'):
        os.makedirs(os.path.join(OUT, d))

    # Check that every current STL is classified.
    listed = {f for _, rows in GROUPS for files, _, _ in rows for f in files}
    on_disk = {f for f in os.listdir(SRC) if f.endswith(('.stl', '.3mf'))}
    missing = on_disk - listed - set(OBSOLETE)
    gone = listed - on_disk
    if missing or gone:
        sys.exit(f'unclassified: {sorted(missing)}  missing: {sorted(gone)}')

    for f in [PLAN, 'lap_screw_template.pdf', STATUS, HANDOFF]:
        shutil.copy2(os.path.join(SRC, f), os.path.join(OUT, 'files', f))
    scripts = sorted({s for _, rows in GROUPS for _, s, _ in rows if s} | set(EXTRA_SCRIPTS))
    for s in scripts:
        shutil.copy2(os.path.join(SRC, s), os.path.join(OUT, 'scripts', s))

    published = {}
    for f in sorted(listed):
        shutil.copy2(os.path.join(SRC, f), os.path.join(OUT, 'stl', f))
        published[f] = 'stl/' + f
    for f in [PLAN, 'lap_screw_template.pdf', STATUS, HANDOFF]:
        published[f] = 'files/' + f
    for s in scripts:
        published[s] = 'scripts/' + s

    # STL index (HTML rows + Markdown rows)
    rows_html, md = [], []
    n_files = 0
    for group, rows in GROUPS:
        rows_html.append(f'<tr class="grp"><th colspan="5">{group}</th></tr>')
        md += [f'\n### {group}\n', '| File | Size | Extents mm (in) | Script | Notes |', '|---|---|---|---|---|']
        for files, script, note in rows:
            cells = []
            mdcells = []
            for f in files:
                n_files += 1
                p = os.path.join(SRC, f)
                if f.endswith('.stl'):
                    mm, inch, faces = dims(p)
                    ext = f'{mm} mm<br><span class="muted">{inch} in</span>'
                    mdext = f'{mm} ({inch})'
                else:
                    ext, mdext = '<span class="muted">3MF project (body + modifier)</span>', '3MF project'
                cells.append(f'<tr><td><a href="stl/{f}" download><code>{f}</code></a></td>'
                             f'<td>{size(os.path.getsize(p))}</td><td>{ext}</td>')
                mdcells.append((f, size(os.path.getsize(p)), mdext))
            sc = f'<a href="scripts/{script}"><code>{script}</code></a>' if script else '<span class="muted">none kept</span>'
            span = len(cells)
            cells[0] += f'<td rowspan="{span}">{sc}</td><td rowspan="{span}">{html.escape(note)}</td></tr>'
            for i in range(1, span):
                cells[i] += '</tr>'
            rows_html += cells
            for i, (f, sz, ext) in enumerate(mdcells):
                s = (f'[`{script}`](../helix/scripts/{script})' if script else 'none kept') if i == 0 else '″'
                nt = note if i == 0 else '″'
                md.append(f'| [`{f}`](../helix/stl/{f}) | {sz} | {ext} | {s} | {nt} |')

    # Build status page, with backticked filenames linked to the published copies.
    text = open(os.path.join(SRC, STATUS)).read()
    body = markdown.markdown(text, extensions=['tables', 'sane_lists'])

    def link(m):
        name = m.group(1)
        return f'<a href="{published[name]}"><code>{name}</code></a>' if name in published else m.group(0)
    body = re.sub(r'<code>([^<]+)</code>', link, body)

    head = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'helix_page_head.html')).read()
    page = head.replace('{{TITLE}}', 'Helix build status').replace('{{BODY}}', f'''
    <div class="page-head">
      <h1>Helix build status</h1>
      <p class="muted"><a href="index.html">Neville Island helix</a> · rendered from <a href="files/{STATUS}"><code>{STATUS}</code></a></p>
    </div>
    <div class="guide-body helix-wrap prose">
{body}
    </div>''')
    open(os.path.join(OUT, 'build-status.html'), 'w').write(page)

    plan_kb = size(os.path.getsize(os.path.join(SRC, PLAN)))
    tmpl_kb = size(os.path.getsize(os.path.join(SRC, 'lap_screw_template.pdf')))
    obs = ', '.join(f'<code>{f}</code>' for f in OBSOLETE)
    index = head.replace('{{TITLE}}', 'Neville Island helix').replace('{{BODY}}', f'''
    <div class="page-head">
      <h1>Neville Island helix</h1>
      <p class="muted">Construction plan, build status, and the printed fixtures for the 26 / 31.75 in helix · updated 15 October 2026</p>
    </div>
    <div class="guide-body helix-wrap prose">
      <h2>Instructions</h2>
      <div class="card-grid">
        <a class="card" href="files/{PLAN}"><h3>Construction plan (PDF)</h3>
          <p>13 pages, {plan_kb}. Frames, braces, bracket elevations, roadbed cut sheets, build sequence, diagonal bracing. <strong>Page 13: half-lap screw template.</strong></p></a>
        <a class="card" href="files/lap_screw_template.pdf"><h3>Half-lap screw template (PDF)</h3>
          <p>US Letter, {tmpl_kb}. Print at 100% / Actual size, then check the 2 in and 50 mm bars. Six #6 × 5/8 screws per lap.</p></a>
        <a class="card" href="build-status.html"><h3>Build status</h3>
          <p>As-built heights and datums, frame alignment, shop process, fasteners, every fixture, and open items. Overrides the PDF where they differ.</p></a>
        <a class="card" href="files/{HANDOFF}"><h3>Design handoff (Markdown)</h3>
          <p>Design rationale, alternatives considered, and formulas behind the locked plan.</p></a>
      </div>
      <p class="note">Read the plan first, then the build status. The plan's entry pages (2, 3, 8) are out of date; the build status has the current entry geometry.</p>

      <h2>Printed fixtures (STL index)</h2>
      <p>{n_files} files, all modelled in millimetres and checked as watertight single bodies. Extents are the bounding box as exported (X × Y × Z). Unless the build status marks a part <em>tested</em>, it has only been verified in software.</p>
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
      <p class="muted">Scripts need Python with <code>numpy trimesh manifold3d shapely mapbox_earcut scipy rtree networkx matplotlib pymupdf pypdf</code>. Their output paths point at the original working folder; change them before running.</p>
    </div>''')
    open(os.path.join(OUT, 'index.html'), 'w').write(index)

    mdtext = ['# Neville Island Helix — Instructions and STL Index', '',
              '*Updated 15 October 2026. Web version: [helix/index.html](../helix/index.html).*', '',
              '## Instructions', '',
              f'- [Construction plan PDF](../helix/files/{PLAN}): 13 pages. **Page 13 is the half-lap screw template.**',
              '- [Half-lap screw template PDF](../helix/files/lap_screw_template.pdf): US Letter, print at 100%, check the 2 in / 50 mm bars.',
              f'- [Build status](../helix/files/{STATUS}): as-built facts; overrides the PDF where they differ.',
              f'- [Design handoff](../helix/files/{HANDOFF}): rationale and formulas.', '',
              '## STL index', '',
              f'{n_files} files, all in millimetres. Extents are the exported bounding box, X × Y × Z.'] + md + [
              '', 'Obsolete, not published: ' + ', '.join(f'`{f}`' for f in OBSOLETE) + '.', '']
    open(os.path.join(PORTAL, 'docs', 'Helix_Instructions_and_STL_Index.md'), 'w').write('\n'.join(mdtext))
    print('files', n_files, 'scripts', len(scripts))


if __name__ == '__main__':
    main()
