"""Shared build for the lightweight half-lap and bracket-pocket router templates (2026-10-03).

Each template is two meshes that print as one part:
  * TEMPLATE: an open lattice plate (solid border, 45 deg ribs, through-holes) with a solid
    CORE band around the bit window, the lip / fence, and countersunk screw holes.
  * CORE modifier: the band around the window, a modifier part at 100 % sparse infill, so the
    wall the bearing rides is solid while the lattice prints at the normal 10-15 %.
write_3mf() puts both in one Creality Print / Orca 3MF as one object (template part +
modifier part, already lined up, modifier already set to 100 %).

All plan geometry is in inches in the template's local frame (end face on the x axis);
meshes are mm. Printed router-face-down: lip / fence point up, lattice holes are vertical,
no supports.
"""
import zipfile
import numpy as np
import trimesh
import manifold3d
from shapely import set_precision
from shapely.geometry import Point, LineString, box
from shapely.ops import unary_union
from shapely import affinity
from stl_text import label_cutters

IN = 25.4
CORE_W = 0.25           # solid band around the bit window (where the bearing rides)
BORDER = 0.12           # rim around the outside of the plate (rib height)
RIB = 0.1               # lattice rib width (2.5 mm)
RIB_H = 0.25            # rib + rim height from the router face. Full height (bears on the wood):
                        # core band, screw bosses, lip and fence only. The end-side rail is over
                        # air anyway and the screws clamp the shoulder-side rail.
PITCH = 1.75            # lattice rib spacing; holes ~1.6 in, a 3+ in router base always spans ribs
HOLE_FILLET = 0.08      # rounds the hole corners
MIN_HOLE = 0.12         # in^2; smaller lattice slivers are filled in
ENGRAVE = 1.0           # mm label depth, into the UNDERSIDE (wood side, top as printed) of a
                        # solid pad at rib height, so the router face / first layer has no text
# #6 flat-head screw, countersunk from the router face, head 0.5 mm below the surface
SCREW_SHAFT = 0.156
SCREW_HEAD = 0.340
SCREW_RECESS = 0.5      # mm
BOSS_R = 0.3


def border_of(plate):
    return plate.difference(plate.buffer(-BORDER, join_style=2))


def lattice_footprint(plate, solids):
    """Plate outline -> solid footprint: border + 45 deg ribs + the given solid regions."""
    x0, y0, x1, y1 = plate.bounds
    span = (x1 - x0) + (y1 - y0)
    cy = (y0 + y1) / 2
    ribs = []
    for c in np.arange(x0 - span, x1 + span, PITCH):   # +45 and -45 deg lines through (c, cy)
        ribs.append(LineString([(c - span, cy - span), (c + span, cy + span)]))
        ribs.append(LineString([(c - span, cy + span), (c + span, cy - span)]))
    rib = unary_union(ribs).buffer(RIB / 2, cap_style=2)
    solid = unary_union([border_of(plate), rib.intersection(plate)] + list(solids)).intersection(plate)
    holes = plate.difference(solid)
    keep = [h.buffer(-HOLE_FILLET).buffer(HOLE_FILLET) for h in getattr(holes, "geoms", [holes])
            if h.area >= MIN_HOLE]
    keep = [h for h in keep if not h.is_empty]
    return plate.difference(unary_union(keep)) if keep else plate


def _prisms(g, h, z0):
    out = []
    g = set_precision(g, 0.002).buffer(0)       # mm grid: no sub-micron slivers between regions
    for poly in getattr(g, "geoms", [g]):
        if poly.is_empty or poly.area < 1e-6:
            continue
        m = trimesh.creation.extrude_polygon(poly, h)
        m.apply_translation([0, 0, z0])
        out.append(m)
    return out


def _mm(g):
    return affinity.scale(g, IN, IN, origin=(0, 0))


def _countersunk_hole(x, y, plate_t_mm):
    """Shaft through everything plus a 90 deg cone opening at z=0 (the router face)."""
    rs, rh = SCREW_SHAFT / 2 * IN, SCREW_HEAD / 2 * IN + SCREW_RECESS
    shaft = trimesh.creation.cylinder(rs, plate_t_mm + 4, sections=64)
    shaft.apply_translation([x, y, plate_t_mm / 2])
    # 90 deg cone, wide end down: base r = rh+1 at z = -1, so r = rh at the face, narrowing to the
    # shaft at z = rh - rs (apex at z = rh, inside the shaft).
    cone = trimesh.creation.cone(rh + 1, rh + 1, sections=64)
    cone.apply_translation([x, y, -1])
    return [shaft, cone]


def build(plate, window, lip, fence, screws, plate_t, block_h, label_lines, label_xy, label_size,
          mirror):
    """Returns (template_mesh, core_mesh) in mm, printed frame (router face at z=0)."""
    flip = (lambda g: affinity.scale(g, 1, -1, origin=(0, 0))) if mirror else (lambda g: g)
    plate, window, lip, fence = map(flip, (plate, window, lip, fence))
    screws = [(x, -y if mirror else y) for x, y in screws]
    lx, ly = label_xy[0], -label_xy[1] if mirror else label_xy[1]

    core = window.buffer(CORE_W, join_style=2).intersection(plate).difference(window)
    bosses = [Point(x, y).buffer(BOSS_R, 64) for x, y in screws]
    fence_pad = fence.buffer(0.05, join_style=2).intersection(plate)
    full = [core, lip, fence_pad] + bosses
    t, h = plate_t * IN, block_h * IN
    rib_h = min(RIB_H * IN, t)
    label_cut, pad = [], []
    if label_lines:
        # Read from the underside (as printed, from above), so not mirrored.
        label_cut = label_cutters(label_lines, lx * IN, ly * IN, label_size, rib_h - ENGRAVE,
                                  ENGRAVE + 1)
        b = trimesh.util.concatenate(label_cut).bounds
        pad = [affinity.scale(box(b[0][0] - 3, b[0][1] - 3, b[1][0] + 3, b[1][1] + 3),
                              1 / IN, 1 / IN, origin=(0, 0)).intersection(plate)]
    lattice = lattice_footprint(plate, full + pad)
    full = unary_union(full).intersection(plate)

    parts = _prisms(_mm(lattice), rib_h, 0) + _prisms(_mm(full), t, 0) + _prisms(_mm(lip), t + h, 0) + _prisms(_mm(fence), h, t)

    cuts = []
    for x, y in screws:
        cuts += _countersunk_hole(x * IN, y * IN, t)
    cuts += label_cut
    body = trimesh.boolean.union(parts, engine="manifold")
    body = trimesh.boolean.difference([body] + cuts, engine="manifold")

    core_m = trimesh.boolean.union(_prisms(_mm(core), t, 0), engine="manifold")
    shift = -body.bounds[0] * [1, 1, 0]
    body.apply_translation(shift)
    core_m.apply_translation(shift)
    return body, core_m


CORE_SETTINGS = {"sparse_infill_density": "100%"}


def write_3mf(path, name, parts, bed_center=(130, 130)):
    """Creality Print / Orca / Bambu project 3MF: ONE object whose parts keep their relative
    positions. parts: [(part_name, mesh, subtype, {setting: value})], subtype "normal_part"
    or "modifier_part"; settings become that part's per-part overrides."""
    lo = np.min([m.bounds[0] for _, m, _, _ in parts], axis=0)
    hi = np.max([m.bounds[1] for _, m, _, _ in parts], axis=0)
    off = -np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    oid = len(parts) + 1
    uid = lambda n: f"{n:08x}-61cb-4c03-9d28-80fed5dfa1dc"
    sub, comps, conf = [], [], []
    for i, (pname, mesh, subtype, settings) in enumerate(parts, 1):
        v = mesh.vertices + off
        verts = "".join(f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>' for x, y, z in v)
        tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces)
        sub.append(f'<object id="{i}" p:UUID="{uid(0x10000 + i)}" type="model"><mesh><vertices>{verts}'
                   f'</vertices><triangles>{tris}</triangles></mesh></object>')
        comps.append(f'<component p:path="/3D/Objects/object_1.model" objectid="{i}" '
                     f'p:UUID="{uid(0x20000 + i)}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>')
        meta = "".join(f'<metadata key="{k}" value="{val}"/>' for k, val in settings.items())
        conf.append(f'<part id="{i}" subtype="{subtype}"><metadata key="name" value="{pname}"/>'
                    '<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>'
                    f'{meta}<mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0" '
                    'facets_reversed="0" backwards_edges="0"/></part>')
    ns = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
          'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
          'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"')
    head = '<?xml version="1.0" encoding="UTF-8"?>\n'
    tx, ty = bed_center
    model = (f'{head}<model unit="millimeter" xml:lang="en-US" {ns}>'
             '<metadata name="Application">Creality_Print V7.0.1.4212 Release</metadata>'
             '<metadata name="BambuStudio:3mfVersion">1</metadata>'
             f'<metadata name="Title">{name}</metadata>'
             f'<resources><object id="{oid}" p:UUID="{uid(1)}" type="model"><components>{"".join(comps)}'
             f'</components></object></resources><build p:UUID="{uid(2)}"><item objectid="{oid}" '
             f'p:UUID="{uid(3)}" transform="1 0 0 0 1 0 0 0 1 {tx} {ty} 0" printable="1"/></build></model>')
    objects = (f'{head}<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/'
               '3dmanufacturing/core/2015/02" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/'
               f'production/2015/06"><resources>{"".join(sub)}</resources><build/></model>')
    config = (f'{head}<config><object id="{oid}"><metadata key="name" value="{name}"/>'
              f'<metadata key="extruder" value="1"/>{"".join(conf)}</object>'
              '<plate><metadata key="plater_id" value="1"/><metadata key="plater_name" value=""/>'
              '<metadata key="locked" value="false"/><model_instance>'
              f'<metadata key="object_id" value="{oid}"/><metadata key="instance_id" value="0"/>'
              '</model_instance></plate><assemble>'
              f'<assemble_item object_id="{oid}" instance_id="0" transform="1 0 0 0 1 0 0 0 1 {tx} {ty} 0" '
              'offset="0 0 0"/></assemble></config>')
    rel = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
           '<Relationship Target="{}" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/'
           '2013/01/3dmodel"/></Relationships>')
    types = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships'
             '+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-'
             '3dmodel+xml"/></Types>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", head + types)
        z.writestr("_rels/.rels", head + rel.format("/3D/3dmodel.model"))
        z.writestr("3D/3dmodel.model", model)
        z.writestr("3D/_rels/3dmodel.model.rels", head + rel.format("/3D/Objects/object_1.model"))
        z.writestr("3D/Objects/object_1.model", objects)
        z.writestr("Metadata/model_settings.config", config)


def clean(m, tol=0.01):
    """Collapse edges < tol mm so the mesh stays watertight after float32 STL rounding."""
    mf = manifold3d.Manifold(manifold3d.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                                             tri_verts=np.asarray(m.faces, np.uint32)))
    out = mf.simplify(tol).to_mesh()
    return trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts))


def stl_roundtrip_ok(path):
    m = trimesh.load(path)
    return m.is_watertight and m.is_volume


def export(base, body, core):
    """base: path without extension. Writes base.stl, base_CORE100.stl and base.3mf."""
    name = base.rsplit("/", 1)[-1]
    body, core = clean(body), clean(core)
    body.export(base + ".stl")
    core.export(base + "_CORE100.stl")
    write_3mf(base + ".3mf", name, [(name, body, "normal_part", {}),
                                    (name + "_CORE100", core, "modifier_part", CORE_SETTINGS)])
    print(base, "watertight", body.is_watertight, core.is_watertight,
          "after STL reload", stl_roundtrip_ok(base + ".stl"), stl_roundtrip_ok(base + "_CORE100.stl"),
          "bodies", len(body.split(only_watertight=False)), len(core.split(only_watertight=False)),
          "size mm", np.round(body.extents, 1),
          "vol cm3", round(body.volume / 1000, 1), "core", round(core.volume / 1000, 1))
