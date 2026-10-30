#!/usr/bin/env python3
"""Pack the per-colour STLs into one Creality Print 3MF, in the same layout as the
helix templates: one object, parts in place, filaments 1-4 in PARTS order.

STL has no units, so the slicer guesses from size and takes the small gold part for
inches. A 3MF declares millimetres.

    python3 cats/station_maps_3d/make_3mf.py
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

STL_DIR = Path(__file__).resolve().parent / "stl"
NAME = "barn"
PARTS = ["white", "black", "teal", "gold"]
BED_CENTER = (130, 130)

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'
VERTEX = re.compile(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)")
RELS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Target="{}" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/'
    '2013/01/3dmodel"/></Relationships>'
)
TYPES = (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships'
    '+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-'
    '3dmodel+xml"/></Types>'
)


def uid(n: int) -> str:
    return f"{n:08x}-61cb-4c03-9d28-80fed5dfa1dc"


def read_stl(path: Path):
    """Read an ASCII STL into shared vertices and triangles."""
    index: dict[tuple[float, float, float], int] = {}
    verts = []
    corners = []
    for m in VERTEX.finditer(path.read_text()):
        p = tuple(float(c) for c in m.groups())
        if p not in index:
            index[p] = len(verts)
            verts.append(p)
        corners.append(index[p])
    tris = [corners[i : i + 3] for i in range(0, len(corners), 3)]
    return verts, tris


def main() -> None:
    meshes = [(p, *read_stl(STL_DIR / f"{NAME}_{p}.stl")) for p in PARTS]
    all_verts = [v for _, verts, _ in meshes for v in verts]
    lo = [min(v[i] for v in all_verts) for i in range(3)]
    hi = [max(v[i] for v in all_verts) for i in range(3)]
    off = ((lo[0] + hi[0]) / -2, (lo[1] + hi[1]) / -2, -lo[2])

    oid = len(meshes) + 1
    sub, comps, conf = [], [], []
    for i, (pname, verts, tris) in enumerate(meshes, 1):
        vx = "".join(
            f'<vertex x="{x + off[0]:.5f}" y="{y + off[1]:.5f}" z="{z + off[2]:.5f}"/>'
            for x, y, z in verts
        )
        tx = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
        sub.append(
            f'<object id="{i}" p:UUID="{uid(0x10000 + i)}" type="model"><mesh><vertices>{vx}'
            f"</vertices><triangles>{tx}</triangles></mesh></object>"
        )
        comps.append(
            f'<component p:path="/3D/Objects/object_1.model" objectid="{i}" '
            f'p:UUID="{uid(0x20000 + i)}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
        )
        conf.append(
            f'<part id="{i}" subtype="normal_part"><metadata key="name" value="{NAME}_{pname}"/>'
            '<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>'
            f'<metadata key="extruder" value="{i}"/><mesh_stat edges_fixed="0" degenerate_facets="0" '
            'facets_removed="0" facets_reversed="0" backwards_edges="0"/></part>'
        )

    ns = (
        'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
        'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
        'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p"'
    )
    bx, by = BED_CENTER
    model = (
        f'{HEAD}<model unit="millimeter" xml:lang="en-US" {ns}>'
        '<metadata name="Application">Creality_Print V7.0.1.4212 Release</metadata>'
        '<metadata name="BambuStudio:3mfVersion">1</metadata>'
        f'<metadata name="Title">{NAME}</metadata>'
        f'<resources><object id="{oid}" p:UUID="{uid(1)}" type="model"><components>{"".join(comps)}'
        f'</components></object></resources><build p:UUID="{uid(2)}"><item objectid="{oid}" '
        f'p:UUID="{uid(3)}" transform="1 0 0 0 1 0 0 0 1 {bx} {by} 0" printable="1"/></build></model>'
    )
    objects = (
        f'{HEAD}<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/'
        '3dmanufacturing/core/2015/02" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/'
        f'production/2015/06"><resources>{"".join(sub)}</resources><build/></model>'
    )
    config = (
        f'{HEAD}<config><object id="{oid}"><metadata key="name" value="{NAME}"/>'
        f'<metadata key="extruder" value="1"/>{"".join(conf)}</object>'
        '<plate><metadata key="plater_id" value="1"/><metadata key="plater_name" value=""/>'
        '<metadata key="locked" value="false"/><model_instance>'
        f'<metadata key="object_id" value="{oid}"/><metadata key="instance_id" value="0"/>'
        "</model_instance></plate><assemble>"
        f'<assemble_item object_id="{oid}" instance_id="0" transform="1 0 0 0 1 0 0 0 1 {bx} {by} 0" '
        'offset="0 0 0"/></assemble></config>'
    )

    out = STL_DIR / f"{NAME}.3mf"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", HEAD + TYPES)
        z.writestr("_rels/.rels", HEAD + RELS.format("/3D/3dmodel.model"))
        z.writestr("3D/3dmodel.model", model)
        z.writestr("3D/_rels/3dmodel.model.rels", HEAD + RELS.format("/3D/Objects/object_1.model"))
        z.writestr("3D/Objects/object_1.model", objects)
        z.writestr("Metadata/model_settings.config", config)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
